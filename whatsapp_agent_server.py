"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini (gemini-3.8-flash with auto-fallback to gemini-2.5-flash)
Integrations: Green-API / Meta WhatsApp Webhook, NetSpark & KosherPlay Filtering, Lab & Repair Services
"""

import os
import sqlite3
import re
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
from google import genai
from google.genai import types

app = FastAPI(title="ShieldBot AI - WhatsApp Agent")

# ----------------- Environment Variables -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip().strip('"').strip("'")
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000").strip().strip('"').strip("'")
NETSPARK_API_TOKEN = os.getenv("NETSPARK_API_TOKEN", "").strip()
KOSHERPLAY_API_TOKEN = os.getenv("KOSHERPLAY_API_TOKEN", "").strip()

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
ACTIVE_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash"]
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
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT keywords, answer FROM learned_kb").fetchall()
    conn.close()
    if not rows:
        return "אין עדיין כללים נוספים."
    return "\n".join([f"- מילות זיהוי ({r[0]}): ענה: {r[1]}" for r in rows])

def lookup_subscriber(phone: str) -> dict:
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
        "models": ACTIVE_MODELS,
        "has_gemini_key": bool(GEMINI_API_KEY),
        "has_whatsapp_url": bool(WHATSAPP_API_URL),
        "admin_phone": ADMIN_WHATSAPP_PHONE
    }

@app.get("/test_send")
def test_send(phone: str = "0524043644"):
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
    try:
        payload = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    # Extract Sender Phone & Message Text
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

    # 1. Admin Learning Loop: מנהל עונה לשאלה שהועברה אליו
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
                ("נענה ע\"י מנהל ונלמד במאגר", last_pending[0])
            )
            send_whatsapp_message(
                last_pending[1],
                f"שלום, חזרתי אליך עם תשובה מהמעבדה / מנהל השירות שלנו:\n{admin_answer}"
            )
            customer_dest = last_pending[1]
        else:
            customer_dest = "אין לקוח ממתין (נשמר ישירות למאגר)"
            
        conn.commit()
        conn.close()
        send_whatsapp_message(sender_phone, f"✅ התשובה נשמרה במאגר הידע של הסוכן ונשלחה ללקוח ({customer_dest})!")
        return {"ok": True, "admin_action": "knowledge_saved"}

    # 2. אימות מנוי קיים
    sub_info = lookup_subscriber(sender_phone)
    subscriber_context = (
        f"פרטי מנוי מאומת: שם {sub_info['name']}, מערכת {sub_info['system']}, "
        f"סטטוס {sub_info['status']}, מסלול/רמה: {sub_info['level']}, מכשיר: {sub_info['deviceId']}."
        if sub_info.get("found")
        else "הלקוח פונה ממספר שאינו רשום כמנוי קיים במערכות נטספרק או כשר פליי."
    )

    learned_rules = get_learned_knowledge()

    # 3. הפעלת מודל Gemini
    reply_text = None
    used_model = None

    if client:
        system_instruction = f"""
אתה סוכן שירות, מכירות ומעבדה אוטונומי ("ShieldBot AI").
סגנון מענה קריטי:
- ענה בעברית טבעית, חמה, קצרה וקולעת! אסור בתכלית האיסור לכתוב תשובות ארוכות וטרחניות!
- אורך התשובה: 2 עד 4 שורות לכל היותר. אנשים בווצאפ רוצים מענה מהיר ומדויק.
- כל המחירים אך ורק בשקלים חדשים (₪). לעולם אל תשתמש בדולר ($).

תחומי הפעילות והשירותים שלנו:
==================================================
1. מעבדת תיקונים מקצועית ומכירת מכשירים:
   • אנו מתקנים מסכים שבורים לכל סוגי המכשירים: מכשירי מקשים (כולל שיאומי מקשים / Qin / Q1 / F21 / F22 וכו') וסמארטפונים!
   • בנוסף: תיקון שקעי טעינה, החלפת סוללות, תיקוני לוח ורכיבים, פריצות כשרות, והתקנת גרסאות כשרות.
   • אם לקוח שואל על תיקון מסך / מעבדה: אשר בשמחה שאנו מתקנים! הזמן אותו להביא את המכשיר או שאל איזה דגם יש לו כדי לתת הצעת מחיר מדויקת.
   • לעולם אל תגיד שאנו עוסקים רק בסינון ולא בתיקונים! אנו מפעילים מעבדה מלאה!

2. כשר פליי (KosherPlay) — מסלולים תמציתיים:
   • בסיסי: 250 ₪ חד-פעמי (ללא דפדפן, ~200 אפליקציות שימושיות כשרות). הרישיון פעיל על המכשיר בלבד.
   • מורחב: 180 ₪ התקנה חד-פעמי + רישיון 200 ₪ לשנה (או 300 ₪ לשנה כולל דפדפן מסונן). כ-20,000 אפליקציות + יוטיוב כשר, ספוטיפי כשר, ווצאפ כשר. הרישיון נייד ועובר למכשיר חדש ללא עלות רישיון!

3. נטספרק (NetSpark):
   • 350 ₪ לשנה (רישיון שנתי).
   • שינוי רמות חופשי ומיידי בווצאפ (רחבה/שמרני, מתקדמת, בסיסית, מותאמת אישית).

4. כלל ברזל נגד המצאות / תשובות שגויות בביטחון (Anti-Hallucination):
   • לעולם אל תגיד בביטחון "אנחנו לא עושים את זה" לגבי מוצר, שירות, דגם מכשיר או תיקון!
   • אם נשאלת שאלה על מחיר ספציפי של תיקון דגם, חלק חילוף, או שאלה טכנית שאינך יודע בוודאות:
     ענה ללקוח בקצרה:
     "אני בודק זאת כעת מול המעבדה/הצוות שלנו ואחזור אליך כאן מיד."
     וצרף בסוף הודעתך באופן מדויק את התגית: [ESCALATE: שאלה_קצרה_למנהל]

5. מצב הלקוח הנוכחי:
   {subscriber_context}

6. כללים שנלמדו מהמנהל:
   {learned_rules}
"""
        for model_candidate in ACTIVE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=f"לקוח {sender_phone}: {message_text}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    )
                )
                if response and response.text:
                    reply_text = response.text.strip()
                    used_model = model_candidate
                    break
            except Exception as exc:
                print(f"[Gemini Error on {model_candidate}]: {exc}")

    if not reply_text:
        reply_text = "שלום! פנייתך התקבלה במוקד השירות, המעבדה והסינון. נציג יחזור אליך בהקדם."

    # 4. בדיקה האם נדרשת העברה למנהל
    is_escalated = False
    if "[ESCALATE:" in reply_text:
        is_escalated = True
        reply_text = re.sub(r"\[ESCALATE:\s*[^\]]+\]", "", reply_text).strip()
    elif any(phrase in reply_text for phrase in ["בודק זאת כעת מול מנהל", "בודק זאת כעת מול המעבדה", "אחזור אליך כאן מיד"]):
        is_escalated = True

    # 5. שמירת הבקשה בדאטה-בייס
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
            "—",
            status,
            datetime.now().isoformat()
        )
    )
    conn.commit()
    conn.close()

    # 6. שליחת הודעת ווצאפ אקטיבית למנהל!
    if is_escalated and clean_admin and clean_sender != clean_admin:
        admin_notification = (
            f"❓ *שאלה מלקוח שדורשת את תשובתך* ({sender_phone}):\n"
            f"\"{message_text}\"\n\n"
            f"השב להודעה זו כדי לענות ללקוח וללמד את הבוט:\n"
            f"תשובה: [התשובה ללקוח] | מילות מפתח: [מילות זיהוי]"
        )
        send_whatsapp_message(clean_admin, admin_notification)

    # 7. שליחת המענה חזרה ללקוח
    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "escalated": is_escalated, "model": used_model}
