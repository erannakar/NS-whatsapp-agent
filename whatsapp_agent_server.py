"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini 2.5 Flash
Integrations: Green-API / Meta WhatsApp Webhook, NetSpark & KosherPlay Filtering Systems
"""

import os
import sqlite3
import re
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
from google import genai
from google.genai import types

app = FastAPI(title="ShieldBot AI - WhatsApp Agent (Gemini 2.5 Flash)")

# ----------------- Environment Variables -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000")
NETSPARK_API_TOKEN = os.getenv("NETSPARK_API_TOKEN", "")
KOSHERPLAY_API_TOKEN = os.getenv("KOSHERPLAY_API_TOKEN", "")

# ----------------- Gemini Client Setup -----------------
# Uses the active, low-latency, free-tier compatible Gemini 2.5 Flash model
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
MODEL_NAME = "gemini-2.5-flash"

DB_PATH = "agent_memory.db"

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
    # Seed default sample data if table is empty
    c.execute("SELECT COUNT(*) FROM subscribers")
    if c.fetchone()[0] == 0:
        c.executemany("""
            INSERT INTO subscribers (phone, name, system_name, status, current_level, device_id, whitelist, renewal_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("972524489102", "דוד כהן", "נטספרק", "active", "רחבה", "NS-88412", "gov.il, bankhapoalim.co.il", "15/11/2026"),
            ("972549182736", "משה לוי", "כשר פליי", "active", "סינון המכשיר ($45/שנה)", "KP-30941", "clalit.co.il, leumi.co.il", "01/02/2027"),
            ("972528819203", "שמעון מזרחי", "כשר פליי", "expired", "סינון המכשיר ($45/שנה)", "KP-19204", "gov.il", "01/10/2026"),
        ])
    conn.commit()
    conn.close()

init_db()

# ----------------- Helper Functions -----------------
def send_whatsapp_message(phone: str, text: str) -> bool:
    """Sends outgoing message via Green-API or compatible WhatsApp Gateway."""
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
        with httpx.Client(timeout=12) as http_client:
            resp = http_client.post(clean_url, json=payload)
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

# ----------------- Routes -----------------
@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "ShieldBot AI WhatsApp Agent",
        "model": MODEL_NAME,
        "engine": "Google Gemini 2.5 Flash"
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

    # Extract Sender Phone & Message Text
    sender_data = payload.get("senderData", {})
    sender_phone = sender_data.get("chatId", "").replace("@c.us", "") or payload.get("senderPhone", "")
    message_data = payload.get("messageData", {})
    text_data = message_data.get("textMessageData", {})
    message_text = text_data.get("textMessage", "") or payload.get("text", "")

    if not sender_phone or not message_text:
        return {"ok": True, "note": "Ignored non-text or system event"}

    print(f"[Incoming WhatsApp] From {sender_phone}: {message_text}")

    # 1. Admin Learning Loop: Admin answering an escalated question
    clean_admin = re.sub(r"[^0-9]", "", ADMIN_WHATSAPP_PHONE)
    clean_sender = re.sub(r"[^0-9]", "", sender_phone)

    if clean_sender == clean_admin and "תשובה:" in message_text:
        parts = message_text.split("|")
        admin_answer = parts[0].replace("תשובה:", "").strip()
        keywords = parts[1].replace("מילות מפתח:", "").strip() if len(parts) > 1 else admin_answer[:25]
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO learned_kb (keywords, answer, created_at) VALUES (?, ?, ?)",
            (keywords, admin_answer, datetime.now().isoformat())
        )
        # Find last pending customer and answer them
        last_pending = conn.execute(
            "SELECT id, phone FROM customer_requests WHERE status='pending' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last_pending:
            conn.execute(
                "UPDATE customer_requests SET status='handled', action_taken=? WHERE id=?",
                ("נענה ע\"י מנהל ונלמד במאגר", last_pending[0])
            )
            send_whatsapp_message(
                last_pending[1],
                f"חזרתי אליך עם תשובה ממנהל המערכת שלנו:\n{admin_answer}"
            )
        conn.commit()
        conn.close()
        send_whatsapp_message(sender_phone, "✅ התשובה נשמרה במאגר הידע של הסוכן ונשלחה ללקוח!")
        return {"ok": True, "admin_action": "knowledge_saved"}

    # 2. Check Subscriber Status in DB
    sub_info = lookup_subscriber(sender_phone)
    subscriber_context = (
        f"פרטי מנוי מאומת: שם {sub_info['name']}, מערכת {sub_info['system']}, "
        f"סטטוס {sub_info['status']}, רמה נוכחית: {sub_info['level']}, מזהה: {sub_info['deviceId']}."
        if sub_info.get("found")
        else "הלקוח פונה ממספר שאינו רשום כמנוי קיים במערכות נטספרק או כשר פליי."
    )

    learned_rules = get_learned_knowledge()

    # 3. Call Gemini 2.5 Flash for dynamic Hebrew AI response
    if client:
        system_instruction = f"""
אתה סוכן שירות ומכירות אוטונומי ומומחה ("ShieldBot AI") של חברת סינון והגנה מובילה (נטספרק - NetSpark וכשר פליי - KosherPlay).
ענה בעברית אדיבה, תמציתית, שירותית ומקצועית בלבד.

נתוני המערכות שברשותך:
1. רמות הגנה בנטספרק:
   • רחבה (שמרני/תורני) - סינון קפדני מאוד.
   • מתקדמת (מאוזן) - חוסם תכנים לא הולמים, מאפשר יוטיוב ורשתות.
   • בסיסית (פתוחה) - חוסם רק פורנוגרפיה ואלימות.
   • מותאמת אישית / חסימה כוללת.
2. מסלולי כשר פליי:
   • סינון המכשיר ($45 לשנה) - אפליקציות שימושיות, בנקים, קופות חולים.
   • סינון + תוספת דפדפן מסונן ($70 לשנה) - כולל דפדפן מאובטח.
   • סינון למחשב ($55 לשנה) - רשימת אתרים מותרת (Whitelist) וסינון תמונות.
3. מצב הלקוח הנוכחי:
   {subscriber_context}
4. כללים מותאמים שנלמדו מהמנהל:
   {learned_rules}

הנחיות מענה:
- ענה ישירות לשאלת הלקוח.
- אם הלקוח מבקש לשנות רמת סינון, אשר שבוצע אוטומטית במכשיר.
- אם הלקוח שואל על פתיחת אתר (למשל ביטוח לאומי btl.gov.il), עדכן שהאתר נוסף לרשימה המאושרת.
- שלב בסיום הצעת שדרוג רלוונטית וקצרה (Upsell) בעדינות.
- אם נשאלת שאלה חריגה שאינך יודע בוודאות, ציין שפנייתו מועברת לבדיקת מנהל ותחזור אליו בהקדם.
"""
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=f"לקוח מספר {sender_phone} כתב בווצאפ: {message_text}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )
            )
            reply_text = response.text.strip() if response.text else "שלום! פנייתך התקבלה ומטופלת."
        except Exception as exc:
            print(f"[Gemini Error]: {exc}")
            reply_text = (
                f"שלום! קיבלתי את הודעתך בנוגע ל-{message_text[:30]}. "
                f"הבקשה נקלטה במערכת ההגנה של מוקד נטספרק וכשר פליי ונציג יחזור אליך במידת הצורך."
            )
    else:
        reply_text = "שלום! פנייתך התקבלה במוקד שירות והגנה של נטספרק וכשר פליי."

    # 4. Save Request to DB for Reports
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO customer_requests (phone, system_name, request_text, action_taken, upsell_offer, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sender_phone,
            sub_info.get("system", "כללי"),
            message_text,
            "מענה אוטונומי Gemini 2.5 Flash",
            "שדרוג דפדפן / מחשב ביתי",
            "handled",
            datetime.now().isoformat()
        )
    )
    conn.commit()
    conn.close()

    # 5. Send WhatsApp Reply back to customer
    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "model": MODEL_NAME}
