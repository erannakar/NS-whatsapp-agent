import os
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
from google import genai
from google.genai import types

app = FastAPI(title="ShieldBot AI - WhatsApp Agent")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
ADMIN_WHATSAPP_PHONE = os.getenv("ADMIN_WHATSAPP_PHONE", "972500000000")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
DB_PATH = "agent_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS learned_kb (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keywords TEXT,
        answer TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS customer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        system_name TEXT,
        request_text TEXT,
        action_taken TEXT,
        upsell_offer TEXT,
        status TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

def send_whatsapp_message(phone: str, text: str):
    if not WHATSAPP_API_URL:
        print("[Warning] WHATSAPP_API_URL is not set!")
        return
    try:
        r = httpx.post(WHATSAPP_API_URL, json={"chatId": f"{phone}@c.us", "message": text}, timeout=10)
        print(f"[WhatsApp Sent] To: {phone}, Status: {r.status_code}")
    except Exception as exc:
        print(f"[WhatsApp Error]: {exc}")

@app.get("/")
def health():
    return {"status": "ok", "agent": "ShieldBot AI"}

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    payload = await req.json()
    sender_data = payload.get("senderData", {})
    sender_phone = sender_data.get("chatId", "").replace("@c.us", "") or payload.get("senderPhone", "")
    message_data = payload.get("messageData", {})
    message_text = message_data.get("textMessageData", {}).get("textMessage", "") or payload.get("text", "")

    if not sender_phone or not message_text:
        return {"ok": True}

    print(f"[Incoming WhatsApp] From {sender_phone}: {message_text}")

    reply_text = "שלום! פנייתך התקבלה במוקד."
    if client:
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=f"לקוח {sender_phone}: {message_text}",
                config=types.GenerateContentConfig(
                    system_instruction="אתה נציג שירות ומכירות מקצועי של חברת סינון והגנה (נטספרק וכשר פליי). ענה בעברית אדיבה וקצרה.",
                    temperature=0.2,
                )
            )
            if response and response.text:
                reply_text = response.text
        except Exception as exc:
            print(f"[Gemini Error]: {exc}")
            reply_text = "שלום! פנייתך התקבלה במוקד ההגנה והסינון (נטספרק וכשר פליי). כיצד נוכל לעזור?"

    send_whatsapp_message(sender_phone, reply_text)
    return {"ok": True, "reply": reply_text}
