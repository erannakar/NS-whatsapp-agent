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
    clean_phone = re.sub(r"[^0-9]", "", phone)
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
    return "\n".join([f"- מילות זיהוי ({r[0]}): ענה: {r[1]}" for r in rows])

def lookup_subscriber(phone: str) -> dict:
    """Checks subscriber status in NetSpark & KosherPlay databases."""
    digits = re.sub(r"[^0-9]", "", phone)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name, system_name, status, current_level, device_id, whitelist, renewal_date "
        "FROM subscribers WHERE phone LIKE ? LIMIT 1",
        (f"%{digits[-7:]}%" if len(digits) >= 7 else phone,)
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

def get_contact_name(phone: str) -> str:
    """Retrieves remembered name from contacts or subscriber database."""
    digits = re.sub(r"[^0-9]", "", phone)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name FROM contacts WHERE phone LIKE ? OR phone = ? LIMIT 1",
        (f"%{digits[-7:]}%" if len(digits) >= 7 else phone, phone)
    ).fetchone()
    if row and row[0]:
        conn.close()
        return row[0].strip()
    
    sub_row = conn.execute(
        "SELECT name FROM subscribers WHERE phone LIKE ? LIMIT 1",
        (f"%{digits[-7:]}%" if len(digits) >= 7 else phone,)
    ).fetchone()
    conn.close()
    if sub_row and sub_row[0]:
        first_only = sub_row[0].strip().split()[0]
        return first_only
    return ""

def save_contact_name(phone: str, name: str):
    """Saves or updates customer name in contacts memory."""
    clean_name = name.strip()
    clean_phone = re.sub(r"[^0-9]", "", phone)
    if not clean_name or not clean_phone:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO contacts (phone, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(phone) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
    """, (clean_phone, clean_name, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def extract_name_from_text(text: str) -> str:
    """Extracts customer first name if explicitly stated in message."""
    stopwords = {"רוצה", "צריך", "יכול", "מדבר", "שואל", "מבקש", "שלום", "היי", "בוקר", "ערב", "יש", "לא", "פה", "כאן"}
    patterns = [
        r"(?:שמי|קוראים לי|אני)\s+([א-ת]{2,15})",
        r"^([א-ת]{2,15})\s*:\s*",
        r"זה\s+([א-ת]{2,15})\s+כאן"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip()
            if candidate not in stopwords:
                return candidate
    return ""

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
    sender_phone = sender_data.get("chatId", "").replace("@c.us", "") or payload.get("senderPhone", "")
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

    clean_admin = re.sub(r"[^0-9]", "", ADMIN_WHATSAPP_PHONE)
    clean_sender = re.sub(r"[^0-9]", "", sender_phone)

    # 1. Admin Learning Loop
    if clean_sender == clean_admin and ("תשובה:" in message_text or "תשובה " in message_text):
        parts = message_text.replace("תשובה:", "תשובה ").split("|")
        admin_answer = parts[0].replace("תשובה", "").strip()
        keywords = parts[1].replace("מילות מפתח:", "").replace("מילות מפתח", "").strip() if len(parts) > 1 else admin_answer[:25]
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO learned_kb (keywords, answer, created_at) VALUES (?, ?, ?)",
            (keywords, admin_answer, datetime.now().isoformat())
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
                f"{salutation} חזרתי אליך עם תשובה:\n{admin_answer}"
            )
            customer_dest = last_pending[1]
        else:
            customer_dest = "אין לקוח ממתין (נשמר ישירות למאגר)"
            
        conn.commit()
        conn.close()
        send_whatsapp_message(sender_phone, f"✅ התשובה נשמרה במאגר הידע של הסוכן ונשלחה ללקוח ({customer_dest})!")
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

    learned_rules = get_learned_knowledge()

    # 4. Call Gemini with automatic model fallback
    reply_text = None
    used_model = None

    if client:
        name_instruction = (
            f"השם הפרטי של הלקוח ידוע: '{customer_name}'. פנה אליו תמיד בשמו הפרטי ('שלום {customer_name}, ...')."
            if customer_name
            else "אינך יודע עדיין את שמו של הלקוח. שאל אותו בנימוס ובטבעיות לשמו (למשל: 'שלום! בשמחה, אני בודק את זה. איך קוראים לך כדי שאדע למי לפנות?'). אם הוא כתב לך את שמו, הוסף בסוף תשובתך [SET_NAME: שם_הלקוח]."
        )

        system_instruction = f"""
אתה סוכן אישי אנושי, חם, מקצועי וענייני בווצאפ ("ShieldBot AI").
סגנון דיבור וכללי יסוד חקוקים בסלע:
==================================================
1. שפה יומיומית, טבעית, בהירה ושלמה (איסור מוחלט על חיתוך מילים!):
   • מענה קצר, ענייני, ומעשי: 1 עד 3 שורות/משפטים ברורים בלבד.
   • חובה קדושה: לסיים תמיד כל מילה וכל משפט במלואם עם סימן פיסוק תקין. לעולם אל תחתוך מילה באמצע (כמו "כן בו" או "תגי")! ודא שכל המסר הועבר במלואו ללקוח.
   • קיצור אמיתי פירושו תמציתיות ולא קטיעת מילים: אין לשלוח גליונות או מגילות של טקסט שלאף אחד אין סבלנות לקרוא, אלא אם הלקוח ביקש במפורש פירוט.
   • אסור להשתמש בתבניות תקליט, שפת מערכת מנוכרת או הודעות פורמליות של מוקדנים. דבר בגובה העיניים כאיש צוות שמטפל אישית בפנייה.
   • {name_instruction}
   • כל המחירים בשקלים חדשים (₪) בלבד. אין אזכור לדולרים ($).

2. שירותי מעבדה ותיקונים (מסכים, שקעי טעינה, סוללות):
   • אנו מתקנים מסכים שבורים לכל סוגי המכשירים: מכשירי מקשים (כולל שיאומי מקשים / Qin / Q1 / F21 / F22 וכו) וסמארטפונים!
   • בנוסף: תיקון שקעי טעינה, החלפת סוללות, תיקוני לוח, פריצות כשרות, והתקנת גרסאות כשרות.
   • אם לקוח שואל אם יש מסך או אם מתקנים: אשר בביטחון ובמילים שלמות: "בוודאי! אנחנו מתקנים מסכים לכל מכשירי המקשים והסמארטפונים."
   • אם שואל כמה עולה או שואל על מכשיר ללא דגם: שאל איזה דגם מדויק יש לו ואיך קוראים לו (אם אינו ידוע) כדי לתת מחיר ולהתקדם.
   • לעולם אל תגיד שאנו לא מתקנים! יש לנו מעבדה מלאה!

3. מחירון ומסלולים:
   • כשר פליי בסיסי: 250 ₪ חד-פעמי (ללא דפדפן, ~200 אפליקציות כשרות חיוניות). רישיון פעיל על המכשיר בלבד.
   • כשר פליי מורחב: 180 ₪ התקנה חד-פעמי + רישיון 200 ₪ לשנה (או 300 ₪ לשנה כולל דפדפן מסונן). כ-20,000 אפליקציות + יוטיוב כשר, ספוטיפי כשר, ווצאפ כשר. הרישיון נייד ועובר למכשיר חדש ללא עלות רישיון!
   • נטספרק: 350 ₪ לשנה (רישיון שנתי). שינוי רמות חופשי ומיידי בווצאפ (רחבה/שמרני, מתקדמת, בסיסית, מותאמת אישית).

4. כלל ברזל נגד המצאות / תשובות שגויות (Anti-Hallucination):
   • לעולם אל תגיד בביטחון "אנחנו לא עושים את זה" לגבי שירות או דגם מכשיר!
   • אם נשאלת שאלה על מחיר תיקון ספציפי, חלק חילוף, או שאלה טכנית שאינך יודע בוודאות:
     ענה ללקוח בקצרה:
     "אני בודק את זה כעת מול המעבדה ומיד חוזר אליך."
     וצרף בסוף הודעתך את התגית: [ESCALATE: שאלה_קצרה_למנהל]

5. פרטי הלקוח:
   {subscriber_context}

6. כללים שנלמדו מהמנהל:
   {learned_rules}
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

        for model_candidate in ACTIVE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=f"לקוח {sender_phone}: {message_text}",
                    config=gen_config
                )
                if response and response.text:
                    reply_text = response.text.strip()
                    used_model = model_candidate
                    break
            except Exception as exc:
                print(f"[Gemini Error on {model_candidate}]: {exc}")

    # Natural Human Fallback (Never robotic boilerplate!)
    if not reply_text:
        if customer_name:
            reply_text = f"שלום {customer_name}, העניין בטיפול ואני כבר בודק את זה וחוזר אליך."
        else:
            reply_text = "שלום! העניין בטיפול ואני כבר בודק את זה. איך קוראים לך כדי שאדע למי לפנות?"

    # Check for [SET_NAME: ...] tag to save customer name
    match_name = re.search(r"\[SET_NAME:\s*([^\]]+)\]", reply_text)
    if match_name:
        new_name = match_name.group(1).strip()
        save_contact_name(sender_phone, new_name)
        customer_name = new_name
        reply_text = re.sub(r"\[SET_NAME:\s*[^\]]+\]", "", reply_text).strip()

    # 5. Check if Escalation to Admin is needed
    is_escalated = False
    escalation_question = message_text
    
    if "[ESCALATE:" in reply_text:
        is_escalated = True
        match = re.search(r"\[ESCALATE:\s*([^\]]+)\]", reply_text)
        if match:
            escalation_question = match.group(1).strip()
        reply_text = re.sub(r"\[ESCALATE:\s*[^\]]+\]", "", reply_text).strip()
    elif any(phrase in reply_text for phrase in ["בודק זאת כעת מול מנהל", "בודק זאת כעת מול המעבדה", "אחזור אליך כאן מיד עם תשובה", "אני בודק את זה ומיד חוזר"]):
        is_escalated = True

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
            f"\"{message_text}\"\n\n"
            f"השב להודעה זו כדי לענות ללקוח וללמד את הבוט:\n"
            f"תשובה: [התשובה ללקוח] | מילות מפתח: [מילות זיהוי]"
        )
        print(f"[Admin Escalation Sent] Sending question to Admin: {clean_admin}")
        send_whatsapp_message(clean_admin, admin_notification)

    # 8. Send WhatsApp Reply back to customer
    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "escalated": is_escalated, "model": used_model}
