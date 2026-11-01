"""
core/sse_bus.py
===============
In-process Server-Sent Events bus keyed by report_id.

Each pipeline run pushes ProgressEvent objects into an asyncio.Queue.
The SSE endpoint (/reports/{id}/stream) reads from that queue and
formats the events as 'text/event-stream'.

NOTE: This in-process bus works for a single-worker deployment (hackathon scope).
For multi-worker deployments, replace with Redis Streams or similar.

Usage (in a pipeline node):
    from app.core.sse_bus import get_bus
    bus = get_bus()
    await bus.publish(report_id, ProgressEvent(node="perceive", status="running", message="..."))

Usage (in the SSE endpoint):
    async for event in bus.subscribe(report_id):
        yield event
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals stream completion


class ProgressEvent(BaseModel):
    """Emitted by each agent node; streamed to the client via SSE."""
    node: str
    status: str                    # "running" | "done" | "error" | "retrying" | "human_review"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_sse(self) -> str:
        """Format as SSE text/event-stream chunk."""
        payload = self.model_dump_json()
        return f"data: {payload}\n\n"


class SSEBus:
    """
    In-memory pub/sub bus.
    One Queue[ProgressEvent | sentinel] per active report_id.
    """

    def __init__(self) -> None:
        # WeakValueDictionary auto-cleans up queues when no subscriber holds a ref
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_or_create_queue(self, report_id: str) -> asyncio.Queue:
        if report_id not in self._queues:
            self._queues[report_id] = asyncio.Queue(maxsize=256)
        return self._queues[report_id]

    async def publish(self, report_id: str, event: ProgressEvent) -> None:
        """Push an event to all subscribers of this report_id."""
        q = self._get_or_create_queue(report_id)
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for report_id=%s; dropping event", report_id)

    async def complete(self, report_id: str) -> None:
        """Signal that the pipeline has finished (closes the SSE stream)."""
        q = self._get_or_create_queue(report_id)
        q.put_nowait(_SENTINEL)

    async def subscribe(self, report_id: str) -> AsyncIterator[str]:
        """
        Async generator that yields SSE-formatted strings.
        Exits when the pipeline calls complete().
        """
        q = self._get_or_create_queue(report_id)
        try:
            while True:
                item = await asyncio.wait_for(q.get(), timeout=60.0)
                if item is _SENTINEL:
                    yield "data: {\"node\": \"__done__\", \"status\": \"complete\"}\n\n"
                    break
                assert isinstance(item, ProgressEvent)
                yield item.to_sse()
        except asyncio.TimeoutError:
            logger.warning("SSE subscription timed out for report_id=%s", report_id)
            yield "data: {\"node\": \"__timeout__\", \"status\": \"error\"}\n\n"
        finally:
            # Clean up queue if empty after subscriber exits
            if report_id in self._queues and self._queues[report_id].empty():
                del self._queues[report_id]


# ── Singleton ─────────────────────────────────────────────────────────────────

_bus: SSEBus | None = None


def get_bus() -> SSEBus:
    global _bus
    if _bus is None:
        _bus = SSEBus()
    return _bus

