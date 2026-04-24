"""
Knowledge Base Ingest Script
Loads knowledge_base.json into Supabase with OpenAI embeddings.

Run once to set up:     python ingest.py
Re-run whenever knowledge_base.json changes.
"""

import json
import os
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = "text-embedding-3-small"

openai_client = OpenAI(api_key=OPENAI_API_KEY)
db = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding


def ingest():
    with open("knowledge_base.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} Q&A pairs.")
    print("Clearing existing knowledge base...")
    db.table("knowledge_base").delete().neq("id", 0).execute()

    print("Generating embeddings and uploading...\n")
    for i, item in enumerate(data):
        # Embed question + answer together for richer semantic matching
        text_to_embed = f"Question: {item['question']}\nAnswer: {item['answer']}"
        embedding = get_embedding(text_to_embed)

        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        db.table("knowledge_base").insert({
            "question": item["question"],
            "answer": item["answer"],
            "embedding": embedding_str,
        }).execute()

        print(f"  [{i + 1}/{len(data)}] {item['question'][:70]}")

    print(f"\nDone! {len(data)} entries uploaded to Supabase.")


if __name__ == "__main__":
    ingest()
