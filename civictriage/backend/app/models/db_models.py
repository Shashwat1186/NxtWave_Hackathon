"""
models/db_models.py
===================
MongoDB document shapes and collection index declarations.

These are NOT ORM models — MongoDB is schemaless.
These classes document the expected shape of each collection's documents.
Use them to construct insertion dicts and to validate fetched documents.

Naming convention: each class ends with `Doc` and matches a collection name.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.schemas import (
    IssueCategory,
    IssueStatus,
    MediaType,
    ReportStatus,
    ScoreBreakdown,
    SeverityTier,
    TicketStatus,
    GeoPoint,
)


# ══════════════════════════════════════════════════════════════════════════════
# Collection: reports
# ══════════════════════════════════════════════════════════════════════════════

class ReportDoc(BaseModel):
    """
    Represents a single citizen submission.
    One report may be merged into an existing issue (deduplicator).
    """
    id: Optional[str] = Field(None, alias="_id")
    status: ReportStatus = ReportStatus.QUEUED
    media_type: MediaType
    file_path: Optional[str] = None       # local path, None for text-only
    file_mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    raw_text: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    issue_id: Optional[str] = None        # set after deduplication
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: issues
# Indexes: 2dsphere on `location`, vector index on `embedding`
# ══════════════════════════════════════════════════════════════════════════════

class SeverityFeaturesDoc(BaseModel):
    """Stored LLM-extracted features used for scoring."""
    hazard_type: str
    structural_risk: bool = False
    blocks_traffic: bool = False
    water_contamination_risk: bool = False
    fire_risk: bool = False
    additional_hazards: list[str] = []


class IssueDoc(BaseModel):
    """
    A deduplicated, geo-clustered civic issue.
    Multiple reports merge into one issue; priority_score is recomputed on merge.
    """
    id: Optional[str] = Field(None, alias="_id")
    category: IssueCategory
    location: GeoPoint                         # 2dsphere indexed
    address: Optional[str] = None
    ward: Optional[str] = None
    city: str = ""
    road_name: Optional[str] = None
    road_class: Optional[str] = None
    status: IssueStatus = IssueStatus.OPEN
    report_count: int = 1
    report_ids: list[str] = []
    severity_features: Optional[SeverityFeaturesDoc] = None
    priority_score: float = 0.0               # 0.0–1.0, deterministic rubric
    score_breakdown: Optional[ScoreBreakdown] = None
    severity_tier: Optional[SeverityTier] = None
    embedding: Optional[list[float]] = None   # Atlas Vector Search indexed
    combined_description: Optional[str] = None
    ticket_id: Optional[str] = None
    # ── Rule-Based Routing fields ────────────────────────────────────────────
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    routing_rule_id: Optional[str] = None
    routing_confidence: Optional[float] = None
    routing_subtype: Optional[str] = None
    routing_asset_type: Optional[str] = None
    routing_jurisdiction: Optional[str] = None
    routing_requires_human_review: Optional[bool] = None
    source_document_ids: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: tickets
# ══════════════════════════════════════════════════════════════════════════════

class TicketStatusHistoryEntry(BaseModel):
    status: TicketStatus
    timestamp: datetime
    note: Optional[str] = None
    updated_by: str = "system"


class TicketDoc(BaseModel):
    """Formal complaint ticket dispatched to an authority/department."""
    id: Optional[str] = Field(None, alias="_id")
    issue_id: str
    authority_id: str
    authority_name: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    fallback_authority_id: Optional[str] = None
    tier: int = 1                              # 1 = primary, 2 = district, 3 = state
    sla_hours: int
    sla_deadline: datetime
    status: TicketStatus = TicketStatus.OPEN
    status_history: list[TicketStatusHistoryEntry] = []
    complaint_text: str
    citation_chunk_ids: list[str] = []
    routing_justification: str = ""
    score_breakdown: Optional[ScoreBreakdown] = None
    escalation_count: int = 0
    is_publicly_flagged: bool = False          # set True by sla_escalation_agent
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: authorities
# ══════════════════════════════════════════════════════════════════════════════

class AuthorityDoc(BaseModel):
    """
    A department or government body that handles civic issues.
    Seeded from backend/seed/authorities.json.
    """
    id: Optional[str] = Field(None, alias="_id")
    name: str
    tier: int                          # 1 = ward/local, 2 = district, 3 = state
    jurisdiction_categories: list[IssueCategory]
    jurisdiction_wards: list[str] = []  # empty = city-wide
    contact_email: Optional[str] = None
    contact_webhook: Optional[str] = None
    escalation_parent_id: Optional[str] = None  # parent authority for escalation
    is_active: bool = True

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: kb_chunks
# Indexes: vector index on `embedding`
# ══════════════════════════════════════════════════════════════════════════════

class KBChunkDoc(BaseModel):
    """
    A knowledge-base chunk used by authority_router for RAG.
    Seeded from backend/kb/*.md files.
    """
    id: Optional[str] = Field(None, alias="_id")
    authority_id: str
    source: str                   # file name or URL
    text: str                     # raw chunk text
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = {}
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: events  (append-only audit log)
# ══════════════════════════════════════════════════════════════════════════════

class EventDoc(BaseModel):
    """
    Immutable audit event. Written by every node and the dispatcher.
    Never updated — only inserted.
    """
    id: Optional[str] = Field(None, alias="_id")
    event_type: str               # "node_started" | "node_completed" | "ticket_created" | "escalated" | etc.
    report_id: Optional[str] = None
    issue_id: Optional[str] = None
    ticket_id: Optional[str] = None
    node: Optional[str] = None
    actor: str = "system"         # "system" | "admin" | "citizen"
    data: dict[str, Any] = {}
    error: Optional[str] = None
    timestamp: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: traces  (per-run LangGraph execution trace)
# ══════════════════════════════════════════════════════════════════════════════

class TraceStepDoc(BaseModel):
    node: str
    status: str                   # "success" | "error" | "skipped"
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_summary: dict[str, Any] = {}
    output_summary: dict[str, Any] = {}
    error: Optional[str] = None
    retry_count: int = 0


class TraceDoc(BaseModel):
    """Full execution trace for a single pipeline run."""
    id: Optional[str] = Field(None, alias="_id")
    report_id: str
    final_status: str
    steps: list[TraceStepDoc] = []
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: geo_cache
# TTL index on `cached_at`
# ══════════════════════════════════════════════════════════════════════════════

class GeoCacheDoc(BaseModel):
    """Cached result from Nominatim or Overpass."""
    key: str                      # hash of (lat, lng, query_type)
    value: dict[str, Any]
    cached_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: departments (Rule-Based Routing)
# ══════════════════════════════════════════════════════════════════════════════

class DepartmentDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    department_id: str
    name: str
    short_name: Optional[str] = None
    tier: int = 1
    categories: list[str] = []
    contact_email: Optional[str] = None
    contact_webhook: Optional[str] = None
    escalation_parent_id: Optional[str] = None
    sla_hours_default: int = 48
    is_active: bool = True
    description: Optional[str] = None
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: routing_rules (Deterministic Rules)
# ══════════════════════════════════════════════════════════════════════════════

class RoutingRuleDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    rule_id: str
    name: str
    category: str
    subtype: str = "any"
    asset_type: str = "any"
    department_id: str
    jurisdiction_type: str = "any"
    priority: int = 50
    sla_hours: int = 48
    requires_human_review: bool = False
    source_document_ids: list[str] = []
    routing_justification: str = ""
    is_active: bool = True
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: jurisdictions (GeoJSON 2dsphere)
# ══════════════════════════════════════════════════════════════════════════════

class JurisdictionDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    jurisdiction_id: str
    name: str
    zone_type: str = "zone"
    city: str = "Hyderabad"
    district: Optional[str] = None
    state: str = "Telangana"
    administrative_body: str = "GHMC"
    boundary: dict[str, Any]  # GeoJSON Polygon
    is_active: bool = True
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: reporting_destinations
# ══════════════════════════════════════════════════════════════════════════════

class ReportingDestinationDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    destination_id: str
    name: str
    department_id: str
    type: str = "internal"  # "internal" | "email" | "webhook" | "external_portal"
    endpoint: Optional[str] = None
    contact_email: Optional[str] = None
    contact_webhook: Optional[str] = None
    is_active: bool = True
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: source_documents (Statutory Evidence / Provenance)
# ══════════════════════════════════════════════════════════════════════════════

class SourceDocumentDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    doc_id: str
    title: str
    section: Optional[str] = None
    url: Optional[str] = None
    authority: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# Collection: status_events (Officer Status Audit Log)
# ══════════════════════════════════════════════════════════════════════════════

class StatusEventDoc(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    event_type: str
    issue_id: Optional[str] = None
    ticket_id: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    actor: str = "system"
    old_status: Optional[str] = None
    new_status: str
    issue_status: Optional[str] = None
    note: Optional[str] = None
    timestamp: datetime

    model_config = {"populate_by_name": True}

