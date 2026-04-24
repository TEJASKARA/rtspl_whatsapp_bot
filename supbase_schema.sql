-- ─────────────────────────────────────────────────────────────
-- WhatsApp Chatbot — Supabase Database Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ─────────────────────────────────────────────────────────────


-- 1. CONTACTS TABLE
--    One row per unique WhatsApp number
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id              BIGSERIAL PRIMARY KEY,
    phone_number    TEXT UNIQUE NOT NULL,          -- e.g. "919876543210"
    display_name    TEXT,                          -- optional, set later if needed
    last_seen       TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'::JSONB       -- flexible extra fields
);

-- Index for fast lookups by phone number
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone_number);


-- 2. MESSAGES TABLE
--    One row per message (user or assistant)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    phone_number    TEXT NOT NULL REFERENCES contacts(phone_number) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast conversation history queries
CREATE INDEX IF NOT EXISTS idx_messages_phone     ON messages(phone_number);
CREATE INDEX IF NOT EXISTS idx_messages_phone_time ON messages(phone_number, created_at DESC);


-- 3. ENABLE ROW LEVEL SECURITY (best practice)
-- ─────────────────────────────────────────────────────────────
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Since your backend uses the service role key, it bypasses RLS automatically.
-- The policies below block any accidental public access via the anon key.
CREATE POLICY "No public access to contacts"
    ON contacts FOR ALL USING (false);

CREATE POLICY "No public access to messages"
    ON messages FOR ALL USING (false);


-- 4. HANDY VIEWS (optional, for inspecting data in dashboard)
-- ─────────────────────────────────────────────────────────────

-- Latest message per contact (useful overview)
CREATE OR REPLACE VIEW contact_summary AS
SELECT
    c.phone_number,
    c.display_name,
    c.last_seen,
    c.created_at AS first_seen,
    COUNT(m.id)  AS total_messages,
    MAX(m.created_at) AS last_message_at,
    (SELECT content FROM messages m2
     WHERE m2.phone_number = c.phone_number
     ORDER BY created_at DESC LIMIT 1) AS last_message
FROM contacts c
LEFT JOIN messages m ON m.phone_number = c.phone_number
GROUP BY c.phone_number, c.display_name, c.last_seen, c.created_at
ORDER BY last_message_at DESC NULLS LAST;