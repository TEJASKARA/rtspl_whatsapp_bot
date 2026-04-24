# WhatsApp AI Chatbot — Rushyendra Technologies and Services

A production-ready WhatsApp AI chatbot built with FastAPI, LangChain, OpenAI, and Supabase. Deployed on Google Cloud Run.

## Architecture

```
WhatsApp User
     │  sends message
     ▼
Meta WhatsApp Cloud API
     │  POST /webhook
     ▼
FastAPI App  (Google Cloud Run)
     │
     ├── RAG (pgvector + OpenAI embeddings)  →  retrieves relevant company info
     ├── LangChain + GPT-4o-mini             →  generates AI reply
     ├── Supabase                            →  stores conversations & contacts
     └── WhatsApp Cloud API                  →  sends reply back
```

## Features

- **AI-powered replies** using GPT-4o-mini via LangChain with conversation memory
- **RAG (Retrieval-Augmented Generation)** — semantic search over a custom company knowledge base using OpenAI embeddings + pgvector
- **Consultation booking flow** — detects booking intent, collects service requirements, and notifies admin via WhatsApp
- **Human agent escalation** — gracefully handles requests to speak with a person
- **Duplicate message prevention** — in-memory + database deduplication for WhatsApp webhook retries
- **Webhook signature verification** — validates `X-Hub-Signature-256` for security
- **Async background processing** — returns 200 to WhatsApp immediately, processes and replies in background
- **First-message greeting** — sends a welcome message on a user's first interaction

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| AI / LLM | LangChain + OpenAI GPT-4o-mini |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector Search | Supabase pgvector |
| Database | Supabase (PostgreSQL) |
| Deployment | Google Cloud Run (Docker) |
| Messaging | Meta WhatsApp Cloud API |

## Project Structure

```
whatsapp-chatbot/
├── main.py              # FastAPI app, webhook handler, conversation flow logic
├── chatbot.py           # LangChain AI logic, system prompt, response generation
├── database.py          # Supabase read/write — messages, contacts, states
├── rag.py               # RAG retrieval — embeds query, searches pgvector
├── ingest.py            # One-time script to load knowledge_base.json into Supabase
├── knowledge_base.json  # Company Q&A pairs (used for RAG)
├── supbase_schema.sql   # Database schema — run once in Supabase SQL Editor
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container config for Cloud Run
└── .env                 # Secrets (never commit this)
```

## Setup

### Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project
- A [Meta Developer](https://developers.facebook.com) app with WhatsApp enabled
- An [OpenAI](https://platform.openai.com) API key
- [Google Cloud CLI](https://cloud.google.com/sdk/install) (for deployment)

### 1. Clone and install

```bash
git clone <repo-url>
cd whatsapp-chatbot

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file:

```env
WHATSAPP_TOKEN=your_whatsapp_access_token
WHATSAPP_PHONE_ID=your_phone_number_id
APP_SECRET=your_meta_app_secret
VERIFY_TOKEN=any_string_you_choose
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### 3. Set up Supabase database

1. Go to your Supabase dashboard → **SQL Editor → New Query**
2. Paste the contents of `supbase_schema.sql` and run it
3. Enable the `pgvector` extension: **Database → Extensions → vector**
4. Create the `knowledge_base` table and `match_knowledge_base` RPC function (see `supbase_schema.sql`)

### 4. Load the knowledge base

Add your company Q&A to `knowledge_base.json`:

```json
[
  { "question": "What services do you offer?", "answer": "We offer Finance & Accounting, Tax & Compliance, HR & Payroll, and BPO services." },
  ...
]
```

Then run the ingest script:

```bash
python ingest.py
```

Re-run this whenever `knowledge_base.json` changes.

### 5. Run locally

```bash
uvicorn main:app --reload --port 8000

# Test health check
curl http://localhost:8000/health
```

Use [ngrok](https://ngrok.com) to expose your local server for Meta webhook testing:

```bash
ngrok http 8000
```

### 6. Configure Meta webhook

1. Go to [Meta Developers](https://developers.facebook.com) → Your App → **WhatsApp → Configuration**
2. Set Callback URL to `https://your-url/webhook`
3. Set Verify Token to match `VERIFY_TOKEN` in your `.env`
4. Subscribe to the **messages** webhook field

### 7. Deploy to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud run deploy whatsapp-chatbot \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars "WHATSAPP_TOKEN=...,WHATSAPP_PHONE_ID=...,APP_SECRET=...,VERIFY_TOKEN=...,OPENAI_API_KEY=...,SUPABASE_URL=...,SUPABASE_SERVICE_ROLE_KEY=..."
```

Update the Meta webhook Callback URL to your Cloud Run service URL.

## Customization

**Change AI behavior** — edit `SYSTEM_PROMPT` in `chatbot.py`.

**Adjust conversation memory** — change `limit=10` in `main.py` (`get_conversation_history` call).

**Use a different LLM** — swap the model in `chatbot.py`:

```python
# Anthropic Claude
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-opus-4-7", api_key=os.getenv("ANTHROPIC_API_KEY"))

# Google Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))
```

**Add consultation keywords** — update `CONSULTATION_KEYWORDS` list in `main.py`.

## Cost Estimate

| Service | Free Tier | Paid (approx) |
|---|---|---|
| Google Cloud Run | 2M req/month | ~$0.40/1M req |
| OpenAI GPT-4o-mini | — | ~$0.15/1M tokens |
| OpenAI Embeddings | — | ~$0.02/1M tokens |
| Supabase | 500MB free | $25/month (Pro) |
| WhatsApp API | 1000 conversations/month | $0.005–0.08/conversation |

For under 1000 users/day, total cost is typically **under $10/month**.

## Troubleshooting

| Problem | Solution |
|---|---|
| Webhook verification fails | Ensure `VERIFY_TOKEN` matches exactly in `.env` and Meta dashboard |
| Messages not received | Subscribe to `messages` webhook field in Meta |
| Supabase errors | Use `service_role` key, not `anon` key |
| RAG returning no results | Lower `threshold` in `rag.py` (default `0.3`) or re-run `ingest.py` |
| Cloud Run 500 errors | Check logs: `gcloud run logs read --service=whatsapp-chatbot` |
| Bot not replying | Check Cloud Run logs for LangChain/OpenAI errors |
