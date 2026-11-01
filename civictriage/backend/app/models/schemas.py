"""
models/schemas.py
=================
ALL Pydantic schemas for:
  - API request/response bodies
  - Agent node inputs/outputs
  - SSE event payloads

This file is the shared contract between backend and frontend.
The TypeScript types in frontend/src/api/types.ts must mirror these.

Rules:
  - Every LLM output schema lives here (no free-text parsing elsewhere).
  - All fields have explicit types and descriptions.
  - Optional fields use Optional[X] = None, not bare X.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class IssueCategory(str, Enum):
    ROAD_DAMAGE = "road_damage"
    WATER_LEAK = "water_leak"
    SEWAGE = "sewage"
    GARBAGE = "garbage"
    STREETLIGHT = "streetlight"
    POLLUTION = "pollution"
    ENCROACHMENT = "encroachment"
    TREE_HAZARD = "tree_hazard"
    FLOOD = "flood"
    OTHER = "other"


class SeverityTier(str, Enum):
    CRITICAL = "critical"   # score >= 0.80
    HIGH = "high"           # score >= 0.60
    MEDIUM = "medium"       # score >= 0.35
    LOW = "low"             # score < 0.35


class ReportStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    MERGED = "merged"          # merged into existing issue
    SPAWNED = "spawned"        # created new issue
    REJECTED = "rejected"      # intake_guard rejected
    HUMAN_REVIEW = "human_review"
    FAILED = "failed"


class IssueStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class MediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    TEXT = "text"


# ══════════════════════════════════════════════════════════════════════════════
# GEO PRIMITIVES
# ══════════════════════════════════════════════════════════════════════════════

class GeoPoint(BaseModel):
    """GeoJSON Point — stored with 2dsphere index."""
    type: str = "Point"
    coordinates: list[float] = Field(..., description="[longitude, latitude]", min_length=2, max_length=2)

    @property
    def longitude(self) -> float:
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        return self.coordinates[1]


class BoundingBox(BaseModel):
    """Geo bounding box for map tile queries."""
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float


# ══════════════════════════════════════════════════════════════════════════════
# API — REPORT SUBMISSION
# ══════════════════════════════════════════════════════════════════════════════

class ReportSubmitResponse(BaseModel):
    """Response to POST /reports."""
    report_id: str
    stream_url: str
    status: ReportStatus = ReportStatus.QUEUED
    message: str = "Report queued. Connect to stream_url for live updates."


class ReportOut(BaseModel):
    """Public representation of a report document."""
    id: str = Field(alias="_id")
    status: ReportStatus
    media_type: MediaType
    description: Optional[str] = None
    location: Optional[GeoPoint] = None
    issue_id: Optional[str] = None
    created_at: datetime

    model_config = {"populate_by_name": True}


# ══════════════════════════════════════════════════════════════════════════════
# API — ISSUES
# ══════════════════════════════════════════════════════════════════════════════

class ScoreBreakdown(BaseModel):
    """Auditable breakdown of the deterministic severity score."""
    hazard_weight: float = Field(ge=0, le=40, description="Points from hazard type (0–40)")
    road_class_weight: float = Field(ge=0, le=15, description="Points from OSM road class (0–15)")
    proximity_bonus: float = Field(ge=0, le=20, description="Points for proximity to school/hospital (0–20)")
    cluster_bonus: float = Field(ge=0, le=15, description="Points from cluster size (0–15)")
    age_penalty: float = Field(ge=0, le=10, description="Points from issue age (0–10)")
    total: float = Field(ge=0, le=100)
    tier: SeverityTier

    @field_validator("total", mode="before")
    @classmethod
    def _compute_total(cls, v: float, info) -> float:
        """Allow pre-computed total or compute from parts."""
        return v


class IssueOut(BaseModel):
    """Public representation of a clustered issue."""
    id: str = Field(alias="_id")
    category: IssueCategory
    location: GeoPoint
    address: Optional[str] = None
    ward: Optional[str] = None
    status: IssueStatus
    report_count: int = 1
    priority_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: Optional[ScoreBreakdown] = None
    severity_tier: SeverityTier
    created_at: datetime
    updated_at: datetime
    # Included only when fetching single issue (GET /issues/{id})
    trace: Optional[list[dict]] = None
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
    status_events: Optional[list[dict]] = None

    model_config = {"populate_by_name": True}


class IssueListOut(BaseModel):
    """Paginated list of issues."""
    items: list[IssueOut]
    total: int
    page: int
    page_size: int


class IssueConfirmRequest(BaseModel):
    """Body for POST /issues/{id}/confirm (citizen confirmation)."""
    report_id: str
    comment: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# API — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

class DashboardStats(BaseModel):
    total_reports: int
    open_issues: int
    resolved_issues: int
    critical_issues: int
    avg_resolution_hours: Optional[float] = None
    top_categories: list[dict]  # [{"category": "road_damage", "count": 42}]


class AuthorityLeaderboardEntry(BaseModel):
    authority_id: str
    authority_name: str
    total_tickets: int
    resolved_tickets: int
    avg_resolution_hours: Optional[float] = None
    sla_breach_count: int
    score: float  # 0–100 performance score


# ══════════════════════════════════════════════════════════════════════════════
# API — ADMIN
# ══════════════════════════════════════════════════════════════════════════════

class TicketStatusUpdate(BaseModel):
    """Body for PATCH /admin/tickets/{id}."""
    status: TicketStatus
    note: Optional[str] = None
    updated_by: str = "admin"


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: intake_guard
# ══════════════════════════════════════════════════════════════════════════════

class IntakeGuardOutput(BaseModel):
    """Structured output from the intake_guard node."""
    is_valid: bool
    is_civic: bool
    rejection_reason: Optional[str] = None  # "spam" | "nsfw" | "non_civic" | "file_too_large" | None
    media_type: MediaType
    file_mime_type: str
    file_size_bytes: int
    confidence: float = Field(ge=0.0, le=1.0)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: perceive
# ══════════════════════════════════════════════════════════════════════════════

class AudioTranscription(BaseModel):
    """Output of audio transcription sub-step."""
    text: str
    language_tag: str = "en"       # BCP-47 language code
    confidence: float = Field(ge=0.0, le=1.0)
    is_transcription_failed: bool = False


class VisualObservation(BaseModel):
    """Structured visual analysis of an image."""
    issue_type: IssueCategory
    damage_features: list[str] = Field(description="E.g. ['pothole_large', 'water_pooling']")
    hazard_indicators: list[str] = Field(description="E.g. ['near_traffic', 'structural_risk']")
    estimated_area_sqm: Optional[float] = None
    confidence: float = Field(ge=0.0, le=1.0)
    raw_description: str = Field(description="One-sentence visual summary")
    image_matches_description: bool = Field(default=True, description="Whether uploaded image matches grievance description")
    mismatch_reason: Optional[str] = Field(default=None, description="Explanation if image does not match grievance description")


class PerceptionOutput(BaseModel):
    """Combined output from the perceive node."""
    transcription: Optional[AudioTranscription] = None
    visual: Optional[VisualObservation] = None
    combined_description: str = Field(description="Unified natural-language description for downstream nodes")
    detected_category: IssueCategory
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str
    image_matches_description: bool = Field(default=True, description="Whether uploaded image matches grievance description")
    mismatch_reason: Optional[str] = Field(default=None, description="Explanation if image does not match grievance description")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: geo_resolver
# ══════════════════════════════════════════════════════════════════════════════

class NearbyPOI(BaseModel):
    """A nearby point of interest from Overpass."""
    osm_id: int
    poi_type: str           # "school" | "hospital" | "road" etc.
    name: Optional[str] = None
    distance_meters: float
    osm_tags: dict = {}


class GeoResolverOutput(BaseModel):
    """Output from the geo_resolver node."""
    location: GeoPoint
    source: str             # "gps" | "exif" | "landmark" | "map_pin" | "fallback"
    address: str
    ward: Optional[str] = None
    city: str
    country: str
    road_name: Optional[str] = None
    road_class: Optional[str] = None   # OSM highway tag value
    nearby_pois: list[NearbyPOI] = []
    geocode_cache_hit: bool = False


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: deduplicator
# ══════════════════════════════════════════════════════════════════════════════

class DeduplicatorOutput(BaseModel):
    """Output from the deduplicator node."""
    action: str                        # "merged" | "created"
    issue_id: str
    cluster_size: int                  # number of reports in the issue after merge
    similarity_score: Optional[float] = None   # if merged
    geo_distance_meters: Optional[float] = None


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: severity_scorer
# ══════════════════════════════════════════════════════════════════════════════

class SeverityFeaturesFromLLM(BaseModel):
    """
    LLM-extracted severity features (inputs to deterministic rubric).
    The LLM only extracts features; it does NOT compute the score.
    """
    hazard_type: str = Field(description="Primary hazard label: 'pothole_large'|'water_main_break'|etc.")
    structural_risk: bool = False
    blocks_traffic: bool = False
    water_contamination_risk: bool = False
    fire_risk: bool = False
    additional_hazards: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class SeverityScorerOutput(BaseModel):
    """Output from the severity_scorer node."""
    severity_features: SeverityFeaturesFromLLM
    score_breakdown: ScoreBreakdown
    priority_score: float = Field(ge=0.0, le=1.0)
    severity_tier: SeverityTier
    sla_hours: int


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: authority_router
# ══════════════════════════════════════════════════════════════════════════════

class AuthorityRef(BaseModel):
    authority_id: str
    authority_name: str
    tier: int                  # 1 = primary, 2 = district, 3 = state
    contact_email: Optional[str] = None
    contact_webhook: Optional[str] = None


class DepartmentRef(BaseModel):
    department_id: str
    name: str
    short_name: Optional[str] = None
    tier: int = 1
    contact_email: Optional[str] = None
    contact_webhook: Optional[str] = None


class SourceDocumentRef(BaseModel):
    doc_id: str
    title: str
    section: Optional[str] = None
    url: Optional[str] = None
    authority: Optional[str] = None


class RoutingRuleSchema(BaseModel):
    rule_id: str
    name: str
    category: IssueCategory
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


class StatusEventSchema(BaseModel):
    event_type: str
    issue_id: Optional[str] = None
    ticket_id: Optional[str] = None
    department_id: Optional[str] = None
    actor: str = "system"
    old_status: Optional[str] = None
    new_status: str
    issue_status: Optional[str] = None
    note: Optional[str] = None
    timestamp: datetime


class AuthorityRouterOutput(BaseModel):
    """Output from the authority_router node."""
    primary_authority: AuthorityRef
    fallback_authority: Optional[AuthorityRef] = None
    confidence: float = Field(ge=0.0, le=1.0)
    citation_chunk_ids: list[str] = Field(description="KB chunk IDs that justify the routing")
    routing_justification: str = Field(description="One paragraph explaining why this authority was chosen")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: critic
# ══════════════════════════════════════════════════════════════════════════════

class CriticFinding(BaseModel):
    field: str
    issue: str
    severity: str  # "blocking" | "warning"


class CriticOutput(BaseModel):
    """Output from the critic node."""
    passed: bool
    findings: list[CriticFinding] = []
    retry_target: Optional[str] = None   # node to re-run: "perceive" | "authority_router"
    clarifying_question: Optional[str] = None  # question to ask citizen
    attempt_number: int = 1


# ══════════════════════════════════════════════════════════════════════════════
# AGENT NODE: dispatcher
# ══════════════════════════════════════════════════════════════════════════════

class DispatcherOutput(BaseModel):
    """Output from the dispatcher node."""
    ticket_id: str
    complaint_text: str
    sla_deadline: datetime
    mock_email_sent: bool = True
    mock_webhook_sent: bool = True
    audit_event_ids: list[str] = []


# ══════════════════════════════════════════════════════════════════════════════
# ERROR / GENERIC
# ══════════════════════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None

