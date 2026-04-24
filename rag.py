"""
RAG Retrieval
Embeds the user's message and finds relevant Q&A from the knowledge base in Supabase.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv
from database import get_client

load_dotenv()

_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBED_MODEL = "text-embedding-3-small"


def _get_embedding(text: str) -> list[float]:
    response = _openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding


async def retrieve_context(user_message: str, top_k: int = 3, threshold: float = 0.3) -> str:
    """
    Returns a formatted string of the most relevant Q&A pairs from the knowledge base.
    Returns empty string if nothing relevant is found.
    """
    try:
        embedding = _get_embedding(user_message)
        db = get_client()

        # pgvector requires the embedding as a formatted string "[x, y, z, ...]"
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        result = db.rpc("match_knowledge_base", {
            "query_embedding": embedding_str,
            "match_threshold": threshold,
            "match_count": top_k,
        }).execute()

        matches = result.data or []
        print(f"RAG: query='{user_message[:60]}' → {len(matches)} match(es) at threshold={threshold}")

        if not matches:
            return ""

        context_parts = [
            f"Q: {match['question']}\nA: {match['answer']}"
            for match in matches
        ]
        return "\n\n".join(context_parts)

    except Exception as e:
        print(f"RAG retrieval error: {e}")
        return ""
