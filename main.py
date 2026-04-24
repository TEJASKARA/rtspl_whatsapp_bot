"""
WhatsApp AI Chatbot - Main Application
FastAPI webhook handler for WhatsApp Cloud API
"""

import os
import hmac
import hashlib
import httpx
from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from chatbot import get_ai_response
from database import (
    save_message, get_conversation_history,
    get_human_assist_count, increment_human_assist_count,
    get_consultation_state, set_consultation_state,
    is_duplicate_message,
)

load_dotenv()

app = FastAPI(title="WhatsApp AI Chatbot")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_SECRET = os.getenv("APP_SECRET")

# ─────────────────────────────────────────────
# IN-MEMORY DEDUPLICATION
# Tracks message IDs already processed to prevent double replies
# on WhatsApp webhook retries
# ─────────────────────────────────────────────
_processed_message_ids: set[str] = set()


# ─────────────────────────────────────────────
# WEBHOOK VERIFICATION (GET)
# ─────────────────────────────────────────────
@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("Webhook verified!")
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ─────────────────────────────────────────────
# INCOMING MESSAGE HANDLER (POST)
# Returns 200 immediately, processes in background
# ─────────────────────────────────────────────
@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    if APP_SECRET:
        _verify_signature(request, body)

    data = await request.json()

    try:
        entry = data["entry"][0]["changes"][0]["value"]

        # Ignore status updates (delivered, read, etc.)
        if "messages" not in entry:
            return {"status": "ok"}

        message = entry["messages"][0]
        message_id = message.get("id", "")
        from_number = message["from"]
        msg_type = message.get("type", "")

        # Deduplicate: skip if this message was already processed (persistent check in Supabase)
        if message_id:
            if message_id in _processed_message_ids or await is_duplicate_message(message_id):
                print(f"Duplicate webhook ignored for message {message_id}")
                return {"status": "ok"}
            _processed_message_ids.add(message_id)
            if len(_processed_message_ids) > 1000:
                _processed_message_ids.clear()

        # Only handle text messages
        if msg_type != "text":
            background_tasks.add_task(
                send_whatsapp_message,
                from_number,
                "Sorry, I can only handle text messages right now."
            )
            return {"status": "ok"}

        user_text = message["text"]["body"]

        # Extract display name from webhook contacts field (provided by WhatsApp)
        contacts = entry.get("contacts", [])
        display_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""

        print(f"Message from {from_number} ({display_name or 'unknown'}): {user_text}")

        # Process and reply in background so WhatsApp gets 200 immediately
        background_tasks.add_task(process_and_reply, from_number, user_text, display_name, message_id)

    except (KeyError, IndexError) as e:
        print(f"Could not parse webhook payload: {e}")

    return {"status": "ok"}


# ─────────────────────────────────────────────
# BACKGROUND TASK: process message and send reply
# ─────────────────────────────────────────────
GREETING_MESSAGE = (
    "Welcome to Rushyendra Technologies and Services! "
    "We're here to assist you with information about our services, solutions, and company. "
    "Feel free to ask your questions anytime."
)

CONSULTATION_KEYWORDS = [
    "book a consultation", "book consultation", "consultation", "book appointment",
    "schedule a meeting", "book a meeting", "want to book", "i want to consult",
    "get a consultation", "request a consultation", "schedule consultation",
]

def _is_consultation_request(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CONSULTATION_KEYWORDS)


ADMIN_WHATSAPP_NUMBER = "919642991499"


async def _send_consultation_notification(user_name: str, user_phone: str, service: str):
    message = (
        f"*New Consultation Request* 📋\n\n"
        f"• *Name:* {user_name or 'Not provided'}\n"
        f"• *Phone:* +{user_phone}\n"
        f"• *Service Required:* {service}"
    )
    print(f"Sending consultation notification to {ADMIN_WHATSAPP_NUMBER}...")
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": ADMIN_WHATSAPP_NUMBER,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to send consultation notification: {resp.status_code} - {resp.text}")
        else:
            print(f"Consultation notification sent to {ADMIN_WHATSAPP_NUMBER}")


HUMAN_ASSIST_KEYWORDS = [
    "human", "agent", "person", "real person", "live agent", "staff",
    "speak to someone", "talk to someone", "talk to a person", "speak to a person",
    "customer support", "representative", "operator", "connect me", "call me",
    "human support", "human help", "need help from a person"
]

def _is_human_assist_request(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in HUMAN_ASSIST_KEYWORDS)


async def process_and_reply(from_number: str, user_text: str, display_name: str = "", message_id: str = ""):
    try:
        await save_message(from_number, "user", user_text, display_name, message_id)
        history = await get_conversation_history(from_number, limit=10)

        # Send greeting only on the very first message
        is_first_message = len(history) <= 1
        if is_first_message:
            await send_whatsapp_message(from_number, GREETING_MESSAGE)

        # Handle consultation booking flow
        consultation_state = await get_consultation_state(from_number)

        if consultation_state == "awaiting_service":
            # User just replied with their service requirement
            service = user_text.strip()
            await set_consultation_state(from_number, None)
            await _send_consultation_notification(display_name, from_number, service)
            reply = (
                "*Thank you! Your consultation request has been submitted.* ✅\n\n"
                f"• *Service Requested:* {service}\n\n"
                "Our team will reach out to you shortly on this number. "
                "If you need immediate assistance, you can also call us at *+91 96429 91499*. 📞"
            )
            await save_message(from_number, "assistant", reply)
            await send_whatsapp_message(from_number, reply)
            return

        if _is_consultation_request(user_text):
            await set_consultation_state(from_number, "awaiting_service")
            reply = (
                "*Great! We'd love to help you.* 😊\n\n"
                "Could you please tell me what kind of service you are looking for?\n\n"
                "For example:\n"
                "• Finance & Accounting\n"
                "• Tax & Compliance (GST, TDS, ROC)\n"
                "• HR & Payroll\n"
                "• BPO Services\n"
                "• Any other specific requirement"
            )
            await save_message(from_number, "assistant", reply)
            await send_whatsapp_message(from_number, reply)
            return

        # Handle human assistance requests
        if _is_human_assist_request(user_text):
            count = await increment_human_assist_count(from_number)
            if count <= 2:
                reply = (
                    "I'm here to help you! 😊 Please go ahead and ask me your question — "
                    "I'll do my best to assist you with information about Rushyendra Technologies and Services."
                )
            else:
                reply = (
                    "*Need to speak with our team directly?* 📞\n\n"
                    "You can reach us through:\n"
                    "• 📧 *Email:* info@rushyendra.com\n"
                    "• 📱 *Phone:* +91 96429 91499\n\n"
                    "Our team will be happy to assist you!"
                )
            await save_message(from_number, "assistant", reply)
            await send_whatsapp_message(from_number, reply)
            return

        ai_reply = await get_ai_response(user_text, history, from_number)
        await save_message(from_number, "assistant", ai_reply)
        await send_whatsapp_message(from_number, ai_reply)
    except Exception as e:
        print(f"Error processing message from {from_number}: {e}")


# ─────────────────────────────────────────────
# SEND MESSAGE VIA WHATSAPP CLOUD API
# ─────────────────────────────────────────────
async def send_whatsapp_message(to: str, text: str):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to send message: {resp.text}")
        else:
            print(f"Message sent to {to}")


# ─────────────────────────────────────────────
# SIGNATURE VERIFICATION (security)
# ─────────────────────────────────────────────
def _verify_signature(request: Request, body: bytes):
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "running", "service": "WhatsApp AI Chatbot"}
