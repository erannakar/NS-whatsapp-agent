"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini 2.5 Flash / 3.8 Flash (ultra-fast sub-second responses)
Integrations: Green-API / Meta WhatsApp Webhook, NetSpark & KosherPlay Filtering, Lab & Repair Services
Persistent Memory & Sync: Permanent Code Seed, Local JSON Cache, SQLite with Render Persistent Disk Support
Keep-Alive: Built-in background ping loop to prevent Render cold starts!
"""

import os
import json
import sqlite3
import re
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
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
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000").strip().strip('"').strip("'")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().strip('"').strip("'")
NETSPARK_API_TOKEN = os.getenv("NETSPARK_API_TOKEN", "").strip()
KOSHERPLAY_API_TOKEN = os.getenv("KOSHERPLAY_API_TOKEN", "").strip()

# ----------------- Gemini Client Setup -----------------
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Active models: gemini-2.5-flash (primary, ultra-fast) with gemini-2.0-flash / gemini-3.8-flash
ACTIVE_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.8-flash"]

# ----------------- Database & Persistent Storage Setup -----------------
DB_PATH = os.getenv("DB_PATH", "")
if not DB_PATH:
    for disk_candidate in ["/var/data", "/data", "/opt/render/project/src/data"]:
        if os.path.exists(disk_candidate) and os.path.isdir(disk_candidate):
            DB_PATH = os.path.join(disk_candidate, "agent_memory.db")
            break
    if not DB_PATH:
        DB_PATH = "agent_memory.db"

BACKUP_JSON_PATH = os.path.join(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", "contacts_cache.json")

# Shared HTTP connection pool to avoid SSL handshake overhead
http_session = httpx.Client(timeout=10)

# ----------------- Keep-Alive Background Task (Render Cold-Start Preventer) -----------------
async def keep_alive_loop():
    """Pings the server itself every 9 minutes so Render free tier never sleeps."""
    target_url = RENDER_EXTERNAL_URL or "http://127.0.0.1:8000"
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"
    ping_url = f"{target_url.rstrip('/')}/healthz"
    
    # Wait 60 seconds after startup before first ping
    await asyncio.sleep(60)
    async with httpx.AsyncClient(timeout=10) as aclient:
        while True:
            try:
                resp = await aclient.get(ping_url)
                print(f"[Keep-Alive] Pinged {ping_url} - Status: {resp.status_code}")
            except Exception as e:
                print(f"[Keep-Alive] Ping error: {e}")
            # Ping every 9 minutes (540 seconds) — Render sleeps after 15 mins
            await asyncio.sleep(540)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch background keep-alive ping loop
    task = asyncio.create_task(keep_alive_loop())
    yield
    # Shutdown: Cancel task
    task.cancel()

app = FastAPI(title="ShieldBot AI - WhatsApp Agent", lifespan=lifespan)

# ----------------- Phone Normalization -----------------
def normalize_phone(phone: str) -> str:
    """Normalizes Israeli and international phone numbers into a single canonical digit string."""
    digits = re.sub(r"[^0-9]", "", phone or "")
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
    """Returns True if the message contains only greetings without an inquiry."""
    clean = re.sub(r"[^\w\sא-תa-zA-Z]", " ", text or "").strip().lower()
    words = clean.split()
    if not words:
        return False
    greeting_stems = {
        "שלום", "היי", "הי", "אהלן", "בוקר", "ערב", "צהריים", "לילה", "טוב", "טובה",
        "טובים", "שלוםם", "היוש", "הייוש", "הלו", "hello", "hi", "hey", "ברכה", "נעים"
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
    """Returns True if the customer is asking about store address, location, or opening hours."""
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
    """Detects if customer is replying 'yes' or asking for the warranty comparison after being offered it."""
    clean = text.strip().lower()
    positive_signals = [
        "כן", "אשמח", "תפרט", "פרט", "מה ההבדל", "מה ההבדלים", "מעוניין", "תשלח",
        "תסביר", "רוצה לדעת", "אשמח לפירוט", "כן אשמח", "תשלח לי", "בטח", "ודאי"
    ]
    # Check if history contained the prompt about warranty tracks
    had_warranty_offer = "ההבדלים המלאים בין מסלולי האחריות" in history_text or "מסלול ימות המשיח" in history_text
    is_positive = any(clean == sig or clean.startswith(sig) for sig in positive_signals)
    return (had_warranty_offer and is_positive) or any(phrase in clean for phrase in ["מה ההבדל בין האחריות", "הבדל בין המסלולים", "פירוט מסלולי אחריות", "מסלול גלות", "ימות המשיח"])

# ----------------- Database Initialization -----------------
def init_db():
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
        INSERT OR IGNORE INTO learned_kb (keywords, answer, created_at)
        VALUES ('כתובת, מיקום, שעות פעילות, שעות פתיחה, איפה אתם, ישעיהו 10, חדרה',
        'החנות והמעבדה שלנו נמצאות ברחוב ישעיהו 10 בחדרה. שעות פעילות: ימים א-ה 12:00-20:00. ימי ו׳ וערבי חג: שעון קיץ 12:00-15:30, שעון חורף 10:30-13:30. מוצאי שבת וחג בתיאום מראש בלבד.',
        datetime('now'))
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
    for p, n in PERMANENT_CONTACTS.items():
        norm_p = normalize_phone(p)
        c.execute("""
            INSERT OR IGNORE INTO contacts (phone, name, created_at, updated_at)
            VALUES (?, ?, datetime('now'), datetime('now'))
        """, (norm_p, n))

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
        CREATE TABLE IF NOT EXISTS pos_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_name TEXT,
            model_keywords TEXT,
            price_nis INTEGER,
            in_stock INTEGER,
            updated_at TEXT
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
    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"[Init DB Error]: {e}")

# ----------------- Helper Functions -----------------
def send_whatsapp_message(phone: str, text: str) -> bool:
    """Sends outgoing message via Green-API or compatible WhatsApp Gateway."""
    clean_phone = normalize_phone(phone)
    if not clean_phone or not WHATSAPP_API_URL:
        print(f"[WhatsApp DryRun] To {clean_phone}: {text}")
        return False
    
    clean_url = WHATSAPP_API_URL.strip().rstrip("/")
    payload = {
        "chatId": f"{clean_phone}@c.us",
        "message": text
    }
    try:
        resp = http_session.post(clean_url, json=payload)
        print(f"[WhatsApp Sent] To: {clean_phone}, Status: {resp.status_code}")
        return resp.status_code == 200
    except Exception as exc:
        print(f"[WhatsApp Send Error]: {exc}")
        return False

def get_learned_knowledge() -> str:
    """Fetches custom knowledge rules taught by the admin."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT keywords, answer FROM learned_kb").fetchall()
    conn.close()
    if not rows:
        return "אין עדיין כללים נוספים."
    return "\n".join([f"- מילות זיהוי ({r[0]}): תשובה שנלמדה בעבר: {r[1]}" for r in rows])

def lookup_subscriber(phone: str) -> dict:
    """Checks subscriber status in NetSpark & KosherPlay databases."""
    norm = normalize_phone(phone)
    if not norm:
        return {"found": False}
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name, system_name, status, current_level, device_id, whitelist, renewal_date "
        "FROM subscribers WHERE phone = ? OR phone LIKE ? LIMIT 1",
        (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
    ).fetchone()
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
            "renewalDate": row[6]
        }
    return {"found": False}

def sync_contacts_to_cache():
    """Writes all contacts to JSON cache file on disk for backup."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT phone, name FROM contacts").fetchall()
        conn.close()
        cache = {r[0]: r[1] for r in rows}
        cache.update({normalize_phone(p): n for p, n in PERMANENT_CONTACTS.items()})
        with open(BACKUP_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[Sync Cache Error]: {exc}")

def save_contact_name(phone: str, name: str):
    """Saves customer name in contacts memory."""
    clean_name = name.strip()
    norm_phone = normalize_phone(phone)
    if not clean_name or not norm_phone or clean_name in COMMON_NON_NAMES:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO contacts (phone, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(phone) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
    """, (norm_phone, clean_name, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    sync_contacts_to_cache()

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
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name FROM contacts WHERE phone = ? OR phone LIKE ? LIMIT 1",
        (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
    ).fetchone()
    if row and row[0] and row[0].strip() not in COMMON_NON_NAMES:
        conn.close()
        return row[0].strip().split()[0]
    
    sub_row = conn.execute(
        "SELECT name FROM subscribers WHERE phone = ? OR phone LIKE ? LIMIT 1",
        (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
    ).fetchone()
    if sub_row and sub_row[0]:
        first_only = sub_row[0].strip().split()[0]
        conn.close()
        save_contact_name(norm, first_only)
        return first_only

    conn.close()
    return ""

def save_chat_message(phone: str, role: str, text: str):
    norm_phone = normalize_phone(phone)
    clean_text = text.strip()
    if not norm_phone or not clean_text:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO conversation_history (phone, role, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (norm_phone, role, clean_text, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_chat_history(phone: str, limit: int = 6) -> str:
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        return ""
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

def has_already_greeted_customer(phone: str) -> bool:
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        return False
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("""
        SELECT COUNT(*) FROM conversation_history
        WHERE phone = ? AND role = 'agent'
    """, (norm_phone,)).fetchone()[0]
    conn.close()
    return count > 0

def purge_unwanted_phrases(text: str) -> str:
    """Strictly purges any occurrence of 'מול המעבדה' or 'מול המעבדה שלנו' and replaces with 'את המחיר העדכני'."""
    cleaned = text
    cleaned = re.sub(r"בודק(?:\s+זאת|\s+כעת)?\s+מול\s+המעבדה(?:\s+שלנו)?", "בודק כעת את המחיר העדכני", cleaned)
    cleaned = re.sub(r"מול\s+המעבדה(?:\s+שלנו)?", "את המחיר העדכני", cleaned)
    # Ensure double spaces cleaned
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned

def apply_customer_name_guard(reply_text: str, customer_name: str, already_greeted: bool) -> str:
    cleaned = reply_text.strip()
    
    # 1. Purge accidental name-asking questions
    cleaned = re.sub(
        r"(?:ו?איך\s+קוראים\s+לך(?:\s+כדי\s+שאדע\s+למי\s+לפנות)?[\s?!.,]*|ו?מה\s+שמך(?:\s+בבקשה)?[\s?!.,]*|תגיד\s+מה\s+השם\s+שלך[\s?!.,]*|למי\s+לפנות[\s?!.,]*)",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # 2. Strict purge of 'מול המעבדה'
    cleaned = purge_unwanted_phrases(cleaned)

    if not customer_name:
        return cleaned

    if already_greeted:
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
            if re.match(r"^(?:שלום|היי|בוקר טוב|ערב טוב|אהלן)[\s!.,]*", cleaned):
                cleaned = re.sub(r"^(?:שלום|היי|בוקר טוב|ערב טוב|אהלן)[\s!.,]*", f"{salutation} ", cleaned, count=1)
            else:
                cleaned = f"{salutation} {cleaned}"
                
    return cleaned

# ----------------- Routes & Backup Endpoints -----------------
@app.api_route("/", methods=["GET", "HEAD"])
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
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT phone, name, updated_at FROM contacts ORDER BY updated_at DESC").fetchall()
    conn.close()
    db_map = {r[0]: {"name": r[1], "source": "db", "updated_at": r[2]} for r in rows}
    for p, n in PERMANENT_CONTACTS.items():
        norm_p = normalize_phone(p)
        if norm_p not in db_map:
            db_map[norm_p] = {"name": n, "source": "permanent_seed", "updated_at": "permanent"}
    return {"total": len(db_map), "contacts": db_map}

@app.get("/test_send")
def test_send(phone: str = "0553164770"):
    success = send_whatsapp_message(
        phone,
        "שלום! זוהי הודעת בדיקה משרת הסוכן ShieldBot AI. החיבור לווצאפ פעיל ומסונכרן בהצלחה! 🛡️"
    )
    return {
        "ok": success,
        "recipient": phone,
        "note": "הודעת בדיקה נשלחה בהצלחה."
    }

# ----------------- Main Webhook -----------------
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    sender_data = payload.get("senderData", {})
    raw_sender = (
        sender_data.get("chatId", "").replace("@c.us", "").replace("@s.whatsapp.net", "").strip()
        or payload.get("senderPhone", "")
    )
    sender_phone = normalize_phone(raw_sender)
    
    message_data = payload.get("messageData", {})
    type_msg = message_data.get("typeMessage", "")
    message_text = ""
    if type_msg == "textMessage":
        message_text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif type_msg == "extendedTextMessage":
        message_text = message_data.get("extendedTextMessageData", {}).get("text", "")
    
    if not message_text:
        message_text = (
            message_data.get("textMessageData", {}).get("textMessage", "")
            or payload.get("text", "")
        )

    if not sender_phone or not message_text:
        return {"ok": True, "note": "Ignored non-text or system event"}

    print(f"[Incoming WhatsApp] From {sender_phone}: {message_text}")

    clean_admin = normalize_phone(ADMIN_WHATSAPP_PHONE)
    customer_name = get_contact_name(sender_phone)
    extracted_name = extract_name_from_text(message_text)
    if extracted_name:
        customer_name = extracted_name
        save_contact_name(sender_phone, extracted_name)

    already_greeted = has_already_greeted_customer(sender_phone)
    recent_history = get_recent_chat_history(sender_phone, limit=6)

    # 1. FAST DETERMINISTIC PATH: Pure Greetings
    if not customer_name and not already_greeted and is_pure_greeting(message_text):
        greeting_prompt_reply = "שלום , על מנת לתת לך את המענה המדויק והמהיר ביותר אשמח שתרשום לי את שמך ובמה אוכל לעזור לך היום ."
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", greeting_prompt_reply)
        send_whatsapp_message(sender_phone, greeting_prompt_reply)
        return {"ok": True, "reply": greeting_prompt_reply, "type": "initial_greeting_prompt"}

    # 2. FAST DETERMINISTIC PATH: Store Address & Hours
    if is_store_info_question(message_text):
        store_reply = get_store_info_reply(customer_name)
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", store_reply)
        send_whatsapp_message(sender_phone, store_reply)
        return {"ok": True, "reply": store_reply, "type": "store_info"}

    # 3. FAST DETERMINISTIC PATH: Warranty Confirmation / Inquiry (Step 2)
    if is_warranty_followup_confirmation(message_text, recent_history):
        name_prefix = f"{customer_name}, " if customer_name else ""
        warranty_reply = f"{name_prefix}{WARRANTY_FULL_EXPLANATION}"
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", warranty_reply)
        send_whatsapp_message(sender_phone, warranty_reply)
        return {"ok": True, "reply": warranty_reply, "type": "warranty_full_explanation"}

    # 4. LLM Generation
    reply_text = None
    used_model = None

    if client:
        name_instruction = f"הלקוח מוכר ושמו הפרטי הוא: '{customer_name}'." if customer_name else "אינך יודע עדיין את שמו של הלקוח."
        learned_rules = get_learned_knowledge()

        system_instruction = f"""
אתה איש שירות ומעבדה אנושי, חם, מקצועי וענייני בווצאפ ("ShieldBot AI").
כללי יסוד קריטיים:
==================================================
1. סגנון ומהירות:
   • מענה קצר, ענייני ומעשי: 1 עד 3 שורות ברורות בלבד!
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

4. מעבדת תיקונים ומסכים:
   • אנו מתקנים ומחליפים מסכים לכל המכשירים: מכשירי מקשים (שיאומי מקשים / Qin / F21 / F22) וסמארטפונים.
   • אם המחיר אינו ידוע לך: אמור שאתה בודק כעת את המחיר העדכני ומיד חוזר אליו.
     וצרף בסוף: [ESCALATE: מחיר וזמינות עבור [חלק/דגם] ללקוח {customer_name or sender_phone}]

5. כתובת ושעות פעילות:
   • רחוב ישעיהו 10, חדרה בלבד (ימים א'-ה' 12:00-20:00, ימי ו' שעון קיץ 12:00-15:30 / חורף 10:30-13:30).

6. כללים שנלמדו:
   {learned_rules}
"""
        config_args = {
            "system_instruction": system_instruction,
            "temperature": 0.2,
            "max_output_tokens": 300,
        }
        gen_config = types.GenerateContentConfig(**config_args) if types else None

        prompt_content = f"היסטוריית שיחה:\n{recent_history}\n\nהודעת לקוח: {message_text}" if recent_history else f"לקוח {sender_phone}: {message_text}"

        for model_candidate in ACTIVE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=prompt_content,
                    config=gen_config
                )
                if response and response.text:
                    reply_text = response.text.strip()
                    used_model = model_candidate
                    break
            except Exception as exc:
                print(f"[Gemini Error on {model_candidate}]: {exc}")

    # Fallback
    if not reply_text:
        cust_label = f" {customer_name}" if customer_name else ""
        reply_text = f"אני בודק כעת את המחיר העדכני{cust_label}, ומיד חוזר אליך עם תשובה מדויקת."

    # Guard and purge
    if customer_name:
        reply_text = apply_customer_name_guard(reply_text, customer_name, already_greeted)
    else:
        reply_text = purge_unwanted_phrases(reply_text)

    # Escalation
    is_escalated = False
    escalation_question = message_text
    if "[ESCALATE:" in reply_text:
        match = re.search(r"\[ESCALATE:\s*([^\]]+)\]", reply_text)
        if match:
            escalation_question = match.group(1).strip()
        reply_text = re.sub(r"\[ESCALATE:\s*[^\]]+\]", "", reply_text).strip()
        is_escalated = True

    # Save to history & requests
    status = "pending" if is_escalated else "handled"
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO customer_requests (phone, system_name, request_text, action_taken, upsell_offer, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sender_phone, "מעבדה/שירות", message_text, "הועבר למנהל" if is_escalated else f"מענה אוטונומי ({used_model})", "", status, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    # Escalate to admin
    if is_escalated and clean_admin and sender_phone != clean_admin:
        customer_label = f"{customer_name} ({sender_phone})" if customer_name else sender_phone
        admin_notification = (
            f"❓ *שאלה מלקוח שדורשת את תשובתך* ({customer_label}):\n"
            f"\"{escalation_question}\"\n\n"
            f"השב להודעה זו כדי לענות ללקוח וללמד את הבוט:\n"
            f"תשובה: [התשובה ללקוח] | מילות מפתח: [מילות זיהוי]"
        )
        send_whatsapp_message(clean_admin, admin_notification)

    save_chat_message(sender_phone, "customer", message_text)
    save_chat_message(sender_phone, "agent", reply_text)
    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "escalated": is_escalated, "model": used_model}
