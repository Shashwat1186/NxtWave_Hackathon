"""
services/pipeline.py
====================
Compiles and runs the CivicTriage LangGraph pipeline.

Graph topology:
  intake_guard
      ↓ (rejected / failed → terminal_reject)
  perceive
      ↓
  geo_resolver
      ↓
  deduplicator
      ↓
  severity_scorer
      ↓
  authority_router
      ↓
  critic
      ↓ (pass    → dispatcher → terminal_done)
      ↓ (retry   → perceive OR authority_router)
      ↓ (give up → terminal_human_review)

All node functions are wrapped with functools.partial to inject
dependencies (llm, db, bus, services) without global state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache, partial
from typing import Any, Optional

from bson import ObjectId
from langgraph.graph import END, StateGraph

from app.agents.nodes.authority_router import authority_router
from app.agents.nodes.critic import critic
from app.agents.nodes.deduplicator import deduplicator
from app.agents.nodes.dispatcher import dispatcher
from app.agents.nodes.geo_resolver import geo_resolver
from app.agents.nodes.intake_guard import intake_guard
from app.agents.nodes.perceive import perceive
from app.agents.nodes.severity_scorer import severity_scorer
from app.core.config import get_settings
from app.core.database import get_db
from app.core.llm_client import get_llm_client
from app.core.sse_bus import ProgressEvent, SSEBus, get_bus
from app.models.graph_state import CivicTriageState, make_initial_state

logger = logging.getLogger(__name__)


# ── Conditional edge functions ────────────────────────────────────────────────

def _route_after_intake(state: CivicTriageState) -> str:
    if state.get("final_status") in ("rejected", "failed"):
        return "terminal_reject"
    return "perceive"


def _route_after_perceive(state: CivicTriageState) -> str:
    if state.get("final_status") in ("rejected", "failed"):
        return "terminal_reject"
    perc = state.get("perception_output")
    if perc and perc.image_matches_description is False:
        return "terminal_reject"
    return "geo_resolver"


def _route_after_critic(state: CivicTriageState) -> str:
    settings = get_settings()

    critic_out = state.get("critic_output")
    final_status = state.get("final_status")

    if critic_out and critic_out.passed:
        return "dispatcher"

    # Exhausted retries: if core outputs exist, proceed to dispatcher so ticket is created
    if state.get("retry_count", 0) >= settings.CRITIC_MAX_RETRIES:
        if state.get("perception_output") and state.get("geo_output") and state.get("router_output"):
            logger.info("Pipeline: max retries reached but core outputs present — proceeding to dispatcher")
            return "dispatcher"
        return "terminal_human_review"

    # Already routed to human review by critic node
    if final_status == "human_review":
        return "terminal_human_review"

    if critic_out is None or state.get("critic_error"):
        return "terminal_human_review"

    retry_target = critic_out.retry_target
    if retry_target == "perceive":
        return "perceive"
    if retry_target == "authority_router":
        return "authority_router"

    # No actionable retry target (e.g., geo issue or clarifying question) → human review
    return "terminal_human_review"


# ── Terminal nodes ────────────────────────────────────────────────────────────

async def _terminal_reject(state: CivicTriageState, *, bus: SSEBus) -> dict:
    """Terminal: report was rejected or pipeline failed before processing."""
    report_id = state["report_id"]
    reason = (
        state.get("rejection_reason")
        or (state["intake_output"].rejection_reason if state.get("intake_output") and state.get("intake_output").rejection_reason else None)
        or (state["perception_output"].mismatch_reason if state.get("perception_output") and state.get("perception_output").mismatch_reason else None)
        or "pipeline_failed"
    )
    final_status = state.get("final_status", "rejected")

    # Update MongoDB reports collection
    try:
        db = await get_db()
        now = datetime.now(timezone.utc)
        await db.reports.update_one(
            {"_id": report_id},
            {"$set": {"status": final_status, "rejection_reason": reason, "updated_at": now}},
        )
    except Exception as exc:
        logger.error("terminal_reject DB update failed for %s: %s", report_id, exc)

    await bus.publish(report_id, ProgressEvent(
        node="__terminal__",
        status="error",
        message=f"Report {final_status}: {reason}",
        data={"final_status": final_status, "rejection_reason": reason},
    ))
    await bus.complete(report_id)
    return {}


async def _terminal_human_review(state: CivicTriageState, *, bus: SSEBus, db) -> dict:
    """Terminal: critic gave up — write to human_review queue."""
    report_id = state["report_id"]
    now = datetime.now(timezone.utc)

    # Write human review record
    try:
        await db.events.insert_one({
            "event_type": "human_review_queued",
            "report_id": report_id,
            "issue_id": state.get("issue_id"),
            "ticket_id": None,
            "node": "terminal_human_review",
            "actor": "system",
            "data": {
                "critic_findings": [
                    f.model_dump()
                    for f in (state["critic_output"].findings if state.get("critic_output") else [])
                ],
                "retry_count": state.get("retry_count", 0),
            },
            "error": None,
            "timestamp": now,
        })
        # Update report status
        await db.reports.update_one(
            {"_id": report_id},
            {"$set": {"status": "human_review", "updated_at": now}},
        )
        # Ensure issue record also retains computed severity score and status
        issue_id = state.get("issue_id")
        sev = state.get("severity_output")
        if issue_id and sev:
            raw_sid = str(issue_id).strip()
            oid_filter = (
                {"$or": [{"_id": ObjectId(raw_sid)}, {"_id": raw_sid}]}
                if ObjectId.is_valid(raw_sid)
                else {"_id": raw_sid}
            )
            await db.issues.update_one(
                oid_filter,
                {"$set": {
                    "priority_score": sev.priority_score,
                    "severity_tier": sev.severity_tier.value,
                    "score_breakdown": sev.score_breakdown.model_dump() if sev.score_breakdown else {},
                    "sla_hours": sev.sla_hours,
                    "status": "in_review",
                    "updated_at": now,
                }},
            )
    except Exception as exc:
        logger.error("human_review DB write failed for %s: %s", report_id, exc)

    await bus.publish(report_id, ProgressEvent(
        node="__terminal__",
        status="human_review",
        message="Your report has been queued for manual review. We will follow up shortly.",
        data={"final_status": "human_review"},
    ))
    await bus.complete(report_id)
    return {"final_status": "human_review"}


async def _terminal_done(state: CivicTriageState, *, bus: SSEBus) -> dict:
    """Terminal: pipeline completed successfully."""
    report_id = state["report_id"]
    await bus.publish(report_id, ProgressEvent(
        node="__terminal__",
        status="complete",
        message="Pipeline complete. Ticket has been created.",
        data={
            "final_status": "dispatched",
            "ticket_id": state.get("ticket_id"),
            "issue_id": state.get("issue_id"),
        },
    ))
    await bus.complete(report_id)
    return {}


# ── Pipeline runner ───────────────────────────────────────────────────────────

class PipelineRunner:
    """
    Compiles the LangGraph graph and provides an async run() method.
    The graph is compiled lazily on first run and cached.
    """

    def __init__(self):
        self._compiled = None

    async def _build_graph(self):
        """Build and compile the StateGraph. Called once and cached."""
        if self._compiled is not None:
            return self._compiled

        db = await get_db()
        llm = get_llm_client()
        bus = get_bus()

        # Import services here to avoid circular imports at module load
        try:
            from app.services.geo_service import GeoService
            from app.services.embed_service import EmbedService
        except ImportError:
            from .geo_service import GeoService
            from .embed_service import EmbedService

        geo_service = GeoService(db=db)
        embed_service = EmbedService(llm=llm)
        # NOTE: kb_service removed — authority_router now uses rule-based engine

        nodes = {
            "intake_guard":       partial(intake_guard, llm=llm, bus=bus),
            "perceive":           partial(perceive, llm=llm, bus=bus),
            "geo_resolver":       partial(geo_resolver, bus=bus, geo_service=geo_service),
            "deduplicator":       partial(deduplicator, bus=bus, db=db, embed_service=embed_service),
            "severity_scorer":    partial(severity_scorer, llm=llm, bus=bus, db=db),
            "authority_router":   partial(authority_router, llm=llm, bus=bus, db=db),
            "critic":             partial(critic, bus=bus, db=db),
            "dispatcher":         partial(dispatcher, llm=llm, bus=bus, db=db),
            "terminal_reject":    partial(_terminal_reject, bus=bus),
            "terminal_human_review": partial(_terminal_human_review, bus=bus, db=db),
            "terminal_done":      partial(_terminal_done, bus=bus),
        }

        g = StateGraph(CivicTriageState)
        for name, fn in nodes.items():
            g.add_node(name, fn)

        g.set_entry_point("intake_guard")
        g.add_conditional_edges("intake_guard", _route_after_intake, {
            "terminal_reject": "terminal_reject",
            "perceive": "perceive",
        })
        g.add_conditional_edges("perceive", _route_after_perceive, {
            "terminal_reject": "terminal_reject",
            "geo_resolver": "geo_resolver",
        })
        g.add_edge("geo_resolver", "deduplicator")
        g.add_edge("deduplicator", "severity_scorer")
        g.add_edge("severity_scorer", "authority_router")
        g.add_edge("authority_router", "critic")
        g.add_conditional_edges("critic", _route_after_critic, {
            "dispatcher": "dispatcher",
            "perceive": "perceive",
            "authority_router": "authority_router",
            "terminal_human_review": "terminal_human_review",
        })
        g.add_edge("dispatcher", "terminal_done")
        g.add_edge("terminal_reject", END)
        g.add_edge("terminal_human_review", END)
        g.add_edge("terminal_done", END)

        self._compiled = g.compile()
        logger.info("LangGraph pipeline compiled successfully")
        return self._compiled

    async def run(
        self,
        report_id: str,
        file_path: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        file_mime_type: Optional[str] = None,
        voice_file_bytes: Optional[bytes] = None,
        voice_file_mime_type: Optional[str] = None,
        raw_text: Optional[str] = None,
        gps_lat: Optional[float] = None,
        gps_lng: Optional[float] = None,
    ) -> Optional[CivicTriageState]:
        """
        Execute the pipeline for a single report.
        Called as an asyncio background task from the API router.
        Returns the final graph state (or None on crash).
        """
        bus = get_bus()
        try:
            graph = await self._build_graph()
            initial = make_initial_state(
                report_id=report_id,
                file_path=file_path,
                file_bytes=file_bytes,
                file_mime_type=file_mime_type,
                voice_file_bytes=voice_file_bytes,
                voice_file_mime_type=voice_file_mime_type,
                raw_text=raw_text,
                gps_lat=gps_lat,
                gps_lng=gps_lng,
            )
            logger.info("Pipeline starting for report_id=%s", report_id)
            final_state = await graph.ainvoke(initial)
            logger.info("Pipeline complete for report_id=%s", report_id)
            return final_state
        except Exception as exc:
            logger.exception("Pipeline crashed for report_id=%s", report_id)
            try:
                await bus.publish(report_id, ProgressEvent(
                    node="__pipeline__", status="error",
                    message="An unexpected error occurred. Your report has been saved.",
                ))
                await bus.complete(report_id)
            except Exception:
                pass
            return None


@lru_cache(maxsize=1)
def get_pipeline_runner() -> PipelineRunner:
    """Singleton PipelineRunner."""
    return PipelineRunner()
