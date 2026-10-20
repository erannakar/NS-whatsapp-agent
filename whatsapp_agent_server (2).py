"""
ShieldBot AI - WhatsApp Autonomous Agent Server
Powered by Google Gemini (gemini-3.8-flash with auto-fallback to gemini-2.5-flash)
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

app = FastAPI(title="ShieldBot AI - WhatsApp Agent")

# ----------------- Environment Variables -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip().strip('"').strip("'")
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000").strip().strip('"').strip("'")
NETSPARK_API_TOKEN = os.getenv("NETSPARK_API_TOKEN", "").strip()
KOSHERPLAY_API_TOKEN = os.getenv("KOSHERPLAY_API_TOKEN", "").strip()

# ----------------- Gemini Client Setup -----------------
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

ACTIVE_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash"]
DB_PATH = "agent_memory.db"

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

@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "ShieldBot AI WhatsApp Agent",
        "models": ACTIVE_MODELS,
        "has_gemini_key": bool(GEMINI_API_KEY),
        "has_whatsapp_url": bool(WHATSAPP_API_URL)
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    sender_data = payload.get("senderData", {})
    sender_phone = sender_data.get("chatId", "").replace("@c.us", "") or payload.get("senderPhone", "")
    message_data = payload.get("messageData", {})
    text_data = message_data.get("textMessageData", {})
    message_text = text_data.get("textMessage", "") or payload.get("text", "")

    if not sender_phone or not message_text:
        return {"ok": True, "note": "Ignored non-text or system event"}

    print(f"[Incoming WhatsApp] From {sender_phone}: {message_text}")

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

    sub_info = lookup_subscriber(sender_phone)
    subscriber_context = (
        f"פרטי מנוי מאומת: שם {sub_info['name']}, מערכת {sub_info['system']}, "
        f"סטטוס {sub_info['status']}, מסלול/רמה נוכחית: {sub_info['level']}, מזהה מכשיר: {sub_info['deviceId']}."
        if sub_info.get("found")
        else "הלקוח פונה ממספר שאינו רשום כמנוי קיים במערכות נטספרק או כשר פליי."
    )

    learned_rules = get_learned_knowledge()

    reply_text = None
    used_model = None

    if client:
        system_instruction = f"""
אתה סוכן שירות ומכירות אוטונומי ומומחה ("ShieldBot AI") של חברת סינון והגנה מובילה (נטספרק - NetSpark וכשר פליי - KosherPlay).
ענה בעברית אדיבה, בהירה, שירותית ומקצועית בלבד.
הערה קריטית: כל המחירים אך ורק בשקלים חדשים (₪). לעולם אל תשתמש בסימן דולר ($).

מחירון ומסלולי השירות הרשמיים שלנו:
==================================================
1. כשר פליי (KosherPlay) - מסלולים ומדיניות החלפת מכשיר:
   א. מסלול כשר פליי בסיסי:
      • כולל: חסימת גישה מלאה לדפדפן ולתכנים בלתי ראויים באפליקציות.
      • חנות אפליקציות: מצומצמת (כ-200 אפליקציות כשרות) הנחוצות לשימוש בסיסי יומיומי ולצרכי עבודה כגון בנקים, קופות חולים, וויז (Waze), ווצאפ ועוד.
      • עלות: 250 ₪ תשלום חד-פעמי.
      • מדיניות החלפת מכשיר: הרישיון פעיל על אותו המכשיר בלבד עד להחלפתו. אם הלקוח מחליף מכשיר, הרישיון אינו עובר ויש לרכוש רישיון חדש.

   ב. מסלול כשר פליי מורחב:
      • כולל: כ-20,000 (עשרים אלף) אפליקציות כשרות ומוגנות, וכן אפליקציות ייחודיות בפיתוח בלעדי: ספוטיפי כשר, יוטיוב כשר, ווצאפ כשר ועוד.
      • עלות התקנה: 180 ₪ חד-פעמי.
      • עלות רישיון/שירות:
        - מערכת הגנה ורישיון בלבד: 200 ₪ לשנה.
        - מערכת הגנה + דפדפן מסונן: 300 ₪ לשנה (שדרוג דפדפן בתוספת 100 ₪ לשנה).
      • מדיניות החלפת מכשיר: הרישיון נייד ויכול לעבור למכשיר החדש ללא תשלום נוסף על הרישיון! הלקוח משלם רק עבור ההתקנה במכשיר החדש (180 ₪).

2. נטספרק (NetSpark):
   • עלות: 350 ₪ לשנה (רישיון שנתי).
   • רמות סינון לבחירה (המעבר ביניהן מתבצע מיידית וחינם דרך הודעה בווצאפ):
     - רחבה (שמרני/תורני): סינון קפדני מאוד, אתרים תורניים וחדשות מאושרות בלבד.
     - מתקדמת (מאוזן): חוסם תכנים לא הולמים, מאפשר יוטיוב ורשתות בצורה מוגנת ומסוננת.
     - בסיסית (פתוחה): חוסם פורנוגרפיה ואלימות קשה.
     - מותאמת אישית / חסימה כוללת.

3. מצב הלקוח הנוכחי:
   {subscriber_context}

4. כללים מותאמים שנלמדו מהמנהל:
   {learned_rules}

הנחיות מענה ושירות:
- ענה ישירות לשאלת הלקוח בסבר פנים יפות.
- אם הלקוח מבקש לשנות רמת סינון בנטספרק, אשר שהרמה שונתה בהצלחה במכשיר.
- אם הלקוח מבקש לפתוח אתר מסוים (כגון btl.gov.il, אתרי ממשלה, בנקים), אשר שהאתר נוסף לרשימה המאושרת במכשירו.
- אם לקוח מתעניין במסלול הבסיסי, ציין את יתרון המחיר החד-פעמי (250 ₪), אך הדגש שבמסלול המורחב (180 ₪ התקנה + 200 ₪ לשנה) מקבלים 20,000 אפליקציות, יוטיוב וספוטיפי כשרים, ובעיקר: כשיחליף מכשיר בעתיד הרישיון נשמר לו ויעבור בחינם (ישלם רק 180 ₪ התקנה במקום רישיון מחדש).
- אם נשאלת שאלה חריגה שאינך יודע בוודאות, ציין שפנייתו הועברה לבדיקת מנהל המערכת ונחזור אליו בהקדם.
"""
        for model_candidate in ACTIVE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=f"לקוח מספר {sender_phone} כתב בווצאפ: {message_text}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    )
                )
                if response and response.text:
                    reply_text = response.text.strip()
                    used_model = model_candidate
                    print(f"[Gemini Success] Answered with model: {model_candidate}")
                    break
            except Exception as exc:
                print(f"[Gemini Error on {model_candidate}]: {exc}")

    if not reply_text:
        reply_text = (
            f"שלום! קיבלתי את הודעתך בנוגע ל-{message_text[:30]}. "
            f"הבקשה נקלטה במוקד השירות וההגנה (נטספרק וכשר פליי) ונציג יחזור אליך בהקדם."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO customer_requests (phone, system_name, request_text, action_taken, upsell_offer, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sender_phone,
            sub_info.get("system", "כללי"),
            message_text,
            f"מענה אוטונומי ({used_model or 'fallback'})",
            "הצעה מותאמת לפי מסלול",
            "handled",
            datetime.now().isoformat()
        )
    )
    conn.commit()
    conn.close()

    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text, "model": used_model}
