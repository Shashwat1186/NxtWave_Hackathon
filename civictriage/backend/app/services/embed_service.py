"""
services/embed_service.py
==========================
Embedding generation and cosine similarity helpers.

Wraps the LLM client's embed() method with:
- Batch support (for seeding KB chunks)
- In-memory LRU cache to avoid redundant API calls within a run
- Cosine similarity utility

Usage:
    from app.services.embed_service import EmbedService
    embed_svc = EmbedService(llm_client)
    vec = await embed_svc.embed("pothole on main road near school")
    score = embed_svc.cosine_similarity(vec1, vec2)
"""

from __future__ import annotations

import asyncio
import math

from app.core.llm_client import LLMClient


class EmbedService:
    """
    Thin wrapper around LLMClient.embed() with caching and utilities.
    """

    def __init__(self, llm: LLMClient, cache_size: int = 512):
        self._llm = llm
        self._cache: dict[str, list[float]] = {}
        self._cache_size = cache_size

    async def embed(self, text: str) -> list[float]:
        """Return embedding vector for text, using in-process cache."""
        if text in self._cache:
            return self._cache[text]
        vec = await self._llm.embed(text)
        if len(self._cache) >= self._cache_size:
            # Evict oldest entry (simple FIFO)
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = vec
        return vec

    async def embed_batch(self, texts: list[str], concurrency: int = 5) -> list[list[float]]:
        """
        Embed multiple texts with bounded concurrency.
        Used by the KB seeding script.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _embed_one(text: str) -> list[float]:
            async with sem:
                return await self.embed(text)

        return await asyncio.gather(*[_embed_one(t) for t in texts])

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

