"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini (ONLY approved 3.8 & 3.5 Flash models for ultra-fast sub-second responses)
Integrations: Green-API / Meta WhatsApp Webhook, NetSpark & KosherPlay Filtering, Lab & Repair Services
Persistent Memory & Sync: Permanent Code Seed, Local JSON Cache, SQLite with Render Persistent Disk Support
Keep-Alive: Built-in background ping loop to prevent Render cold starts!
Multi-Route Webhook: Listens on /, /webhook/whatsapp, /webhook, /whatsapp, and all POST paths!
"""

import os
import json
import sqlite3
import re
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# ----------------- Environment Variables -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip().strip('"').strip("'")

# Both of Eran's numbers are registered as permanent admin phones
ADMIN_PHONES = ["972553164770", "972524043644"]
DEFAULT_ADMIN_PHONE = "972524043644"
_raw_admin = os.getenv("ADMIN_WHATSAPP_PHONE", DEFAULT_ADMIN_PHONE).strip().strip('"').strip("'")
ADMIN_WHATSAPP_PHONE = DEFAULT_ADMIN_PHONE if (not _raw_admin or _raw_admin == "972500000000") else _raw_admin

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().strip('"').strip("'")
PORT = os.getenv("PORT", "8000")

# ----------------- Gemini Client Setup (Clean Client, No Invalid Short Deadline) -----------------
# Note: Google GenAI API requires deadline >= 10s. Default client handles standard deadlines cleanly!
client = genai.Client(api_key=GEMINI_API_KEY) if (genai and GEMINI_API_KEY) else None

# כלל ברזל קבוע: אך ורק מודלים מאושרים ומהירים מסדרות 3.8 ו-3.5 בלבד!
# חל איסור מוחלט להכניס מודלים ישנים (ללא 2.0, ללא 1.5, ללא 2.5) כדי למנוע שגיאות ועיכובים.
APPROVED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]
ACTIVE_MODELS = [
    m for m in APPROVED_MODELS
    if m.startswith(("gemini-3.8", "gemini-3.5"))
]

def build_fast_gen_config(system_instruction: str):
    """
    Builds a low-latency GenerateContentConfig.
    max_output_tokens=1000 ensures complete, natural sentences and tags are never truncated mid-word!
    """
    if not types:
        return None
    try:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=1000,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    except Exception:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=1000,
        )

# ----------------- Database & Persistent Storage Setup -----------------
def resolve_working_db_path() -> str:
    explicit = os.getenv("DB_PATH", "").strip()
    candidates = []
    if explicit:
        candidates.append(explicit)
    for disk in ["/var/data", "/data", "/opt/render/project/src/data"]:
        if os.path.exists(disk) and os.path.isdir(disk):
            candidates.append(os.path.join(disk, "agent_memory.db"))
    candidates.extend(["agent_memory.db", "/tmp/agent_memory.db"])
    for p in candidates:
        try:
            conn = sqlite3.connect(p, timeout=5)
            conn.execute("CREATE TABLE IF NOT EXISTS _probe (id INT)")
            conn.commit()
            conn.close()
            return p
        except Exception:
            continue
    return ":memory:"

DB_PATH = resolve_working_db_path()
BACKUP_JSON_PATH = os.path.join(
    os.path.dirname(DB_PATH) if (DB_PATH != ":memory:" and os.path.dirname(DB_PATH)) else "/tmp",
    "contacts_cache.json"
)

# Shared HTTP connection pool with keep-alive to avoid SSL handshake overhead on every message
http_session = httpx.Client(
    timeout=10,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60)
)

# ----------------- Keep-Alive Background Task (Render Cold-Start Preventer) -----------------
async def keep_alive_loop():
    """Pings the server itself every 9 minutes so Render free tier never sleeps."""
    target_url = RENDER_EXTERNAL_URL or f"http://127.0.0.1:{PORT}"
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"
    ping_url = f"{target_url.rstrip('/')}/healthz"

    await asyncio.sleep(45)
    async with httpx.AsyncClient(timeout=10) as aclient:
        while True:
            try:
                resp = await aclient.get(ping_url)
                print(f"[Keep-Alive] Pinged {ping_url} - Status: {resp.status_code}")
            except Exception as e:
                print(f"[Keep-Alive] Ping notice: {e}")
            await asyncio.sleep(540)

async def verify_green_api_on_startup():
    """
    Read-only diagnostic check on startup.
    IMPORTANT: Does NOT call setSettings if webhookUrl and incomingWebhook are already set,
    because calling Green-API setSettings reboots the WhatsApp instance for up to 5 minutes!
    """
    await asyncio.sleep(3)
    base, token, _ = parse_green_api_credentials()
    if not base or not token:
        print("[Green-API Check] WHATSAPP_API_URL not configured or custom gateway in use.")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as aclient:
            state_resp = await aclient.get(f"{base}/getStateInstance/{token}")
            print(f"[Green-API State]: {state_resp.status_code} - {state_resp.text[:120]}")

            settings_resp = await aclient.get(f"{base}/getSettings/{token}")
            if settings_resp.status_code == 200:
                settings = settings_resp.json()
                curr_url = settings.get("webhookUrl", "")
                inc_wh = settings.get("incomingWebhook", "")
                print(f"[Green-API Settings]: webhookUrl='{curr_url}', incomingWebhook='{inc_wh}'")
                # Only call setSettings if webhookUrl is completely missing or incomingWebhook is disabled
                if not curr_url or inc_wh != "yes":
                    render_url = (RENDER_EXTERNAL_URL or "https://ns-whatsapp-agent-1.onrender.com").strip().rstrip("/")
                    target_webhook = curr_url or f"{render_url}/webhook/whatsapp"
                    payload = {
                        "webhookUrl": target_webhook,
                        "incomingWebhook": "yes",
                        "outgoingMessageWebhook": "no",
                        "outgoingAPIMessageWebhook": "no"
                    }
                    fix_resp = await aclient.post(f"{base}/setSettings/{token}", json=payload)
                    print(f"[Green-API Auto-Repair] Applied missing webhook settings: {fix_resp.status_code}")
    except Exception as exc:
        print(f"[Green-API Startup Check Notice]: {exc}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    check_task = asyncio.create_task(verify_green_api_on_startup())
    keep_alive_task = asyncio.create_task(keep_alive_loop())
    yield
    check_task.cancel()
    keep_alive_task.cancel()

app = FastAPI(title="ShieldBot AI - WhatsApp Agent", lifespan=lifespan)

# ----------------- Phone Normalization -----------------
def normalize_phone(phone: str) -> str:
    """
    Normalizes phone numbers, stripping WhatsApp device IDs (e.g. :0, :12) and domain suffixes (@c.us, @s.whatsapp.net).
    """
    if not phone:
        return ""
    raw = str(phone).split("@")[0].split(":")[0]
    digits = re.sub(r"[^0-9]", "", raw)
    if not digits:
        return ""
    if digits.startswith("9720"):
        digits = "972" + digits[4:]
    elif digits.startswith("0"):
        digits = "972" + digits[1:]
    elif digits.startswith("5") and len(digits) == 9:
        digits = "972" + digits
    return digits

# ----------------- PERMANENT CONTACTS SEED (Immune to Server Rebuilds) -----------------
PERMANENT_CONTACTS = {
    "972553164770": "ערן נקר",
    "0553164770": "ערן נקר",
    "972524043644": "ערן נקר",
    "0524043644": "ערן נקר",
    "972500000000": "מנהל מערכת",
}

COMMON_NON_NAMES = {
    "רוצה", "צריך", "יכול", "מדבר", "שואל", "מבקש", "שלום", "היי", "בוקר", "ערב",
    "יש", "אין", "לא", "כן", "פה", "כאן", "זה", "אני", "מה", "מי", "איפה", "למה",
    "כמה", "מתי", "איך", "טוב", "תודה", "בסדר", "אחלה", "יופי", "סבבה", "מסך",
    "סוללה", "שקע", "תיקון", "מעבדה", "מחיר", "עלות", "שיאומי", "סמסונג", "אייפון",
    "בדיקה", "בבקשה", "החלפה", "עזרה", "טלפון", "מכשיר", "דגם", "מנוי", "סינון",
    "הוא", "היא", "הם", "הן", "שלי", "שלך", "שלו", "שלנו", "שלכם", "אותי", "אותך",
    "אפשר", "רוצים", "בדיוק", "תגיד", "תגידו", "רציתי", "לשאול", "דבר", "נוסף",
    "מעולה", "מצוין", "מגיע", "אליכם", "מחר", "היום", "עכשיו", "בתור", "לחכות"
}

# ----------------- Greeting Detection -----------------
def is_pure_greeting(text: str) -> bool:
    clean = re.sub(r"[^\w\sא-תa-zA-Z]", " ", text or "").strip().lower()
    words = clean.split()
    if not words:
        return False
    greeting_stems = {
        "שלום", "היי", "הי", "אהלן", "בוקר", "ערב", "צהריים", "לילה", "טוב", "טובה",
        "טובים", "שלוםם", "היוש", "הייוש", "הלו", "hello", "hi", "hey", "ברכה", "נעים",
        "מה", "נשמע", "שלומך", "קורה", "העניינים", "איתך"
    }
    for w in words:
        stem = w[1:] if (w.startswith("ו") and len(w) > 2 and w not in greeting_stems) else w
        if stem not in greeting_stems and w not in greeting_stems:
            return False
    return True

# ----------------- Store Address & Opening Hours (Hadera) -----------------
STORE_ADDRESS = "רחוב ישעיהו 10, חדרה"
STORE_HOURS_DETAILS = """אנחנו נמצאים ברחוב ישעיהו 10, חדרה 📍

שעות הפעילות שלנו:
• ימים א'-ה': 12:00-20:00
• ימי ו' וערבי חג:
  - שעון קיץ: 12:00-15:30
  - שעון חורף: 10:30-13:30
• מוצאי שבת וחג: בתיאום מראש בלבד"""

def is_store_info_question(text: str) -> bool:
    clean = re.sub(r"[^\w\sא-ת]", " ", text or "").strip().lower()
    indicators = [
        "כתובת", "איפה אתם", "איפה החנות", "איפה המעבדה", "מיקום", "שעות פעילות",
        "שעות פתיחה", "מתי פתוח", "מתי אתם פתוחים", "מתי סגור", "שעות קבלה",
        "איפה אתם יושבים", "איפה נמצאים", "איפה יושבים", "איזה רחוב", "איך מגיעים",
        "איפה הסניף", "כתובת שלכם", "שעות הפעילות", "הכתובת שלכם"
    ]
    return any(ind in clean for ind in indicators)

def get_store_info_reply(customer_name: str = "") -> str:
    name_str = f" {customer_name}" if customer_name else ""
    closing = f"מוזמן להגיע אלינו{name_str}! 😃"
    return f"""{STORE_HOURS_DETAILS}

{closing}"""

# ----------------- Warranty Tracks Content (Noam Siach 3 Tracks) -----------------
WARRANTY_FULL_EXPLANATION = """📋 *השוואת מסלולי האחריות במכשירי נעם שיח:*

🔴 *1. מסלול גלות (אחריות יבואן רשמי):*
• אחריות יבואן ארצי בלבד.
• במקרה של תקלה: המכשיר נשלח למעבדת היבואן (המתנה של עד 3 שבועות).
• ללא בדיקה במקום, ללא מכשיר חלופי, ללא עדכוני תוכנה וללא העברת נתונים חינם.

🟡 *2. מסלול ימות המשיח (האחריות המומלצת שלנו ⭐):*
• איתור ותיקון תקלה ישירות במעבדה המקומית שלנו בחדרה (חוסך שבועות של המתנה!).
• מכשיר חלופי תואם בעת התיקון.
• העברת אנשי קשר ותכנים + עדכוני גרסה כשרה ללא עלות.
• תיקון אקספרס עד שעתיים ממועד המסירה.

🟢 *3. מסלול גאולה (VIP פרימיום — שקט מושלם 🛡️):*
• כל יתרונות "ימות המשיח" ובנוסף:
• *תיקון נזק לקוח (שבר / קורוזיה / נפילה) ללא עלות!* (תיקון ראשון חינם, שני ב-50% הנחה).
• החלפת מכשיר לדגם אחר עד 14 ימי עסקים (גם אם נעשה שימוש במכשיר!).
• התחייבות לתיקון או החלפת מכשיר תוך 3 שעות בלבד!

איזה מסלול תרצה שנתאים עבורך? 😃"""

def is_warranty_followup_confirmation(text: str, history_text: str) -> bool:
    clean = text.strip().lower()
    positive_signals = [
        "כן", "אשמח", "תפרט", "פרט", "מה ההבדל", "מה ההבדלים", "מעוניין", "תשלח",
        "תסביר", "רוצה לדעת", "אשמח לפירוט", "כן אשמח", "תשלח לי", "בטח", "ודאי"
    ]
    had_warranty_offer = "ההבדלים המלאים בין מסלולי האחריות" in history_text or "מסלול ימות המשיח" in history_text
    is_positive = any(clean == sig or clean.startswith(sig) for sig in positive_signals)
    direct_warranty_triggers = [
        "מסלולי אחריות", "מסלולי האחריות", "פירוט אחריות", "פירוט האחריות", "האחריות שלכם",
        "הבדל בין האחריות", "הבדל בין המסלולים", "הבדלים בין המסלולים", "מסלול גלות",
        "ימות המשיח", "מסלול גאולה", "פירוט של מסלולי", "אחריות מורחבת"
    ]
    return (had_warranty_offer and is_positive) or any(phrase in clean for phrase in direct_warranty_triggers)

# ----------------- Database Initialization & JSON Backup Sync -----------------
def sync_contacts_to_json():
    """Exports all contacts from SQLite to local JSON cache for extra durability."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT phone, name FROM contacts").fetchall()
        conn.close()
        data = {r[0]: r[1] for r in rows if r[0] and r[1]}
        with open(BACKUP_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS learned_kb (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keywords TEXT,
                answer TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS customer_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                system_name TEXT,
                request_text TEXT,
                action_taken TEXT,
                upsell_offer TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                phone TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        # 1. Seed from PERMANENT_CONTACTS
        for p, n in PERMANENT_CONTACTS.items():
            norm_p = normalize_phone(p)
            c.execute("""
                INSERT OR IGNORE INTO contacts (phone, name, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
            """, (norm_p, n))

        # 2. Restore from JSON cache if present
        if os.path.exists(BACKUP_JSON_PATH):
            try:
                with open(BACKUP_JSON_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, dict):
                    for cp, cn in cached.items():
                        norm_cp = normalize_phone(cp)
                        if norm_cp and cn:
                            c.execute("""
                                INSERT OR IGNORE INTO contacts (phone, name, created_at, updated_at)
                                VALUES (?, ?, datetime('now'), datetime('now'))
                            """, (norm_cp, str(cn).strip()))
            except Exception:
                pass

        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                role TEXT,
                message TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                name TEXT,
                system_name TEXT,
                status TEXT,
                current_level TEXT,
                device_id TEXT,
                whitelist TEXT,
                renewal_date TEXT
            )
        """)
        c.execute("SELECT COUNT(*) FROM subscribers")
        if c.fetchone()[0] == 0:
            c.executemany("""
                INSERT INTO subscribers (phone, name, system_name, status, current_level, device_id, whitelist, renewal_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                ("972524489102", "דוד כהן", "נטספרק", "active", "רחבה (350 ₪/שנה)", "NS-88412", "gov.il, bankhapoalim.co.il", "15/11/2026"),
                ("972549182736", "משה לוי", "כשר פליי", "active", "כשר פליי מורחב (200 ₪/שנה)", "KP-30941", "clalit.co.il, leumi.co.il", "01/02/2027"),
                ("972528819203", "שמעון מזרחי", "כשר פליי", "expired", "כשר פליי מורחב + דפדפן (300 ₪/שנה)", "KP-19204", "gov.il", "01/10/2026"),
                ("972501234567", "יוסף אברהמי", "כשר פליי", "active", "כשר פליי בסיסי (250 ₪ חד-פעמי)", "KP-B-102", "bankleumi.co.il, waze", "ללא תפוגה (פעיל עד החלפת מכשיר)"),
            ])
        conn.commit()
        conn.close()
        sync_contacts_to_json()
    except Exception as e:
        print(f"[Init DB Notice]: {e}")

init_db()

# ----------------- Helper Functions -----------------
def parse_green_api_credentials():
    """Extracts instance base URL, token, and clean sendMessage URL from WHATSAPP_API_URL."""
    clean = (WHATSAPP_API_URL or "").strip().strip('"').strip("'").rstrip("/")
    if "/sendMessage/" in clean:
        base, token = clean.split("/sendMessage/", 1)
        token = token.strip().strip("/")
        return base, token, f"{base}/sendMessage/{token}"
    return None, None, clean

def get_green_api_base_and_token():
    base, token, _ = parse_green_api_credentials()
    return base, token

def send_whatsapp_message(phone: str, text: str, raw_chat_id: str = "") -> bool:
    clean_phone = normalize_phone(phone)
    clean_text = (text or "").strip()
    if (not clean_phone and not raw_chat_id) or not clean_text:
        print(f"[WhatsApp Skip] Invalid phone or empty text: phone={clean_phone}")
        return False

    _, _, send_url = parse_green_api_credentials()
    if not send_url:
        print(f"[WhatsApp DryRun] No WHATSAPP_API_URL configured. Message to {clean_phone}: {clean_text[:60]}")
        return False

    target_chat_id = f"{clean_phone}@c.us" if clean_phone else raw_chat_id
    payload = {
        "chatId": target_chat_id,
        "message": clean_text
    }
    try:
        resp = http_session.post(send_url, json=payload, timeout=8)
        print(f"[WhatsApp Sent] To: {target_chat_id}, Status: {resp.status_code}, Response: {resp.text[:100]}")
        return resp.status_code == 200
    except Exception as exc:
        print(f"[WhatsApp Send Error]: {exc}")
        return False

def lookup_subscriber(phone: str, message_text: str = "") -> dict:
    """Checks subscriber status in NetSpark & KosherPlay database by phone or name mentioned in text."""
    norm = normalize_phone(phone)
    try:
        conn = sqlite3.connect(DB_PATH)
        row = None
        if norm:
            row = conn.execute(
                "SELECT name, system_name, status, current_level, device_id, whitelist, renewal_date, phone "
                "FROM subscribers WHERE phone = ? OR phone LIKE ? LIMIT 1",
                (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
            ).fetchone()
        if not row and message_text:
            all_subs = conn.execute(
                "SELECT name, system_name, status, current_level, device_id, whitelist, renewal_date, phone FROM subscribers"
            ).fetchall()
            for s in all_subs:
                if s[0] and s[0] in message_text:
                    row = s
                    break
        conn.close()
        if row:
            return {
                "found": True,
                "name": row[0],
                "system": row[1],
                "status": row[2],
                "level": row[3],
                "deviceId": row[4],
                "whitelist": row[5],
                "renewalDate": row[6],
                "phone": row[7]
            }
    except Exception:
        pass
    return {"found": False}

def get_learned_knowledge() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT keywords, answer FROM learned_kb").fetchall()
        conn.close()
        if not rows:
            return "אין עדיין כללים נוספים."
        return "\n".join([f"- מילות זיהוי ({r[0]}): תשובה שנלמדה בעבר: {r[1]}" for r in rows])
    except Exception:
        return "אין עדיין כללים נוספים."

def save_contact_name(phone: str, name: str):
    clean_name = name.strip()
    norm_phone = normalize_phone(phone)
    if not clean_name or not norm_phone or clean_name in COMMON_NON_NAMES:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO contacts (phone, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
        """, (norm_phone, clean_name, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        sync_contacts_to_json()
    except Exception as exc:
        print(f"[Save Contact Notice]: {exc}")

def extract_name_from_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    patterns = [
        r"(?:שמי\s+הוא|שמי|קוראים\s+לי|השם\s+שלי\s+הוא|השם\s+שלי|מדבר|זה)\s+([א-ת]{2,15}(?:\s+[א-ת]{2,15})?)",
        r"^(?:אני)\s+([א-ת]{2,15}(?:\s+[א-ת]{2,15})?)",
        r"^([א-ת]{2,15}(?:\s+[א-ת]{2,15})?)\s*[:,\-]\s*",
        r"([א-ת]{2,15})\s+כאן\b"
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            candidate = match.group(1).strip()
            first_word = candidate.split()[0]
            if first_word not in COMMON_NON_NAMES:
                return first_word

    words = cleaned.split()
    if 1 <= len(words) <= 2:
        if all(re.fullmatch(r"[א-ת]{2,15}", w) for w in words):
            first_w = words[0]
            if first_w not in COMMON_NON_NAMES:
                return first_w

    return ""

def get_contact_name(phone: str) -> str:
    norm = normalize_phone(phone)
    if not norm:
        return ""
    if norm in PERMANENT_CONTACTS:
        return PERMANENT_CONTACTS[norm].split()[0]
    for p, n in PERMANENT_CONTACTS.items():
        clean_p = normalize_phone(p)
        if clean_p and len(clean_p) >= 9 and len(norm) >= 9:
            if clean_p[-9:] == norm[-9:]:
                return n.split()[0]

    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT name FROM contacts WHERE phone = ? OR phone LIKE ? LIMIT 1",
            (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
        ).fetchone()
        conn.close()
        if row and row[0] and row[0].strip() not in COMMON_NON_NAMES:
            return row[0].strip().split()[0]
    except Exception:
        pass

    return ""

def save_chat_message(phone: str, role: str, text: str):
    norm_phone = normalize_phone(phone)
    clean_text = text.strip()
    if not norm_phone or not clean_text:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO conversation_history (phone, role, message, created_at)
            VALUES (?, ?, ?, ?)
        """, (norm_phone, role, clean_text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_recent_chat_history(phone: str, limit: int = 6) -> str:
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        return ""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT role, message FROM conversation_history
            WHERE phone = ? OR phone LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (norm_phone, f"%{norm_phone[-9:]}%" if len(norm_phone) >= 9 else f"%{norm_phone}%", limit)).fetchall()
        conn.close()
        if not rows:
            return ""
        rows.reverse()
        lines = []
        for r, msg in rows:
            sender = "לקוח" if r == "customer" else "סוכן"
            lines.append(f"[{sender}]: {msg}")
        return "\n".join(lines)
    except Exception:
        return ""

def has_already_greeted_customer(phone: str) -> bool:
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("""
            SELECT COUNT(*) FROM conversation_history
            WHERE phone = ? AND role = 'agent'
        """, (norm_phone,)).fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False

def purge_unwanted_phrases(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"בודק(?:\s+זאת|\s+כעת)?\s+מול\s+המעבדה(?:\s+שלנו)?", "בודק כעת את המחיר העדכני", cleaned)
    cleaned = re.sub(r"מול\s+המעבדה(?:\s+שלנו)?", "את המחיר העדכני", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned

def apply_customer_name_guard(reply_text: str, customer_name: str, already_greeted: bool) -> str:
    cleaned = reply_text.strip()

    # Strip unwanted prompts asking for customer's name
    cleaned = re.sub(
        r"(?:ו?איך\s+קוראים\s+לך(?:\s+כדי\s+שאדע\s+למי\s+לפנות)?[\s?!.,]*|ו?מה\s+שמך(?:\s+בבקשה)?[\s?!.,]*|תגיד\s+מה\s+השם\s+שלך[\s?!.,]*|למי\s+לפנות[\s?!.,]*)",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    cleaned = purge_unwanted_phrases(cleaned)

    if not customer_name:
        return cleaned

    if already_greeted:
        # Strip redundant repeated greetings in ongoing conversation
        cleaned = re.sub(
            rf"^(?:שלום|היי|אהלן)\s+{re.escape(customer_name)}[\s,]+(?:מה\s+שלומך|מה\s+נשמע|שלומך)[\s?!.,]*",
            "",
            cleaned,
            flags=re.IGNORECASE
        ).strip()
        cleaned = re.sub(
            r"^(?:שלום|היי|אהלן)?[\s,]+(?:מה\s+שלומך|מה\s+נשמע)[\s?!.,]*",
            "",
            cleaned,
            flags=re.IGNORECASE
        ).strip()
    else:
        has_name = customer_name in cleaned
        has_how_are_you = any(p in cleaned for p in ["מה שלומך", "מה נשמע"])
        if not has_name or not has_how_are_you:
            salutation = f"שלום {customer_name}, מה שלומך?"
            # Cleanly replace leading greeting without duplicating customer name
            greeting_pattern = rf"^(?:שלום|היי|בוקר טוב|ערב טוב|אהלן)(?:\s+{re.escape(customer_name)})?[\s!.,]*"
            if re.match(greeting_pattern, cleaned):
                cleaned = re.sub(greeting_pattern, f"{salutation} ", cleaned, count=1)
            else:
                cleaned = f"{salutation} {cleaned}"

    return cleaned

# ----------------- Routes & Health Endpoints -----------------
@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def root_handler(request: Request):
    """Handles GET/HEAD health check, and POST webhooks if Green-API is configured to hit root /."""
    if request.method == "POST":
        return await unified_whatsapp_webhook(request)
    return health_check()

def health_check():
    return {
        "status": "online",
        "service": "ShieldBot AI WhatsApp Agent",
        "models": ACTIVE_MODELS,
        "db_path": DB_PATH,
        "has_gemini_key": bool(GEMINI_API_KEY),
        "has_whatsapp_url": bool(WHATSAPP_API_URL),
        "admin_phone": ADMIN_WHATSAPP_PHONE,
        "permanent_contacts_count": len(PERMANENT_CONTACTS)
    }

@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/contacts")
def list_contacts():
    db_map = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT phone, name, updated_at FROM contacts ORDER BY updated_at DESC").fetchall()
        conn.close()
        db_map = {r[0]: {"name": r[1], "source": "db", "updated_at": r[2]} for r in rows}
    except Exception:
        pass
    for p, n in PERMANENT_CONTACTS.items():
        norm_p = normalize_phone(p)
        if norm_p not in db_map:
            db_map[norm_p] = {"name": n, "source": "permanent_seed", "updated_at": "permanent"}
    return {"total": len(db_map), "contacts": db_map}

@app.post("/api/contacts/add")
async def add_contact_api(req: Request):
    try:
        body = await req.json()
        phone = normalize_phone(body.get("phone", ""))
        name = str(body.get("name", "")).strip()
        if not phone or not name:
            return {"ok": False, "error": "phone and name are required"}
        save_contact_name(phone, name)
        return {"ok": True, "phone": phone, "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/backup/export")
def export_backup():
    contacts_data = list_contacts().get("contacts", {})
    kb_data = []
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT id, keywords, answer, created_at FROM learned_kb").fetchall()
        conn.close()
        kb_data = [{"id": r[0], "keywords": r[1], "answer": r[2], "created_at": r[3]} for r in rows]
    except Exception:
        pass
    return {"contacts": contacts_data, "learned_kb": kb_data, "exported_at": datetime.now().isoformat()}

@app.get("/test_send")
def test_send(phone: str = "0524043644"):
    success = send_whatsapp_message(
        phone,
        "שלום! זוהי הודעת בדיקה משרת הסוכן ShieldBot AI. החיבור לווצאפ פעיל ומסונכרן בהצלחה! 🛡️"
    )
    return {
        "ok": success,
        "recipient": phone,
        "note": "הודעת בדיקה נשלחה."
    }

# ----------------- Automated Green-API Diagnostic & Manual Webhook Repair -----------------
@app.get("/api/green_api_status")
def green_api_status():
    """Queries Green-API directly to see current webhook settings and instance state without rebooting."""
    base, token = get_green_api_base_and_token()
    if not base or not token:
        return {"error": "WHATSAPP_API_URL is missing or invalid format"}

    results = {}
    try:
        resp = http_session.get(f"{base}/getSettings/{token}", timeout=8)
        results["settings"] = resp.json() if resp.status_code == 200 else resp.text
    except Exception as e:
        results["settings_error"] = str(e)

    try:
        resp2 = http_session.get(f"{base}/getStateInstance/{token}", timeout=8)
        results["stateInstance"] = resp2.json() if resp2.status_code == 200 else resp2.text
    except Exception as e:
        results["state_error"] = str(e)

    return results

@app.get("/api/fix_green_api_webhook")
def fix_green_api_webhook():
    """Manually forces Green-API via API to set the Render webhook URL (Note: Green-API takes ~2-5 mins to apply)."""
    base, token = get_green_api_base_and_token()
    if not base or not token:
        return {"error": "WHATSAPP_API_URL is missing or invalid format"}

    render_url = (RENDER_EXTERNAL_URL or "https://ns-whatsapp-agent-1.onrender.com").strip().rstrip("/")
    target_webhook = f"{render_url}/webhook/whatsapp"
    payload = {
        "webhookUrl": target_webhook,
        "webhookUrlToken": "",
        "incomingWebhook": "yes",
        "outgoingMessageWebhook": "no",
        "outgoingAPIMessageWebhook": "no",
        "stateWebhook": "no"
    }
    try:
        resp = http_session.post(f"{base}/setSettings/{token}", json=payload, timeout=8)
        return {
            "action": "setSettings",
            "sent_payload": payload,
            "status_code": resp.status_code,
            "green_api_response": resp.json() if resp.status_code == 200 else resp.text
        }
    except Exception as e:
        return {"error": str(e)}

# ----------------- Unified Multi-Route Webhook Handler -----------------
@app.api_route("/webhook/whatsapp", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/webhook/whatsapp/", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/webhook", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/webhook/", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/whatsapp", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/whatsapp/", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def webhook_direct(req: Request):
    if req.method in ["GET", "HEAD", "OPTIONS"]:
        return {"ok": True, "service": "ShieldBot AI Webhook Endpoint Active"}
    return await unified_whatsapp_webhook(req)

async def unified_whatsapp_webhook(req: Request):
    print(f"[HTTP Incoming] Received {req.method} to {req.url.path}")
    try:
        payload = await req.json()
    except Exception as e:
        print(f"[HTTP Incoming Error]: Cannot parse JSON: {e}")
        return JSONResponse(content={"ok": False, "error": "Invalid JSON"}, status_code=200)

    # 1. Unwrap if wrapped in {"receiptId": ..., "body": {...}}
    if isinstance(payload, dict) and "body" in payload and isinstance(payload["body"], dict):
        payload = payload["body"]

    # 2. Strictly process ONLY incomingMessageReceived when typeWebhook is present
    type_webhook = payload.get("typeWebhook", "")
    print(f"[Payload Received]: typeWebhook={type_webhook}")
    if type_webhook and type_webhook != "incomingMessageReceived":
        return {"ok": True, "note": f"Ignored non-incoming webhook: {type_webhook}"}

    # 3. Extract Sender Phone cleanly & ignore group chats or self-messages
    sender_data = payload.get("senderData", {}) if isinstance(payload.get("senderData"), dict) else {}
    message_data = payload.get("messageData", {}) if isinstance(payload.get("messageData"), dict) else {}
    instance_data = payload.get("instanceData", {}) if isinstance(payload.get("instanceData"), dict) else {}

    raw_chat_id = str(sender_data.get("chatId", "") or payload.get("chatId", ""))
    if raw_chat_id.endswith("@g.us"):
        print(f"[Ignored Group Message] chatId={raw_chat_id}")
        return {"ok": True, "note": "Ignored group chat message"}

    # Prefer a @c.us phone identifier if either sender or chatId has it
    raw_sender_field = str(sender_data.get("sender", "") or payload.get("sender", ""))
    if "@c.us" in raw_sender_field:
        raw_sender = raw_sender_field
    elif "@c.us" in raw_chat_id:
        raw_sender = raw_chat_id
    else:
        raw_sender = (
            raw_chat_id
            or raw_sender_field
            or str(payload.get("senderPhone", ""))
            or str(payload.get("from", ""))
        )

    clean_sender_raw = str(raw_sender).split("@")[0].split(":")[0]
    sender_phone = normalize_phone(clean_sender_raw)

    # Guard against bot replying to its own instance WID
    bot_own_phone = normalize_phone(str(instance_data.get("wid", "")))
    if bot_own_phone and sender_phone and bot_own_phone == sender_phone and raw_sender_field == str(instance_data.get("wid", "")):
        print(f"[Ignored Self Message] sender={sender_phone} matches instance wid={bot_own_phone}")
        return {"ok": True, "note": "Ignored self message"}

    # 4. Extract Message Text across all message types
    type_msg = message_data.get("typeMessage", "")
    message_text = ""
    if type_msg == "textMessage":
        message_text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif type_msg in ["extendedTextMessage", "quotedMessage"]:
        message_text = (
            message_data.get("extendedTextMessageData", {}).get("text", "")
            or message_data.get("quotedMessage", {}).get("textMessage", "")
            or message_data.get("quotedMessage", {}).get("text", "")
        )
    elif type_msg in ["imageMessage", "videoMessage", "documentMessage", "audioMessage"]:
        message_text = message_data.get("fileMessageData", {}).get("caption", "")
    elif type_msg == "buttonsResponseMessage":
        message_text = (
            message_data.get("buttonsResponseMessage", {}).get("selectedDisplayText", "")
            or message_data.get("buttonsResponseMessage", {}).get("selectedButtonId", "")
        )
    elif type_msg == "templateButtonsReplyMessage":
        message_text = (
            message_data.get("templateButtonReplyMessage", {}).get("selectedDisplayText", "")
            or message_data.get("templateButtonReplyMessage", {}).get("selectedId", "")
        )
    elif type_msg == "listResponseMessage":
        message_text = (
            message_data.get("listResponseMessage", {}).get("title", "")
            or message_data.get("listResponseMessage", {}).get("singleSelectReply", {}).get("selectedRowId", "")
        )

    if not message_text:
        message_text = (
            message_data.get("textMessageData", {}).get("textMessage", "")
            or message_data.get("extendedTextMessageData", {}).get("text", "")
            or payload.get("text", "")
            or payload.get("message", "")
        )
    message_text = (message_text or "").strip()

    if not sender_phone or not message_text:
        print(f"[Ignored] Non-message webhook event: sender={sender_phone}, typeMessage={type_msg}")
        return {"ok": True, "note": "Ignored non-text or system event"}

    print(f"[Incoming WhatsApp] From {sender_phone}: {message_text}")

    # Recognize both of Eran's numbers as authorized admin numbers
    admin_numbers_set = {
        normalize_phone(ADMIN_WHATSAPP_PHONE),
        "972553164770",
        "972524043644"
    }

    # 0. ADMIN LEARNING INTERCEPTOR: When Admin replies directly in WhatsApp to teach the bot
    if sender_phone in admin_numbers_set and ("תשובה:" in message_text or "תשובה " in message_text):
        parts = message_text.replace("תשובה:", "תשובה ").split("|")
        admin_answer = parts[0].replace("תשובה", "").strip()
        keywords = parts[1].replace("מילות מפתח:", "").replace("מילות מפתח", "").strip() if len(parts) > 1 else admin_answer[:25]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO learned_kb (keywords, answer, created_at) VALUES (?, ?, ?)",
                (keywords, admin_answer, datetime.now().isoformat())
            )
            last_pending = conn.execute(
                "SELECT id, phone, request_text FROM customer_requests WHERE status='pending' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            customer_dest = "אין לקוח ממתין (נשמר ישירות למאגר)"
            if last_pending:
                conn.execute(
                    "UPDATE customer_requests SET status='handled', action_taken=? WHERE id=?",
                    ("נענה על ידי מנהל ונלמד במאגר", last_pending[0])
                )
                target_cust_phone = last_pending[1]
                cust_reply_msg = "שלום, חזרתי אליך עם תשובה מהמעבדה / מנהל השירות שלנו:\n" + str(admin_answer)
                send_whatsapp_message(target_cust_phone, cust_reply_msg)
                save_chat_message(target_cust_phone, "agent", cust_reply_msg)
                customer_dest = target_cust_phone
            conn.commit()
            conn.close()
            confirm_msg = f"✅ התשובה נשמרה במאגר הידע של הסוכן ונשלחה ללקוח ({customer_dest})!"
            send_whatsapp_message(sender_phone, confirm_msg, raw_chat_id)
            return {"ok": True, "admin_action": "knowledge_saved", "customer": customer_dest}
        except Exception as exc:
            print(f"[Admin Learning Error]: {exc}")
            send_whatsapp_message(sender_phone, f"⚠️ שגיאה בשמירת התשובה: {exc}", raw_chat_id)
            return {"ok": False, "error": str(exc)}

    customer_name = get_contact_name(sender_phone)
    extracted_name = extract_name_from_text(message_text)
    if extracted_name:
        customer_name = extracted_name
        save_contact_name(sender_phone, extracted_name)

    already_greeted = has_already_greeted_customer(sender_phone)
    recent_history = get_recent_chat_history(sender_phone, limit=6)

    # 1. FAST DETERMINISTIC PATH: Pure Greetings (Send WhatsApp FIRST, then save to DB)
    if is_pure_greeting(message_text):
        if not customer_name:
            greeting_reply = "שלום , על מנת לתת לך את המענה המדויק והמהיר ביותר אשמח שתרשום לי את שמך ובמה אוכל לעזור לך היום ."
        elif already_greeted:
            greeting_reply = f"שלום {customer_name}, במה אוכל לעזור לך היום? 😃"
        else:
            greeting_reply = f"שלום {customer_name}, מה שלומך? במה אוכל לעזור לך היום? 😃"

        send_whatsapp_message(sender_phone, greeting_reply, raw_chat_id)
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", greeting_reply)
        return {"ok": True, "reply": greeting_reply, "type": "greeting_reply"}

    # 2. FAST DETERMINISTIC PATH: Store Address & Hours (Send WhatsApp FIRST, then save to DB)
    if is_store_info_question(message_text):
        store_reply = get_store_info_reply(customer_name)
        send_whatsapp_message(sender_phone, store_reply, raw_chat_id)
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", store_reply)
        return {"ok": True, "reply": store_reply, "type": "store_info"}

    # 3. FAST DETERMINISTIC PATH: Warranty Confirmation / Inquiry (Send WhatsApp FIRST, then save to DB)
    if is_warranty_followup_confirmation(message_text, recent_history):
        name_prefix = f"{customer_name}, " if customer_name else ""
        warranty_reply = f"{name_prefix}{WARRANTY_FULL_EXPLANATION}"
        send_whatsapp_message(sender_phone, warranty_reply, raw_chat_id)
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", warranty_reply)
        return {"ok": True, "reply": warranty_reply, "type": "warranty_full_explanation"}

    # 4. LLM Generation (Strictly ONLY 3.8 & 3.5 Flash models with full token headroom)
    reply_text = None
    used_model = None
    sub_info = lookup_subscriber(sender_phone, message_text)

    if client:
        if sub_info.get("found") and not customer_name:
            customer_name = sub_info["name"].split()[0]

        name_instruction = f"הלקוח מוכר ושמו הפרטי הוא: '{customer_name}'." if customer_name else "אינך יודע עדיין את שמו של הלקוח."
        if sub_info.get("found"):
            subscriber_context = (
                f"פרטי מנוי מאומת: שם מלא '{sub_info['name']}', מערכת '{sub_info['system']}', "
                f"סטטוס '{sub_info['status']}', מסלול/רמה: '{sub_info['level']}', מזהה מכשיר: '{sub_info['deviceId']}', "
                f"אתרים פתוחים: '{sub_info['whitelist']}', תוקף: '{sub_info['renewalDate']}'."
            )
        else:
            subscriber_context = "הלקוח אינו מופיע ברשימת מנויי נטספרק או כשר פליי הקיימים במערכת."
        learned_rules = get_learned_knowledge()

        system_instruction = f"""
אתה איש שירות ומעבדה אנושי, חם, מקצועי וענייני בווצאפ ("ShieldBot AI").
כללי יסוד קריטיים:
==================================================
1. סגנון ומהירות:
   • מענה קצר, ענייני ומעשי: 1 עד 3 שורות ברורות ומלאות! לעולם אל תעצור באמצע משפט!
   • {name_instruction}
   • כל המחירים בשקלים חדשים (₪) בלבד.

2. איסור מוחלט על אמירת "מול המעבדה":
   • לעולם אל תגיד ללקוח "אני בודק מול המעבדה" או "בודק זאת מול המעבדה שלנו"!
   • במקום זאת אמור תמיד: "אני בודק כעת את המחיר העדכני וכבר חוזר אליך עם תשובה מדויקת" או "אני בודק כעת את הזמינות והמחיר העדכני".

3. רכישת מכשירים ומסלולי אחריות בנעם שיח (כלל 2 השלבים):
   • כאשר לקוח שואל על רכישת מכשיר או מחיר מכשיר חדש:
     הצג לו את המחיר בשתי אפשרויות אחריות:
     - אחריות יבואן ארצי (מסלול גלות)
     - אחריות מלאה אצלנו במעבדה (מסלול ימות המשיח ⭐)
     ושאל אותו בסוף ההודעה:
     "האם תרצה פירוט מורחב של ההבדלים המלאים בין מסלולי האחריות? 😃"

4. מעבדת תיקונים ומסכים ובדיקת זמינות מכשירים:
   • אנו מתקנים ומחליפים מסכים לכל המכשירים: מכשירי מקשים (שיאומי מקשים / Qin / F21 / F22) וסמארטפונים.
   • אם המחיר או הזמינות של דגם מכשיר/חלק אינם ידועים לך בוודאות:
     אמור תמיד שאתה בודק כעת את הזמינות והמחיר העדכני ומיד חוזר אליו עם תשובה מדויקת (לעולם אל תגיד שתבדוק מחר!).
     וצרף בסוף ההודעה: [ESCALATE: מחיר וזמינות עבור {message_text} ללקוח {customer_name or sender_phone}]

5. כתובת ושעות פעילות:
   • רחוב ישעיהו 10, חדרה בלבד (ימים א'-ה' 12:00-20:00, ימי ו' שעון קיץ 12:00-15:30 / חורף 10:30-13:30).

6. מסלולי סינון והגנה (כשר פליי ונטספרק):
   • כשר פליי (KosherPlay):
     - בסיסי: 250 ₪ חד-פעמי (ללא דפדפן, כ-200 אפליקציות כשרות חיוניות: בנקים, קופות חולים, Waze, וואטסאפ). הרישיון פעיל על המכשיר בלבד (בהחלפת מכשיר יש לרכוש רישיון חדש).
     - מורחב: 180 ₪ התקנה חד-פעמי + רישיון 200 ₪ לשנה (או 300 ₪ לשנה כולל דפדפן מסונן). כ-20,000 אפליקציות כשרות ומוגנות + יוטיוב כשר, ספוטיפי כשר, ווצאפ כשר. הרישיון נייד ועובר בחינם למכשיר חדש (משלמים רק 180 ₪ התקנה)!
   • נטספרק (NetSpark):
     - 350 ₪ לשנה (רישיון שנתי).
     - שינוי רמות סינון מיידי בווצאפ (רחבה/שמרני, מתקדמת, בסיסית, מותאמת אישית).

7. מצב מנוי הלקוח הנוכחי:
   {subscriber_context}

8. כללים שנלמדו:
   {learned_rules}
"""
        gen_config = build_fast_gen_config(system_instruction)
        prompt_content = f"היסטוריית שיחה:\n{recent_history}\n\nהודעת לקוח: {message_text}" if recent_history else f"לקוח {sender_phone}: {message_text}"

        for model_candidate in ACTIVE_MODELS:
            try:
                # Run with 12s timeout at application layer (Google API deadline is standard >=10s)
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_candidate,
                        contents=prompt_content,
                        config=gen_config
                    ),
                    timeout=12.0
                )
                if response and response.text:
                    reply_text = response.text.strip()
                    used_model = model_candidate
                    break
            except Exception as exc:
                print(f"[Gemini Error on {model_candidate}]: {exc}")

    # Fallback if AI is unreachable
    if not reply_text:
        reply_text = "אני בודק כעת את הזמינות והמחיר העדכני, ומיד חוזר אליך עם תשובה מדויקת. 😃"

    # Comprehensive Escalation Detection:
    # 1. Explicit tag from AI
    is_escalated = False
    escalation_question = message_text
    if "[ESCALATE:" in reply_text:
        match = re.search(r"\[ESCALATE:\s*([^\]]+)\]", reply_text)
        if match:
            escalation_question = match.group(1).strip()
        reply_text = re.sub(r"\[ESCALATE:\s*[^\]]+\]", "", reply_text).strip()
        is_escalated = True

    # 2. Any checking / followup keywords in reply text
    checking_markers = [
        "בודק", "אבדוק", "נבדוק", "יבדוק", "תבדוק", "בדיקה",
        "אברר", "נברר", "בירור", "לברר",
        "אחזור", "נחזור", "חוזר",
        "אעדכן", "נעדכן", "מעדכן",
        "תשובה מדויקת", "מחיר עדכני", "המחיר העדכני", "זמינות",
        "במלאי", "מחר"
    ]
    if any(marker in reply_text for marker in checking_markers):
        is_escalated = True

    # 3. Any device / model / availability / repair pricing question from customer
    q_clean = message_text.lower()
    product_inquiry_markers = [
        "יש לכם", "כמה עולה", "מחיר", "עלות", "זמין", "במלאי", "מכשיר",
        "מסך", "תיקון", "החלפה", "f25", "pro", "שיאומי", "סמסונג", "אייפון"
    ]
    if any(p in q_clean for p in product_inquiry_markers):
        is_escalated = True

    # Guard and clean salutations/name
    if customer_name:
        reply_text = apply_customer_name_guard(reply_text, customer_name, already_greeted)
    else:
        reply_text = purge_unwanted_phrases(reply_text)

    # CRITICAL: Ensure reply_text is never empty or a truncated fragment
    if not reply_text or len(reply_text.strip()) < 8:
        if customer_name:
            reply_text = f"שלום {customer_name}, אני בודק כעת את הזמינות והמחיר העדכני ומיד חוזר אליך עם תשובה מדויקת. 😃"
        else:
            reply_text = "שלום! אני בודק כעת את הזמינות והמחיר העדכני ומיד חוזר אליך עם תשובה מדויקת. 😃"

    # SEND WHATSAPP MESSAGE TO CUSTOMER FIRST FOR MAXIMUM SPEED!
    send_whatsapp_message(sender_phone, reply_text, raw_chat_id)

    # Save to history & requests after customer already received the reply
    save_chat_message(sender_phone, "customer", message_text)
    save_chat_message(sender_phone, "agent", reply_text)
    try:
        status = "pending" if is_escalated else "handled"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO customer_requests (phone, system_name, request_text, action_taken, upsell_offer, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sender_phone,
                sub_info.get("system", "מעבדה/שירות"),
                message_text,
                "הועבר למנהל" if is_escalated else f"מענה אוטונומי ({used_model})",
                "",
                status,
                datetime.now().isoformat()
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Save Request Notice]: {e}")

    # ESCALATE TO ADMIN: Send question to Admin WhatsApp so they can answer and teach the bot!
    if is_escalated:
        try:
            # Smart admin recipient determination:
            # If the message sender is one of Eran's admin phones (testing mode), send directly to THAT phone!
            # If from an external customer, send to all registered admin numbers so Eran sees it on whichever phone he holds!
            if sender_phone in admin_numbers_set:
                target_admins = [sender_phone]
            else:
                target_admins = list(admin_numbers_set)

            customer_label = f"{customer_name} ({sender_phone})" if customer_name else sender_phone
            admin_notification = (
                f"❓ *שאלה מלקוח שדורשת את תשובתך* ({customer_label}):\n\"{escalation_question}\"\n\n"
                f"השב להודעה זו כדי לענות ללקוח וללמד את הבוט:\n"
                f"תשובה: [התשובה ללקוח] | מילות מפתח: [מילות זיהוי]"
            )
            
            # Small pause before admin send so Green-API never drops consecutive messages to the same chat
            await asyncio.sleep(1.0)
            for adm in target_admins:
                if adm and adm != "972500000000":
                    print(f"[Admin Escalation] Sending question to Admin ({adm}): {escalation_question}")
                    send_whatsapp_message(adm, admin_notification)
        except Exception as e_adm:
            print(f"[Admin Escalation Notice]: {e_adm}")

    return {"ok": True, "reply": reply_text, "escalated": is_escalated, "model": used_model}

# Catch-all for any incoming POST to any sub-path (to never miss a webhook)
@app.post("/{full_path:path}")
async def catch_all_post(request: Request, full_path: str):
    print(f"[Catch-All POST] Received at: /{full_path}")
    return await unified_whatsapp_webhook(request)
