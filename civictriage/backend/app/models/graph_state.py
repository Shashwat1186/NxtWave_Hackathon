"""
models/graph_state.py
=====================
LangGraph typed state definition for the CivicTriage pipeline.

All node functions receive and return CivicTriageState.
Fields are append-only where possible to support safe retries and
full audit trails. No node should delete fields already set by
a prior node.

The `audit_events` list is the authoritative in-flight event log;
it is written to MongoDB at the end of the pipeline by the dispatcher.
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

try:
    from app.models.schemas import (
        AuthorityRouterOutput,
        CriticOutput,
        DeduplicatorOutput,
        DispatcherOutput,
        GeoResolverOutput,
        IntakeGuardOutput,
        PerceptionOutput,
        SeverityScorerOutput,
    )
except ImportError:
    from .schemas import (
        AuthorityRouterOutput,
        CriticOutput,
        DeduplicatorOutput,
        DispatcherOutput,
        GeoResolverOutput,
        IntakeGuardOutput,
        PerceptionOutput,
        SeverityScorerOutput,
    )


class AuditEvent(TypedDict):
    """Append-only audit event written by each node."""
    event_type: str           # e.g. "node_started" | "node_completed" | "node_error"
    node: str
    timestamp: str            # ISO 8601
    data: dict[str, Any]
    error: Optional[str]


class CivicTriageState(TypedDict):
    """
    Immutable-style state for the CivicTriage LangGraph pipeline.

    Conventions:
    - Fields set by a node are never overwritten by later nodes
      (except critic_output, which accumulates retries).
    - `_error` fields record the last error from each node; None = success.
    - `retry_count` is incremented by the critic before looping back.
    """

    # ── Input (set at pipeline start) ────────────────────────────────────────
    report_id: str
    file_path: Optional[str]           # local path to uploaded file
    file_bytes: Optional[bytes]        # loaded file bytes (set by runner)
    file_mime_type: Optional[str]
    voice_file_bytes: Optional[bytes] # optional voice note accompanying visual evidence
    voice_file_mime_type: Optional[str]
    raw_text: Optional[str]            # citizen's text description
    gps_lat: Optional[float]
    gps_lng: Optional[float]

    # ── Node outputs ─────────────────────────────────────────────────────────
    intake_output: Optional[IntakeGuardOutput]
    intake_error: Optional[str]

    perception_output: Optional[PerceptionOutput]
    perception_error: Optional[str]

    geo_output: Optional[GeoResolverOutput]
    geo_error: Optional[str]

    dedup_output: Optional[DeduplicatorOutput]
    dedup_error: Optional[str]

    severity_output: Optional[SeverityScorerOutput]
    severity_error: Optional[str]

    router_output: Optional[AuthorityRouterOutput]
    router_error: Optional[str]

    critic_output: Optional[CriticOutput]
    critic_error: Optional[str]
    retry_count: int                   # incremented by critic on retry

    dispatcher_output: Optional[DispatcherOutput]
    dispatcher_error: Optional[str]

    # ── Final outcome ─────────────────────────────────────────────────────────
    final_status: Optional[str]        # "dispatched" | "human_review" | "rejected" | "failed"
    rejection_reason: Optional[str]
    issue_id: Optional[str]
    ticket_id: Optional[str]

    # ── Audit trail (append-only list) ────────────────────────────────────────
    audit_events: list[AuditEvent]


def make_initial_state(
    report_id: str,
    file_path: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    file_mime_type: Optional[str] = None,
    voice_file_bytes: Optional[bytes] = None,
    voice_file_mime_type: Optional[str] = None,
    raw_text: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lng: Optional[float] = None,
) -> CivicTriageState:
    """Factory to create a fresh CivicTriageState for a new report."""
    return CivicTriageState(
        report_id=report_id,
        file_path=file_path,
        file_bytes=file_bytes,
        file_mime_type=file_mime_type,
        voice_file_bytes=voice_file_bytes,
        voice_file_mime_type=voice_file_mime_type,
        raw_text=raw_text,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        intake_output=None,
        intake_error=None,
        perception_output=None,
        perception_error=None,
        geo_output=None,
        geo_error=None,
        dedup_output=None,
        dedup_error=None,
        severity_output=None,
        severity_error=None,
        router_output=None,
        router_error=None,
        critic_output=None,
        critic_error=None,
        retry_count=0,
        dispatcher_output=None,
        dispatcher_error=None,
        final_status=None,
        rejection_reason=None,
        issue_id=None,
        ticket_id=None,
        audit_events=[],
    )
