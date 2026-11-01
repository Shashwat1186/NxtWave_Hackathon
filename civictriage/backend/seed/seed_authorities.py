"""
seed/seed_authorities.py
=========================
Seeds the MongoDB `authorities` and `kb_chunks` collections.

Usage:
    cd backend/
    python seed/seed_authorities.py

Reads:
  - seed/authorities.json   → authorities collection
  - kb/*.md                 → kb_chunks collection (split into chunks, embedded)

Requires MONGODB_URI and GOOGLE_API_KEY (or OPENAI_API_KEY) in .env
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.core.database import connect_db, disconnect_db, get_db
from app.core.llm_client import get_llm_client
from app.services.embed_service import EmbedService


CHUNK_SIZE = 400    # characters per KB chunk
CHUNK_OVERLAP = 50  # character overlap between chunks


def _split_into_chunks(text: str, source: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end].strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if len(c) > 50]  # drop tiny trailing chunks


async def seed_authorities(db) -> None:
    """Insert authority documents from authorities.json."""
    seed_file = Path(__file__).parent / "authorities.json"
    if not seed_file.exists():
        print(f"WARNING: {seed_file} not found. Skipping authorities seed.")
        return

    authorities = json.loads(seed_file.read_text())
    if authorities:
        await db.authorities.delete_many({})
        result = await db.authorities.insert_many(authorities)
        print(f"Seeded {len(result.inserted_ids)} authorities")


async def seed_kb_chunks(db, embed_service: EmbedService) -> None:
    """Chunk and embed all statutory charters using the unified chunking engine."""
    chunks_file = Path(__file__).parent / "kb_chunks.json"
    if not chunks_file.exists():
        from seed.chunk_kb import build_kb_chunks
        chunks = build_kb_chunks()
    else:
        chunks = json.loads(chunks_file.read_text(encoding="utf-8"))

    if not chunks:
        print("WARNING: No chunks available. Skipping KB seed.")
        return

    await db.kb_chunks.delete_many({})
    print(f"Embedding {len(chunks)} KB chunks...")
    texts = [c["text"] for c in chunks]
    embeddings = await embed_service.embed_batch(texts, concurrency=3)

    docs = []
    now = datetime.now(timezone.utc)
    for chunk, embedding in zip(chunks, embeddings):
        d = dict(chunk)
        d["embedding"] = embedding
        d["created_at"] = now
        docs.append(d)

    if docs:
        result = await db.kb_chunks.insert_many(docs)
        print(f"Seeded {len(result.inserted_ids)} KB chunks into MongoDB Atlas")


async def main():
    await connect_db()
    db = await get_db()
    llm = get_llm_client()
    embed_service = EmbedService(llm)

    print("Seeding authorities...")
    await seed_authorities(db)

    print("Seeding KB chunks...")
    await seed_kb_chunks(db, embed_service)

    await disconnect_db()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

