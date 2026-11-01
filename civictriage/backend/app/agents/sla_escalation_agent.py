"""
agents/sla_escalation_agent.py
================================
Standalone SLA escalation agent.

Can be triggered:
  1. Manually via POST /internal/sla-sweep
  2. On a schedule (cron job or APScheduler task)

This module provides the run() coroutine that wraps SLAService.sweep().
It can be invoked from the API router or from a scheduled task runner.

Every escalation produces:
  - A new TicketStatusHistoryEntry ("escalated")
  - An EventDoc in the events audit log
  - Updated authority leaderboard score (is_publicly_flagged)
  - SSE event to any active dashboard subscribers (future enhancement)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.llm_client import get_llm_client
from app.services.sla_service import SLAService

logger = logging.getLogger(__name__)


async def run_sla_sweep() -> dict:
    """
    Entry point for the SLA escalation agent.
    Called from POST /internal/sla-sweep or a scheduler.

    Returns:
        Summary dict from SLAService.sweep()
    """
    db = await get_db()
    llm = get_llm_client()
    service = SLAService(db=db, llm=llm)

    logger.info("SLA escalation agent starting at %s", datetime.now(timezone.utc).isoformat())
    result = await service.sweep()
    logger.info("SLA escalation agent finished: %s", result)
    return result

