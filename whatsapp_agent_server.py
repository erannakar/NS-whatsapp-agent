"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini 3.8 Flash (primary) & Gemini 3.5 Flash Lite (fallback)
Integrations: Green-API / Meta WhatsApp Webhook, NetSpark & KosherPlay Filtering, Lab & Repair Services
"""

import os
import sqlite3
import re
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

app = FastAPI(title="ShieldBot AI - WhatsApp Agent")

# ----------------- Environment Variables -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip().strip('"').strip("'")
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000").strip().strip('"').strip("'")
NETSPARK_API_TOKEN = os.getenv("NETSPARK_API_TOKEN", "").strip()
KOSHERPLAY_API_TOKEN = os.getenv("KOSHERPLAY_API_TOKEN", "").strip()

# ----------------- Gemini Client Setup -----------------
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Active models: gemini-3.8-flash (primary) with gemini-3.5-flash-lite (fast fallback)
ACTIVE_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

DB_PATH = os.getenv("DB_PATH", "agent_memory.db")

# Shared HTTP connection pool to avoid SSL handshake overhead on every WhatsApp message
http_session = httpx.Client(timeout=10)

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

# Common words that must NEVER be misidentified as a customer's first name
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
    """Returns True if the message contains only greetings (שלום, בוקר טוב, ערב טוב, etc.) without an inquiry."""
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

# ----------------- Database Initialization -----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Learned Knowledge from Admin
    c.execute("""
        CREATE TABLE IF NOT EXISTS learned_kb (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keywords TEXT,
            answer TEXT,
            created_at TEXT
        )
    """)
    # Seed A17 screen rule explicitly approved by Admin
    c.execute("""
        INSERT OR IGNORE INTO learned_kb (keywords, answer, created_at)
        VALUES ('a17, samsung a17, מסך סאני מקורי', 'עלות החלפת מסך מקורי ל-Samsung Galaxy A17 (סאני) כולל עבודה ואחריות היא 400 ₪.', datetime('now'))
    """)
    # Customer Requests Log
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
    # Contacts Memory: Remembers Customer Names Across Chats
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            phone TEXT PRIMARY KEY,
            name TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # Pre-seed owner/test contact so name is recognized from first interaction
    c.execute("""
        INSERT OR IGNORE INTO contacts (phone, name, created_at, updated_at)
        VALUES ('972524043644', 'ערן', datetime('now'), datetime('now'))
    """)
    # Conversation History Memory: Retains recent chat context per customer
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            role TEXT,
            message TEXT,
            created_at TEXT
        )
    """)
    # Live POS Inventory Table
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
    # Clean any old mock records with unconfirmed prices (e.g. F21 Pro 220 NIS)
    c.execute("DELETE FROM pos_inventory WHERE model_keywords LIKE '%f21%' OR model_keywords LIKE '%qin 1s%'")
    
    # Live Lab Queue Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS lab_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_model TEXT,
            issue TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    # Clean any mock lab tickets that caused fake "4 מכשירים בתיקון"
    c.execute("DELETE FROM lab_tickets WHERE device_model IN ('Samsung S23', 'Xiaomi Qin F21 Pro', 'iPhone 13', 'Samsung A14')")

    # Subscribers (NetSpark & KosherPlay)
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

init_db()

# ----------------- Helper Functions -----------------
def send_whatsapp_message(phone: str, text: str) -> bool:
    """Sends outgoing message via Green-API or compatible WhatsApp Gateway using connection pool."""
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

def save_contact_name(phone: str, name: str):
    """Saves or updates customer name in contacts memory using normalized phone."""
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

def extract_name_from_text(text: str) -> str:
    """Extracts customer first name if stated in message or when answering a name prompt."""
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
    """
    Retrieves remembered name from contacts memory, subscribers DB, or prior conversation history.
    """
    norm = normalize_phone(phone)
    if not norm:
        return ""
    
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Check contacts memory table
    row = conn.execute(
        "SELECT name FROM contacts WHERE phone = ? OR phone LIKE ? LIMIT 1",
        (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
    ).fetchone()
    if row and row[0] and row[0].strip() not in COMMON_NON_NAMES:
        conn.close()
        return row[0].strip()
    
    # 2. Check subscribers table
    sub_row = conn.execute(
        "SELECT name FROM subscribers WHERE phone = ? OR phone LIKE ? LIMIT 1",
        (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")
    ).fetchone()
    if sub_row and sub_row[0]:
        first_only = sub_row[0].strip().split()[0]
        conn.close()
        save_contact_name(norm, first_only)
        return first_only

    # 3. Check conversation_history for any past mention of name
    hist_rows = conn.execute("""
        SELECT role, message FROM conversation_history
        WHERE phone = ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 20
    """, (norm, f"%{norm[-9:]}%" if len(norm) >= 9 else f"%{norm}%")).fetchall()
    conn.close()

    for role, msg in hist_rows:
        if role == "customer":
            extracted = extract_name_from_text(msg)
            if extracted:
                save_contact_name(norm, extracted)
                return extracted
        elif role == "agent":
            m = re.search(r"(?:שלום|היי)\s+([א-ת]{2,15})[\s,!.]", msg)
            if m:
                cand = m.group(1).strip()
                if cand not in COMMON_NON_NAMES:
                    save_contact_name(norm, cand)
                    return cand

    return ""

def save_chat_message(phone: str, role: str, text: str):
    """Saves a conversation turn to SQLite for persistent chat memory."""
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
    """Retrieves recent conversation history to provide conversational context to the LLM."""
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
    """Checks if the agent has already sent messages to this customer in the current conversation."""
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

def parse_admin_reply(raw_text: str):
    """
    Sanitizes admin reply to strip out מילות מפתח so internal keywords NEVER leak to customer.
    Supports pipe |, newline, or inline keywords notation.
    """
    text = raw_text.strip()
    text = re.sub(r"^(?:תשובה\s*[:=]?\s*)", "", text, flags=re.IGNORECASE).strip()
    
    clean_answer = text
    keywords = ""
    
    if "|" in text:
        parts = text.split("|", 1)
        clean_answer = parts[0].strip()
        keywords = re.sub(r"^(?:מילות\s*מפתח|מילים\s*לזיהוי|תגיות)\s*[:=]?\s*", "", parts[1].strip())
    elif re.search(r"(?:מילות\s*מפתח|מילים\s*לזיהוי|מילות\s*זיהוי|תגיות)\s*[:=]?", text):
        parts = re.split(r"(?:מילות\s*מפתח|מילים\s*לזיהוי|מילות\s*זיהוי|תגיות)\s*[:=]?", text, 1)
        clean_answer = parts[0].strip()
        keywords = parts[1].strip() if len(parts) > 1 else ""
        
    clean_answer = re.sub(r"[\s\|]*(?:מילות\s*מפתח|מילים\s*לזיהוי|תגיות).*", "", clean_answer, flags=re.IGNORECASE | re.DOTALL).strip()
    
    if not keywords:
        keywords = clean_answer[:30]
        
    return clean_answer, keywords

def is_substantive_admin_question(customer_message: str) -> bool:
    """
    Returns True ONLY if the customer message is a real substantive question/request requiring admin assistance.
    Returns False for customer introductions ('תודה קוראים לי ערן'), greetings, thank-yous, affirmations,
    queue logistics ('לא רוצה לחכות בתור'), arrivals ('מעולה אני מגיע אליכם'), or known items.
    """
    clean = customer_message.strip()
    if not clean or len(clean) < 2:
        return False

    has_question_indicator = any(qw in clean for qw in [
        "כמה", "מחיר", "עלות", "האם יש", "יש לכם", "תקלה", "נשבר", "לתקן", "להחליף", "שקע", "סוללה", "?"
    ])

    # 1. Name statements or introductions without question words
    if extract_name_from_text(clean) and not has_question_indicator:
        return False

    # 2. Queue, waiting, arrival, greetings, thanks logistics -> handled autonomously by bot
    logistics_and_social = {
        "תודה", "רבה", "לך", "לכם", "שלום", "היי", "אהלן", "בוקר", "ערב", "צהריים",
        "טוב", "טובה", "טובים", "בסדר", "גמור", "אחלה", "יופי", "מעולה", "מצוין",
        "סבבה", "מאה", "אחוז", "להתראות", "ביי", "הבנתי", "יום",
        "שמי", "קוראים", "לי", "זה", "אני", "נעים", "להכיר", "שמח",
        "מעולה", "מגיע", "אליכם", "מחר", "היום", "עכשיו", "מחכה", "בדרך",
        "תור", "בתור", "לחכות", "להמתין", "הרבה", "זמן", "רוצה", "להקפיץ", "להשאיר", "לאסוף"
    }
    cleaned_no_punct = re.sub(r"[^\w\sא-ת]", "", clean).strip()
    words = cleaned_no_punct.split()
    if all(w in logistics_and_social or len(w) <= 2 for w in words):
        return False

    # 3. Check learned_kb - if already answered, don't escalate!
    conn = sqlite3.connect(DB_PATH)
    kb_rows = conn.execute("SELECT keywords FROM learned_kb").fetchall()
    conn.close()
    clean_low = clean.lower()
    for (kws,) in kb_rows:
        kw_list = [k.strip().lower() for k in kws.split(",") if k.strip()]
        if any(k in clean_low for k in kw_list if len(k) >= 3):
            return False

    return True

def apply_customer_name_guard(reply_text: str, customer_name: str, already_greeted: bool) -> str:
    """
    Conversational Natural Flow Guard:
    1. If customer_name is known:
       - FIRST message of chat: greets once warmly with 'שלום [שם], מה שלומך?'.
       - ONGOING chat (already_greeted is True): STRIPS repetitive 'מה שלומך' and formal 'שלום [שם], מה שלומך?'!
    2. Purges any accidental 'איך קוראים לך' questions for known customers.
    3. Purges any hallucinated machine count numbers (e.g. '4 מכשירים בתיקון').
    """
    cleaned = reply_text.strip()
    
    # 1. Purge accidental name-asking questions
    cleaned = re.sub(
        r"(?:ו?איך\s+קוראים\s+לך(?:\s+כדי\s+שאדע\s+למי\s+לפנות)?[\s?!.,]*|ו?מה\s+שמך(?:\s+בבקשה)?[\s?!.,]*|תגיד\s+מה\s+השם\s+שלך[\s?!.,]*|למי\s+לפנות[\s?!.,]*)",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()
    
    # 2. Purge fake machine count hallucinations
    cleaned = re.sub(r"\(?\d+\s+מכשירים\s+בתיקון\)?", "", cleaned).strip()
    cleaned = re.sub(r"יש\s+כרגע\s+\d+\s+מכשירים\s+בתיקון\s*,?\s*", "", cleaned).strip()
    cleaned = re.sub(r"שיש\s+כרגע\s+\d+\s+מכשירים\s+בתיקון\s*,?\s*", "", cleaned).strip()
    
    if not customer_name:
        return cleaned

    if already_greeted:
        # In ongoing conversation: STRIP repetitive greetings!
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
        # First turn only: ensure we greet once with name and ask how they are
        has_name = customer_name in cleaned
        has_how_are_you = any(p in cleaned for p in ["מה שלומך", "מה נשמע"])
        if not has_name or not has_how_are_you:
            salutation = f"שלום {customer_name}, מה שלומך?"
            if re.match(r"^(?:שלום|היי|בוקר טוב|ערב טוב|אהלן)[\s!.,]*", cleaned):
                cleaned = re.sub(r"^(?:שלום|היי|בוקר טוב|ערב טוב|אהלן)[\s!.,]*", f"{salutation} ", cleaned, count=1)
            else:
                cleaned = f"{salutation} {cleaned}"
                
    return cleaned

# ----------------- Routes -----------------
@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {
        "status": "online",
        "service": "ShieldBot AI WhatsApp Agent",
        "models": ACTIVE_MODELS,
        "has_gemini_key": bool(GEMINI_API_KEY),
        "has_whatsapp_url": bool(WHATSAPP_API_URL),
        "admin_phone": ADMIN_WHATSAPP_PHONE
    }

# ----------------- POS & Lab Integration Endpoints -----------------
@app.get("/api/pos/parts")
def get_pos_parts():
    """Returns current parts and live prices from Back-Office / POS inventory."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, part_name, model_keywords, price_nis, in_stock, updated_at FROM pos_inventory").fetchall()
    conn.close()
    return [{"id": r[0], "part_name": r[1], "keywords": r[2], "price_nis": r[3], "in_stock": bool(r[4]), "updated_at": r[5]} for r in rows]

@app.post("/api/pos/update_part")
async def update_pos_part(req: Request):
    """Endpoint for Back-Office / POS system to update daily part prices and stock."""
    try:
        data = await req.json()
        part_name = data.get("part_name", "").strip()
        price_nis = int(data.get("price_nis", 0))
        model_keywords = data.get("model_keywords", part_name).strip()
        in_stock = int(data.get("in_stock", 1))
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO pos_inventory (part_name, model_keywords, price_nis, in_stock, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (part_name, model_keywords, price_nis, in_stock, datetime.now().strftime("%d/%m/%Y %H:%M")))
        conn.commit()
        conn.close()
        return {"ok": True, "message": f"Part {part_name} updated to {price_nis} NIS"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

@app.get("/test_send")
def test_send(phone: str = "0524043644"):
    """Quick diagnostic endpoint to test WhatsApp outgoing message delivery."""
    success = send_whatsapp_message(
        phone,
        "שלום! זוהי הודעת בדיקה משרת הסוכן ShieldBot AI. החיבור לווצאפ פעיל ומסונכרן בהצלחה! 🛡️"
    )
    return {
        "ok": success,
        "recipient": phone,
        "note": "הודעת בדיקה נשלחה בהצלחה."
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    """
    Main Webhook receiving incoming WhatsApp messages from Green-API or Meta Cloud API.
    """
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
    clean_sender = sender_phone

    # 1. Admin Learning Loop (Sanitized - Zero Keywords leak to customer!)
    if clean_sender == clean_admin and ("תשובה:" in message_text or "תשובה " in message_text or "מילות מפתח" in message_text):
        clean_answer, keywords = parse_admin_reply(message_text)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO learned_kb (keywords, answer, created_at) VALUES (?, ?, ?)",
            (keywords, clean_answer, datetime.now().isoformat())
        )
        last_pending = conn.execute(
            "SELECT id, phone, request_text FROM customer_requests WHERE status='pending' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        
        if last_pending:
            conn.execute(
                "UPDATE customer_requests SET status='handled', action_taken=? WHERE id=?",
                ("נענה על ידי מנהל ונלמד במאגר", last_pending[0])
            )
            cust_name = get_contact_name(last_pending[1])
            salutation = f"שלום {cust_name}," if cust_name else "שלום,"
            send_whatsapp_message(
                last_pending[1],
                f"{salutation} חזרתי אליך עם תשובה:\n{clean_answer}"
            )
            customer_dest = last_pending[1]
        else:
            customer_dest = "אין לקוח ממתין (נשמר ישירות למאגר)"
            
        conn.commit()
        conn.close()
        send_whatsapp_message(sender_phone, f"✅ התשובה נשלחה ללקוח ({customer_dest}) ללא מילות מפתח ונשמרה במאגר תחת מילות הזיהוי:\n'{keywords}'")
        return {"ok": True, "admin_action": "knowledge_saved"}

    # 2. Check Customer Name & Memory
    customer_name = get_contact_name(sender_phone)
    extracted_name = extract_name_from_text(message_text)
    if extracted_name:
        customer_name = extracted_name
        save_contact_name(sender_phone, extracted_name)

    # 3. Check Subscriber Status in DB
    sub_info = lookup_subscriber(sender_phone)
    if sub_info.get("found") and not customer_name:
        customer_name = sub_info["name"].split()[0]
        save_contact_name(sender_phone, customer_name)

    subscriber_context = (
        f"פרטי מנוי מאומת: שם {sub_info['name']}, מערכת {sub_info['system']}, "
        f"סטטוס {sub_info['status']}, מסלול/רמה נוכחית: {sub_info['level']}, מזהה מכשיר: {sub_info['deviceId']}."
        if sub_info.get("found")
        else "הלקוח פונה ממספר שאינו רשום כמנוי קיים במערכות נטספרק או כשר פליי."
    )

    already_greeted = has_already_greeted_customer(sender_phone)
    learned_rules = get_learned_knowledge()

    # ----------------- FAST DETERMINISTIC PATH FOR PURE GREETINGS -----------------
    # If the customer's name is not known yet and they only wrote a greeting (שלום, בוקר טוב, ערב טוב וכו')
    if not customer_name and not already_greeted and is_pure_greeting(message_text):
        greeting_prompt_reply = "שלום , על מנת לתת לך את המענה המדויק והמהיר ביותר אשמח שתרשום לי את שמך ובמה אוכל לעזור לך היום ."
        save_chat_message(sender_phone, "customer", message_text)
        save_chat_message(sender_phone, "agent", greeting_prompt_reply)
        send_whatsapp_message(sender_phone, greeting_prompt_reply)
        return {"ok": True, "reply": greeting_prompt_reply, "type": "initial_greeting_prompt"}

    # 4. Call Gemini with conversational prompt
    reply_text = None
    used_model = None

    if client:
        if customer_name:
            if already_greeted:
                name_instruction = f"""
הלקוח מוכר ושמו הפרטי הוא: '{customer_name}'.
כבר בירכת אותו לשלומו בתחילת השיחה!
כללי שיחה אנושיים וקריטיים:
• איסור מוחלט: אל תכתוב שוב "שלום {customer_name}, מה שלומך?" או "היי {customer_name}, מה שלומך?"! שאלת לשלומו קודם, אל תשאל שוב!
• אל תשאל לעולם "איך קוראים לך" - שמו ידוע: {customer_name}.
• שלב את שמו הפרטי '{customer_name}' בטבעיות בתוך גוף המשפט בלבד:
  - אם הוא כותב שהוא לא רוצה להמתין בתור:
    "חשוב לי {customer_name} שלא תמתין זמן מיותר ולכן אין צורך שתמתין במקום — אתה מוזמן פשוט להשאיר לנו את המכשיר במעבדה, וברגע שהוא יהיה מוכן נשלח לך הודעה מסודרת לאיסוף."
  - אם הוא כותב "מעולה אני מגיע אליכם" או "אני בדרך":
    "מצויין תגיע אלינו {customer_name} אנחנו מחכים לך 😃"
"""
            else:
                name_instruction = f"""
הלקוח מוכר ושמו הפרטי הוא: '{customer_name}'. זוהי תחילת השיחה שלכם.
• פתח פעם אחת בברכה חמה: "שלום {customer_name}, מה שלומך?".
• אל תשאל אותו לשמו - שמו ידוע: {customer_name}.
"""
        else:
            name_instruction = """
אינך יודע עדיין את שמו של הלקוח:
1. אם הלקוח מסר את שמו בהודעתו (למשל "קוראים לי ערן", "שמי דניאל", "אני משה"):
   פנה אליו בשמו, וצרף בסוף [SET_NAME: שם_הלקוח].
2. בפנייה ראשונית כאשר שמו של הלקוח עדיין אינו ידוע:
   • במידה והלקוח רק רשם שלום, ערב טוב, בוקר טוב וכו' ללא בקשה מסוימת:
     חובה לענות בדיוק במילים אלו:
     "שלום , על מנת לתת לך את המענה המדויק והמהיר ביותר אשמח שתרשום לי את שמך ובמה אוכל לעזור לך היום ."
   • במידה והלקוח רשם מה הוא צריך:
     חובה להשיב במבנה הבא (כדי לקבל את שמו לפני הטיפול המעמיק):
     "נשמח לעזור לך ב[מה שביקש הלקוח] . תאמר לי בבקשה את שמך המלא שאוכל לטפל בך בצורה המהירה והמקצועית ביותר ."
"""

        system_instruction = f"""
אתה איש שירות ומעבדה אנושי, חם, מקצועי וענייני בווצאפ ("ShieldBot AI").
סגנון דיבור וכללי יסוד חקוקים בסלע:
==================================================
1. שפה יומיומית, טבעית, בהירה וקולחת (בלי תקליטים שחוזרים על עצמם!):
   • מענה קצר, ענייני ומעשי: 1 עד 3 שורות ברורות בלבד.
   • חובה קדושה: לסיים תמיד כל מילה וכל משפט במלואם עם סימן פיסוק תקין.
   • קרא תמיד את היסטוריית השיחה המצורפת ואל תחזור על דברים שכבר נאמרו!
   • {name_instruction}
   • כל המחירים בשקלים חדשים (₪) בלבד. אין אזכור לדולרים ($).

2. מודל תמחור דינמי ומשוער למעבדה (כל עוד אין חיבור ישיר לקופה או לספק):
   • אנו מתקנים ומחליפים מסכים שבורים לכל סוגי המכשירים: מכשירי מקשים (כולל שיאומי מקשים / Qin 1s / F21 Pro / F22 וכו') וסמארטפונים.
   • איסור מוחלט על המצאת מחירים מראש! מחירי מסכים ורכיבים משתנים תדיר אצל הספקים.
   • מקרה א': אם המחיר אינו ידוע לך כלל (לא נלמד מהמנהל):
     אמור ללקוח שאתה בודק כעת את זמינות המסך/החלק והמחיר המעודכן מול המעבדה ומיד חוזר אליו עם תשובה מדויקת.
     וצרף בסוף הודעתך תגית: [ESCALATE: מחיר וזמינות [דגם/חלק] ללקוח {customer_name or sender_phone}].
   • מקרה ב' (כלל המפתח למחיר שנלמד בעבר):
     אם המחיר X כבר נלמד ונשמר מפעם קודמת בכללים שלהלן, לעולם אל תגיד שזהו מחיר סופי להיום!
     ענה ללקוח שהמחיר הוא "בערך X ₪" (אותו אתה זוכר מפעם שעברה, ולכן אמרת בערך), והצע לו לקבל הצעת מחיר מדויקת נכון להיום:
     "המחיר עבור [המוצר/התיקון] הוא בערך X ₪ (לפי מה שנבדק אצלנו בפעם שעברה, ולכן אמרתי בערך). האם תרצה שאבדוק עבורך הצעת מחיר מדויקת נכון להיום?"
     (אל תצרף תגית ESCALATE בהודעה זו - תן ללקוח להשיב תחילה).
   • מקרה ג': אם הלקוח משיב בחיוב ("כן", "אשמח שתבדוק", "תבדוק לי בבקשה", "מעוניין"):
     השב לו שאתה בודק כעת את הצעת המחיר המדויקת להיום מול המעבדה ומיד חוזר אליו.
     וצרף תגית: [ESCALATE: בדיקת הצעת מחיר מדויקת להיום עבור [המוצר/התיקון] ללקוח {customer_name or sender_phone}].
   • איסור מוחלט על המצאת נתוני עומס מזויפים:
     לעולם אל תגיד "יש 4 מכשירים בתיקון" או תנקוב במספר מכשירים!
     אם הלקוח שואל על תור או זמנים:
     הסבר לו בצורה שירותית שאין צורך להמתין במקום — הוא יכול להשאיר את המכשיר במעבדה, וברגע שהמכשיר מוכן הוא יקבל מיד הודעה מסודרת לאיסוף.

3. מחירון ומסלולי הגנה קבועים:
   • כשר פליי בסיסי: 250 ₪ חד-פעמי (ללא דפדפן, ~200 אפליקציות כשרות חיוניות). רישיון פעיל על המכשיר בלבד.
   • כשר פליי מורחב: 180 ₪ התקנה חד-פעמי + רישיון 200 ₪ לשנה (או 300 ₪ לשנה כולל דפדפן מסונן). כ-20,000 אפליקציות + יוטיוב כשר, ספוטיפי כשר, ווצאפ כשר.
   • נטספרק: 350 ₪ לשנה (רישיון שנתי). שינוי רמות חופשי ומיידי בווצאפ (רחבה/שמרני, מתקדמת, בסיסית, מותאמת אישית).

4. כללים שנלמדו מהמנהל בעבר (השתמש במחירים שלהלן כמחיר משוער "בערך X ₪" והצע בדיקה להיום):
   {learned_rules}

5. מתי מעבירים שאלה למנהל באמצעות [ESCALATE: ...]:
   • בכל פעם שלקוח שואל על מחיר מסך או תיקון שאינו מופיע בכללים שנלמדו מהמנהל!
   • בכל פעם שלקוח ביקש לבדוק הצעת מחיר מדויקת ומעודכנת להיום!
   • לעולם אל תצרף [ESCALATE:] להודעות הצגת שם, ברכות, תודות, אישורים, או הודעות הגעה ("מעולה אני מגיע אליכם")!
"""
        config_args = {
            "system_instruction": system_instruction,
            "temperature": 0.2,
            "max_output_tokens": 1000,
        }
        if types and hasattr(types, "ThinkingConfig"):
            try:
                config_args["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
        gen_config = types.GenerateContentConfig(**config_args) if types else None

        recent_history = get_recent_chat_history(sender_phone, limit=6)
        if recent_history:
            prompt_content = f"""היסטוריית ההודעות האחרונות בשיחה זו:
{recent_history}

הודעה חדשה מהלקוח: {message_text}"""
        else:
            prompt_content = f"לקוח {sender_phone}: {message_text}"

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

    # Natural Human Fallback
    if not reply_text:
        if customer_name:
            if already_greeted:
                reply_text = f"העניין בטיפול מול המעבדה {customer_name}, ואני כבר בודק את זה וחוזר אליך."
            else:
                reply_text = f"שלום {customer_name}, מה שלומך? העניין בטיפול ואני כבר בודק את זה וחוזר אליך."
        else:
            if is_pure_greeting(message_text):
                reply_text = "שלום , על מנת לתת לך את המענה המדויק והמהיר ביותר אשמח שתרשום לי את שמך ובמה אוכל לעזור לך היום ."
            else:
                reply_text = "נשמח לעזור לך במה שביקשת . תאמר לי בבקשה את שמך המלא שאוכל לטפל בך בצורה המהירה והמקצועית ביותר ."

    # Check for [SET_NAME: ...] tag to save customer name
    match_name = re.search(r"\[SET_NAME:\s*([^\]]+)\]", reply_text)
    if match_name:
        new_name = match_name.group(1).strip()
        save_contact_name(sender_phone, new_name)
        customer_name = new_name
        reply_text = re.sub(r"\[SET_NAME:\s*[^\]]+\]", "", reply_text).strip()

    # Apply fail-safe name & greeting guard
    if customer_name:
        reply_text = apply_customer_name_guard(reply_text, customer_name, already_greeted)

    # 5. Check if Escalation to Admin is needed
    is_escalated = False
    escalation_question = message_text
    
    if "[ESCALATE:" in reply_text:
        match = re.search(r"\[ESCALATE:\s*([^\]]+)\]", reply_text)
        if match:
            escalation_question = match.group(1).strip()
        reply_text = re.sub(r"\[ESCALATE:\s*[^\]]+\]", "", reply_text).strip()
        is_escalated = True
    elif any(phrase in reply_text for phrase in ["בודק זאת כעת מול מנהל", "בודק זאת כעת מול המעבדה", "אחזור אליך כאן מיד עם תשובה", "אני בודק את זה ומיד חוזר"]):
        if is_substantive_admin_question(message_text):
            is_escalated = True

    # HARD GUARD: NEVER escalate non-substantive messages (names, thank-yous, greetings, arrival notices like "אני מגיע")
    if is_escalated:
        is_quote_escalation = any(k in escalation_question for k in ["הצעת מחיר", "מחיר מדויק", "זמינות", "מחיר"])
        # Suppress if message is purely arrival, queue complaint, or thank you
        if any(arr in message_text for arr in ["מגיע אליכם", "בדרך אליכם", "בתור", "לחכות בתור", "תודה"]):
            is_escalated = False
        elif not is_quote_escalation and not is_substantive_admin_question(message_text):
            print(f"[Admin Escalation Suppressed] Non-substantive message was not sent to admin: '{message_text}'")
            is_escalated = False

    # 6. Save Request to DB
    status = "pending" if is_escalated else "handled"
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO customer_requests (phone, system_name, request_text, action_taken, upsell_offer, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sender_phone,
            sub_info.get("system", "מעבדה/שירות"),
            message_text,
            "הועבר למנהל לבדיקה" if is_escalated else f"מענה אוטונומי ({used_model})",
            "הצעה מותאמת",
            status,
            datetime.now().isoformat()
        )
    )
    conn.commit()
    conn.close()

    # 7. If Escalated -> ACTUALLY SEND WHATSAPP MESSAGE TO ADMIN!
    if is_escalated and clean_admin and clean_sender != clean_admin:
        customer_label = f"{customer_name} ({sender_phone})" if customer_name else sender_phone
        admin_notification = (
            f"❓ *שאלה מלקוח שדורשת את תשובתך* ({customer_label}):\n"
            f"\"{escalation_question}\"\n\n"
            f"השב להודעה זו כדי לענות ללקוח וללמד את הבוט:\n"
            f"תשובה: [התשובה ללקוח] | מילות מפתח: [מילות זיהוי]"
        )
        print(f"[Admin Escalation Sent] Sending question to Admin: {clean_admin}")
        send_whatsapp_message(clean_admin, admin_notification)

    # 8. Save turns to persistent conversation memory
    save_chat_message(sender_phone, "customer", message_text)
    save_chat_message(sender_phone, "agent", reply_text)

    # 9. Send WhatsApp Reply back to customer
    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "escalated": is_escalated, "model": used_model}
