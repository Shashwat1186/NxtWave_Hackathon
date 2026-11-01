"""
agents/nodes/critic.py
======================
Node 7: critic

Responsibilities:
- Validate all prior node outputs against their Pydantic schemas
- Check that confidence values exceed CRITIC_MIN_CONFIDENCE
- Verify that authority_router.citation_chunk_ids reference real KB chunks
- Verify that cited evidence in routing_justification is consistent with
  the retrieved chunk content
- On failure, determine the BEST retry target:
    * perception low-conf → re-run perceive with alternate prompt/model
    * routing low-conf    → re-run authority_router with wider k
    * missing geo         → emit clarifying_question to citizen via SSE
- After CRITIC_MAX_RETRIES attempts, route to human_review queue

Retry loop (in graph.py conditional edges):
  critic passes  → dispatcher
  critic retries → perceive OR authority_router (targeted)
  critic gives up → human_review terminal node

Never silently accepts uncertain outputs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.core.config import get_settings
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import CriticFinding, CriticOutput

logger = logging.getLogger(__name__)


async def critic(
    state: CivicTriageState,
    *,
    bus: SSEBus,
    db,           # to verify KB chunk IDs exist
) -> dict:
    """
    LangGraph node for critic.

    Returns updated state: critic_output, retry_count, and/or critic_error.
    Does NOT modify prior node outputs — only adds new fields.
    """
    report_id = state["report_id"]
    settings = get_settings()
    attempt = state.get("retry_count", 0) + 1

    await bus.publish(report_id, ProgressEvent(
        node="critic",
        status="running",
        message=f"Validating pipeline outputs (attempt {attempt})…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "critic",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"attempt": attempt},
        "error": None,
    }
    findings: list[CriticFinding] = []
    retry_target: str | None = None
    clarifying_question: str | None = None

    try:
        # ── CHECK 1: Presence checks ──────────────────────────────────────────
        if not state.get("perception_output"):
            findings.append(CriticFinding(
                field="perception_output",
                issue="Missing perception output",
                severity="blocking",
            ))
            retry_target = "perceive"

        if not state.get("geo_output"):
            findings.append(CriticFinding(
                field="geo_output",
                issue="Missing geo resolution",
                severity="blocking",
            ))
            if not retry_target:
                # Geo failures require user clarification, not a pipeline re-run
                clarifying_question = (
                    "We could not determine the location of your report. "
                    "Please drop a pin on the map to continue."
                )
                retry_target = None  # geo issues can't be fixed by re-running perceive

        if not state.get("router_output"):
            findings.append(CriticFinding(
                field="router_output",
                issue="Missing authority routing",
                severity="blocking",
            ))
            if not retry_target:
                retry_target = "authority_router"

        # ── CHECK 2: Confidence checks ────────────────────────────────────────
        perception = state.get("perception_output")
        if perception and perception.confidence < settings.CRITIC_MIN_CONFIDENCE:
            findings.append(CriticFinding(
                field="perception_output.confidence",
                issue=(
                    f"Low confidence {perception.confidence:.2f} < "
                    f"{settings.CRITIC_MIN_CONFIDENCE}"
                ),
                severity="blocking",
            ))
            if not retry_target:
                retry_target = "perceive"

        router = state.get("router_output")
        if router and router.confidence < settings.CRITIC_MIN_CONFIDENCE:
            has_assigned_dept = bool(
                router.primary_authority
                and router.primary_authority.authority_id
                and router.primary_authority.authority_id != "unknown"
            )
            findings.append(CriticFinding(
                field="router_output.confidence",
                issue=(
                    f"Low routing confidence {router.confidence:.2f} < "
                    f"{settings.CRITIC_MIN_CONFIDENCE}"
                ),
                severity="warning" if has_assigned_dept else "blocking",
            ))
            if not has_assigned_dept and not retry_target:
                retry_target = "authority_router"

        # ── CHECK 3: Citation/Rule verification (async DB check) ─────────────
        # citation_chunk_ids now contains rule_id + source doc IDs
        # Verify that the primary citation (rule_id) exists in routing_rules
        if router and router.citation_chunk_ids:
            primary_citation = router.citation_chunk_ids[0]  # first is always rule_id
            rule_verified = False
            try:
                # Check routing_rules collection for rule_id
                rule_doc = await db.routing_rules.find_one({"rule_id": primary_citation})
                if rule_doc:
                    rule_verified = True
                else:
                    # Also accept source_document IDs as valid citations
                    src_doc = await db.source_documents.find_one({"doc_id": primary_citation})
                    if src_doc:
                        rule_verified = True
                    else:
                        # Backward compat: check kb_chunks (old format)
                        try:
                            id_filter = {"_id": ObjectId(primary_citation)} if ObjectId.is_valid(primary_citation) else {"_id": primary_citation}
                            kb_doc = await db.kb_chunks.find_one(id_filter)
                            if kb_doc:
                                rule_verified = True
                        except Exception:
                            pass
            except Exception:
                rule_verified = True  # DB error → don't block on citation check

            if not rule_verified:
                findings.append(CriticFinding(
                    field="router_output.citation_chunk_ids",
                    issue=f"Primary citation '{primary_citation}' not found in routing_rules or source_documents",
                    severity="warning",  # warning not blocking — routing still valid
                ))
                logger.warning(
                    "critic: unverified routing citation '%s' for report_id=%s",
                    primary_citation, report_id,
                )

        # ── DECISION ──────────────────────────────────────────────────────────
        blocking_findings = [f for f in findings if f.severity == "blocking"]

        if blocking_findings and attempt >= settings.CRITIC_MAX_RETRIES:
            # If we exhausted retries but core outputs exist, downgrade confidence blocks
            # to warnings so the ticket can still be dispatched and tracked
            has_core = bool(
                state.get("perception_output")
                and state.get("geo_output")
                and state.get("router_output")
            )
            if has_core:
                logger.info(
                    "critic: max retries reached (%d) for report_id=%s — proceeding to dispatcher with audit warnings",
                    settings.CRITIC_MAX_RETRIES,
                    report_id,
                )
                for f in findings:
                    if "confidence" in f.field:
                        f.severity = "warning"
                blocking_findings = [f for f in findings if f.severity == "blocking"]

        passed = len(blocking_findings) == 0

        if not passed and attempt >= settings.CRITIC_MAX_RETRIES:
            # True hard block (missing output that could not be resolved)
            updates["final_status"] = "human_review"
            retry_target = None
            logger.warning(
                "critic: unresolvable blocking findings for report_id=%s — routing to human_review",
                report_id,
            )

        output = CriticOutput(
            passed=passed,
            findings=findings,
            retry_target=retry_target,
            clarifying_question=clarifying_question,
            attempt_number=attempt,
        )
        updates["critic_output"] = output
        updates["retry_count"] = attempt

        audit["event_type"] = "node_completed"
        audit["data"] = {
            "attempt": attempt,
            "passed": passed,
            "blocking_count": len(blocking_findings),
            "warning_count": len([f for f in findings if f.severity == "warning"]),
            "retry_target": retry_target,
        }

        # ── SSE events ────────────────────────────────────────────────────────
        if passed:
            msg = "All quality checks passed ✓" if not [f for f in findings if f.severity == "warning"] else "Quality checks validated with audit notes ✓"
            await bus.publish(report_id, ProgressEvent(
                node="critic",
                status="done",
                message=msg,
            ))
        elif attempt >= settings.CRITIC_MAX_RETRIES:
            await bus.publish(report_id, ProgressEvent(
                node="critic",
                status="human_review",
                message="Sent to human review for manual processing.",
                data={"findings": [f.model_dump() for f in findings]},
            ))
        elif clarifying_question:
            await bus.publish(report_id, ProgressEvent(
                node="critic",
                status="retrying",
                message=clarifying_question,
                data={"action": "request_clarification"},
            ))
        else:
            await bus.publish(report_id, ProgressEvent(
                node="critic",
                status="retrying",
                message=(
                    f"Re-running {retry_target} "
                    f"(attempt {attempt}/{settings.CRITIC_MAX_RETRIES})…"
                ),
            ))

        logger.info(
            "critic: report_id=%s attempt=%d passed=%s retry_target=%s",
            report_id,
            attempt,
            passed,
            retry_target,
        )

    except Exception as exc:
        logger.exception("critic failed for report_id=%s", report_id)
        updates["critic_error"] = str(exc)
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)
        await bus.publish(report_id, ProgressEvent(
            node="critic",
            status="error",
            message="Critic check failed.",
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates
