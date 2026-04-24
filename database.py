"""
Supabase Database Layer
Stores and retrieves WhatsApp conversations
"""

import os
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")   # Use service role key (server-side)

# Lazy init — created once on first use
_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─────────────────────────────────────────────
# UPSERT CONTACT
# Creates or updates a contact record for the phone number
# ─────────────────────────────────────────────
async def upsert_contact(phone_number: str, display_name: str = None):
    db = get_client()
    data = {"phone_number": phone_number, "last_seen": datetime.utcnow().isoformat()}
    if display_name:
        data["display_name"] = display_name
    db.table("contacts").upsert(data, on_conflict="phone_number").execute()


# ─────────────────────────────────────────────
# SAVE MESSAGE
# Inserts a single message row into the messages table
# ─────────────────────────────────────────────
async def is_duplicate_message(whatsapp_message_id: str) -> bool:
    """Returns True if this WhatsApp message ID was already processed."""
    db = get_client()
    result = (
        db.table("messages")
        .select("id")
        .eq("whatsapp_message_id", whatsapp_message_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


async def save_message(phone_number: str, role: str, content: str, display_name: str = None, whatsapp_message_id: str = None):
    """
    role: "user" or "assistant"
    """
    db = get_client()

    # Make sure the contact exists first
    await upsert_contact(phone_number, display_name)

    row = {
        "phone_number": phone_number,
        "role": role,
        "content": content,
        "created_at": datetime.utcnow().isoformat(),
    }
    if whatsapp_message_id:
        row["whatsapp_message_id"] = whatsapp_message_id

    db.table("messages").insert(row).execute()
    print(f"💾 Saved [{role}] message for {phone_number}")


# ─────────────────────────────────────────────
# GET CONVERSATION HISTORY
# Returns the last N messages for a phone number (oldest first)
# ─────────────────────────────────────────────
async def get_conversation_history(phone_number: str, limit: int = 10) -> list[dict]:
    """
    Returns list of {"role": ..., "content": ...} dicts, oldest first.
    """
    db = get_client()

    result = (
        db.table("messages")
        .select("role, content, created_at")
        .eq("phone_number", phone_number)
        .order("created_at", desc=True)       # latest first
        .limit(limit)
        .execute()
    )

    messages = result.data or []
    messages.reverse()                         # flip to oldest-first for LangChain
    return [{"role": m["role"], "content": m["content"]} for m in messages]


# ─────────────────────────────────────────────
# HUMAN ASSIST COUNT
# Tracks how many times a user has asked for a human agent
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# CONSULTATION STATE
# Tracks whether a user is mid-booking flow
# ─────────────────────────────────────────────
async def get_consultation_state(phone_number: str) -> str | None:
    db = get_client()
    result = db.table("contacts").select("metadata").eq("phone_number", phone_number).execute()
    if result.data:
        metadata = result.data[0].get("metadata") or {}
        return metadata.get("consultation_state")
    return None


async def set_consultation_state(phone_number: str, state: str | None):
    db = get_client()
    result = db.table("contacts").select("metadata").eq("phone_number", phone_number).execute()
    metadata = {}
    if result.data:
        metadata = result.data[0].get("metadata") or {}
    if state is None:
        metadata.pop("consultation_state", None)
    else:
        metadata["consultation_state"] = state
    db.table("contacts").update({"metadata": metadata}).eq("phone_number", phone_number).execute()


async def get_human_assist_count(phone_number: str) -> int:
    db = get_client()
    result = db.table("contacts").select("metadata").eq("phone_number", phone_number).execute()
    if result.data:
        metadata = result.data[0].get("metadata") or {}
        return metadata.get("human_assist_requests", 0)
    return 0


async def increment_human_assist_count(phone_number: str) -> int:
    db = get_client()
    result = db.table("contacts").select("metadata").eq("phone_number", phone_number).execute()
    metadata = {}
    if result.data:
        metadata = result.data[0].get("metadata") or {}
    count = metadata.get("human_assist_requests", 0) + 1
    metadata["human_assist_requests"] = count
    db.table("contacts").update({"metadata": metadata}).eq("phone_number", phone_number).execute()
    return count


# ─────────────────────────────────────────────
# GET ALL CONTACTS  (optional admin utility)
# ─────────────────────────────────────────────
async def get_all_contacts() -> list[dict]:
    db = get_client()
    result = db.table("contacts").select("*").order("last_seen", desc=True).execute()
    return result.data or []