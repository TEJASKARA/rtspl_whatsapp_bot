"""
LangChain Chatbot Logic
Handles AI responses using conversation history from Supabase + RAG from knowledge base.
"""

import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from dotenv import load_dotenv

from rag import retrieve_context

load_dotenv()

# ─────────────────────────────────────────────
# LLM SETUP
# ─────────────────────────────────────────────
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY"),
)

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are a professional and friendly WhatsApp assistant for Rushyendra Technologies and Services.

Your Role:
- You are a chatbot integrated into the Rushyendra Technologies and Services platform.
- You help users understand what the company does and how it can help with their needs.

Formatting Rules (strictly follow these for every reply):
- Use WhatsApp formatting to make replies look clean and professional.
- Use *bold* (asterisks) for headings, key terms, and important points.
- Use bullet points with • for listing items or features.
- Keep paragraphs short — max 2-3 lines each.
- Add a relevant emoji at the start of each section or key point to make the message visually appealing.
- End every reply with a helpful closing line like "Feel free to ask if you have more questions! 😊"
- Never use markdown headers (## or ###) — WhatsApp does not support them.

Example of a good reply format:
*Our Services* 🛠️
• Finance & Accounting
• Tax & Compliance
• HR Services
• BPO Services

*Why Choose Us?* ✅
• 100% accuracy guaranteed
• Qualified CA, CS, CMA team
• Full statutory compliance

Feel free to ask if you have more questions! 😊

Instructions:
- Reply in the same language the user writes in.
- If the user sends a greeting (e.g. hi, hello, hey, good morning), respond warmly and invite them to ask about Rushyendra Technologies and Services.
- If the user asks about Rushyendra Technologies, refer to the COMPANY INFORMATION provided and answer in the formatted style above.
- You can answer questions similar in meaning to the knowledge base — match intent, not just exact wording.
- If the question is not related to Rushyendra Technologies and Services, reply exactly: "I'm here to help with questions about Rushyendra Technologies and Services. Please ask only queries related to our services, company, or offerings."
- If the question is related but you lack the information, reply exactly: "I currently don't have the information to answer that. Please contact us directly at info@rushyendra.com and our team will be happy to help you."

Don'ts:
- Do NOT answer anything unrelated to Rushyendra Technologies and Services.
- Do NOT use markdown headers (##, ###).
- Do NOT write long unbroken paragraphs.

Always reply in the same language the user writes in."""


# ─────────────────────────────────────────────
# PROMPT TEMPLATE (dynamic system prompt for RAG)
# ─────────────────────────────────────────────
prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}"),
])

chain = prompt | llm


# ─────────────────────────────────────────────
# CONVERT SUPABASE HISTORY → LANGCHAIN MESSAGES
# ─────────────────────────────────────────────
def build_message_history(history: list[dict]) -> ChatMessageHistory:
    chat_history = ChatMessageHistory()
    for msg in history:
        if msg["role"] == "user":
            chat_history.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            chat_history.add_ai_message(msg["content"])
    return chat_history


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────
async def get_ai_response(user_message: str, history: list[dict], phone_number: str) -> str:
    """
    user_message: latest message from the user
    history: list of past messages from Supabase (oldest first)
    phone_number: for logging purposes
    """
    try:
        lc_history = build_message_history(history)

        # Retrieve semantically similar Q&A from knowledge base
        context = await retrieve_context(user_message)

        if context:
            system_with_context = (
                SYSTEM_PROMPT
                + "\n\n---\nCOMPANY INFORMATION (use this to answer accurately):\n"
                + context
                + "\n---"
            )
            print(f"RAG: {context.count('Q:')} match(es) found for {phone_number}")
        else:
            system_with_context = SYSTEM_PROMPT
            print(f"RAG: no matches found for {phone_number}")

        response = await chain.ainvoke({
            "system_prompt": system_with_context,
            "input": user_message,
            "history": lc_history.messages,
        })

        reply = response.content.strip()
        print(f"AI reply to {phone_number}: {reply[:80]}...")
        return reply

    except Exception as e:
        print(f"LangChain error: {e}")
        return "Sorry, I'm having trouble right now. Please try again in a moment. 🙏"
