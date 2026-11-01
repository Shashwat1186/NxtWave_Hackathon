"""
agents/nodes/severity_scorer.py
================================
Node 5: severity_scorer — HYBRID

Architecture:
  Step A (LLM): Extract hazard features from perception output.
                Output: SeverityFeaturesFromLLM (Pydantic-validated).
  Step B (deterministic): Apply rubric to compute priority_score.
                          Rubric is pure Python — no LLM involved.

Deterministic rubric (0–100 pts, normalised to 0.0–1.0):
  hazard_weight     0–40   based on hazard_type dict
  road_class_weight 0–15   based on OSM highway tag
  proximity_bonus   0–20   nearest school/hospital within threshold
  cluster_bonus     0–15   log-scaled from cluster_size (report_count)
  age_penalty       0–10   hours since issue was first created (older = higher)

Score breakdown is always stored so every point is auditable.

On failure:
  - LLM feature extraction fails → use rule-based fallback from perception_output
  - Rubric always succeeds (pure Python) → no failure path
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from app.core.config import get_settings
from app.core.database import get_db
from app.core.llm_client import LLMClient, LLMError
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import (
    ScoreBreakdown,
    SeverityFeaturesFromLLM,
    SeverityScorerOutput,
    SeverityTier,
)

logger = logging.getLogger(__name__)

# ── Rubric weight tables ──────────────────────────────────────────────────────

HAZARD_WEIGHTS: dict[str, float] = {
    "water_main_break": 38,
    "pothole_large": 30,
    "sewage_overflow": 35,
    "structural_collapse": 40,
    "fallen_tree": 32,
    "fire_risk": 40,
    "streetlight_out": 18,
    "garbage_dumping": 15,
    "encroachment": 12,
    "pothole_small": 18,
    "water_pooling": 20,
    "default": 15,
}

ROAD_CLASS_WEIGHTS: dict[str, float] = {
    "motorway": 15,
    "trunk": 14,
    "primary": 12,
    "secondary": 10,
    "tertiary": 8,
    "residential": 5,
    "service": 3,
    "default": 4,
}

SEVERITY_THRESHOLDS = {
    SeverityTier.CRITICAL: 0.80,
    SeverityTier.HIGH: 0.60,
    SeverityTier.MEDIUM: 0.35,
}

# ── Category → hazard_type fallback mapping ────────────────────────────────────

CATEGORY_TO_HAZARD: dict[str, str] = {
    "road_damage": "pothole_large",
    "water_leak": "water_pooling",
    "sewage": "sewage_overflow",
    "garbage": "garbage_dumping",
    "streetlight": "streetlight_out",
    "pollution": "default",
    "encroachment": "encroachment",
    "tree_hazard": "fallen_tree",
    "flood": "water_main_break",
    "other": "default",
}

CATEGORY_ALLOWED_HAZARDS: dict[str, set[str]] = {
    "road_damage": {"pothole_large", "pothole_small", "structural_collapse"},
    "water_leak": {"water_main_break", "water_pooling"},
    "sewage": {"sewage_overflow"},
    "garbage": {"garbage_dumping", "fire_risk"},
    "streetlight": {"streetlight_out", "fire_risk"},
    "pollution": {"default", "fire_risk"},
    "encroachment": {"encroachment", "structural_collapse"},
    "tree_hazard": {"fallen_tree", "structural_collapse"},
    "flood": {"water_main_break", "water_pooling"},
    "other": {"default"},
}


def _category_hazard(category: str, hazard_type: str) -> str:
    """Keep extracted severity hazards consistent with the detected category."""
    allowed = CATEGORY_ALLOWED_HAZARDS.get(category, {"default"})
    if hazard_type in allowed:
        return hazard_type
    return CATEGORY_TO_HAZARD.get(category, "default")


def _compute_rubric(
    features: SeverityFeaturesFromLLM,
    road_class: str | None,
    nearest_poi_distance_meters: float | None,
    cluster_size: int,
    issue_age_hours: float,
    settings=None,
) -> ScoreBreakdown:
    """
    Pure deterministic rubric. Returns ScoreBreakdown.
    No LLM calls here.
    """
    if settings is None:
        settings = get_settings()

    hazard_weight = HAZARD_WEIGHTS.get(features.hazard_type, HAZARD_WEIGHTS["default"])
    # Bonus for structural/fire risk
    if features.structural_risk or features.fire_risk:
        hazard_weight = min(40.0, hazard_weight + 8)

    road_class_weight = ROAD_CLASS_WEIGHTS.get(road_class or "default", ROAD_CLASS_WEIGHTS["default"])

    proximity_bonus = 0.0
    if nearest_poi_distance_meters is not None:
        if nearest_poi_distance_meters <= settings.PROXIMITY_SCHOOL_BONUS_METERS:
            proximity_bonus = 20.0
        elif nearest_poi_distance_meters <= settings.PROXIMITY_HOSPITAL_BONUS_METERS:
            proximity_bonus = 15.0
        elif nearest_poi_distance_meters <= 500:
            proximity_bonus = 8.0

    cluster_bonus = min(15.0, math.log1p(max(0, cluster_size - 1)) * 4.5)

    age_penalty = min(10.0, math.log1p(issue_age_hours) * 1.5)

    total = hazard_weight + road_class_weight + proximity_bonus + cluster_bonus + age_penalty

    if total >= SEVERITY_THRESHOLDS[SeverityTier.CRITICAL] * 100:
        tier = SeverityTier.CRITICAL
    elif total >= SEVERITY_THRESHOLDS[SeverityTier.HIGH] * 100:
        tier = SeverityTier.HIGH
    elif total >= SEVERITY_THRESHOLDS[SeverityTier.MEDIUM] * 100:
        tier = SeverityTier.MEDIUM
    else:
        tier = SeverityTier.LOW

    return ScoreBreakdown(
        hazard_weight=round(hazard_weight, 2),
        road_class_weight=round(road_class_weight, 2),
        proximity_bonus=round(proximity_bonus, 2),
        cluster_bonus=round(cluster_bonus, 2),
        age_penalty=round(age_penalty, 2),
        total=round(total, 2),
        tier=tier,
    )


async def severity_scorer(
    state: CivicTriageState,
    *,
    llm: LLMClient,
    bus: SSEBus,
    db=None,
) -> dict:
    """
    LangGraph node for severity_scorer.
    Step A: LLM extracts SeverityFeaturesFromLLM.
    Step B: deterministic _compute_rubric() computes ScoreBreakdown.
    """
    report_id = state["report_id"]
    settings = get_settings()

    await bus.publish(report_id, ProgressEvent(
        node="severity_scorer",
        status="running",
        message="Assessing severity and computing priority score…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "severity_scorer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        # ── Gather context from state ─────────────────────────────────────────
        perception = state.get("perception_output")
        geo = state.get("geo_output")
        dedup = state.get("dedup_output")
        raw_text: str = state.get("raw_text") or ""

        # ── Step A: LLM feature extraction ────────────────────────────────────
        feature_prompt = f"""
Analyze this civic issue and extract severity features.

Issue description: {perception.combined_description if perception else raw_text}
Detected category: {perception.detected_category.value if perception else "unknown"}
Location: {geo.address if geo else "unknown"}

Identify:
- hazard_type: one of [water_main_break, pothole_large, pothole_small, sewage_overflow, structural_collapse, fallen_tree, fire_risk, streetlight_out, garbage_dumping, encroachment, water_pooling, default]
- structural_risk: true/false
- blocks_traffic: true/false
- water_contamination_risk: true/false
- fire_risk: true/false
- additional_hazards: list of strings
- confidence: 0.0-1.0

Return ONLY valid JSON matching the schema.
"""

        features: SeverityFeaturesFromLLM
        try:
            features = await llm.generate_structured(
                prompt=feature_prompt,
                response_model=SeverityFeaturesFromLLM,
                temperature=0.1,
                # The prompt contains the category/description; the dynamic
                # key lets demo fallback select the corresponding golden case.
                demo_cache_key=f"{report_id}_severity",
            )
            category_str = perception.detected_category.value if perception else "other"
            normalized_hazard = _category_hazard(category_str, features.hazard_type)
            if normalized_hazard != features.hazard_type:
                logger.warning(
                    "severity_scorer: correcting category-incompatible hazard "
                    "report_id=%s category=%s hazard=%s -> %s",
                    report_id,
                    category_str,
                    features.hazard_type,
                    normalized_hazard,
                )
                features = features.model_copy(update={"hazard_type": normalized_hazard})
            logger.info(
                "severity_scorer: LLM features extracted for report_id=%s hazard=%s",
                report_id,
                features.hazard_type,
            )
        except LLMError as llm_exc:
            # ── Step A fallback: rule-based from perception_output ────────────
            logger.warning(
                "severity_scorer: LLM failed for report_id=%s (%s) — using rule-based fallback",
                report_id,
                llm_exc,
            )

            # Map detected_category → hazard_type
            category_str: str = (
                perception.detected_category.value if perception else "other"
            )
            hazard_type: str = CATEGORY_TO_HAZARD.get(category_str, "default")

            # Extract boolean signals from visual hazard indicators if available
            hazard_indicators: list[str] = []
            if perception and perception.visual:
                hazard_indicators = perception.visual.hazard_indicators or []

            structural_risk = any(
                kw in ind for ind in hazard_indicators
                for kw in ("structural_risk", "collapse", "structural")
            )
            fire_risk_flag = any(
                kw in ind for ind in hazard_indicators
                for kw in ("fire", "fire_risk", "flammable")
            )
            blocks_traffic = any(
                kw in ind for ind in hazard_indicators
                for kw in ("near_traffic", "blocks_traffic", "road_blocked")
            )
            water_contamination = any(
                kw in ind for ind in hazard_indicators
                for kw in ("water_contamination", "sewage", "contamination")
            )

            features = SeverityFeaturesFromLLM(
                hazard_type=hazard_type,
                structural_risk=structural_risk,
                blocks_traffic=blocks_traffic,
                water_contamination_risk=water_contamination,
                fire_risk=fire_risk_flag,
                additional_hazards=hazard_indicators,
                confidence=0.4,
            )

        # ── Step B: gather rubric inputs ──────────────────────────────────────

        # road_class from geo_output
        road_class: str | None = geo.road_class if geo else None

        # nearest_poi_distance: minimum distance_meters across all nearby POIs
        nearest_poi_distance: float | None = None
        if geo and geo.nearby_pois:
            try:
                nearest_poi_distance = min(
                    p.distance_meters for p in geo.nearby_pois
                )
            except (ValueError, AttributeError):
                nearest_poi_distance = None

        # cluster_size from dedup_output (default 1 if not present)
        cluster_size: int = dedup.cluster_size if dedup else 1

        # issue_age_hours: if merged, assume a small existing age; if new, 0.0
        if dedup and dedup.action == "merged":
            issue_age_hours: float = 2.0  # conservative small default for merged issues
        else:
            issue_age_hours = 0.0

        # ── Step B: compute rubric ────────────────────────────────────────────
        breakdown: ScoreBreakdown = _compute_rubric(
            features=features,
            road_class=road_class,
            nearest_poi_distance_meters=nearest_poi_distance,
            cluster_size=cluster_size,
            issue_age_hours=issue_age_hours,
            settings=settings,
        )

        # Normalise total (0–100) → priority_score (0.0–1.0)
        priority_score: float = round(min(1.0, breakdown.total / 100.0), 4)

        # ── SLA hours from tier ───────────────────────────────────────────────
        sla_map: dict[SeverityTier, int] = {
            SeverityTier.CRITICAL: settings.SLA_CRITICAL_HOURS,
            SeverityTier.HIGH: settings.SLA_HIGH_HOURS,
            SeverityTier.MEDIUM: settings.SLA_MEDIUM_HOURS,
            SeverityTier.LOW: settings.SLA_LOW_HOURS,
        }
        sla_hours: int = sla_map[breakdown.tier]

        # ── Build output ──────────────────────────────────────────────────────
        severity_output = SeverityScorerOutput(
            severity_features=features,
            score_breakdown=breakdown,
            priority_score=priority_score,
            severity_tier=breakdown.tier,
            sla_hours=sla_hours,
        )

        updates["severity_output"] = severity_output

        # Persist severity score to MongoDB issue immediately so it is never 0
        issue_id = state.get("issue_id") or (dedup.issue_id if dedup else None)
        if issue_id:
            try:
                if db is None:
                    db = await get_db()
                raw_sid = str(issue_id).strip()
                oid_filter = (
                    {"$or": [{"_id": ObjectId(raw_sid)}, {"_id": raw_sid}]}
                    if ObjectId.is_valid(raw_sid)
                    else {"_id": raw_sid}
                )
                await db.issues.update_one(
                    oid_filter,
                    {"$set": {
                        "priority_score": priority_score,
                        "severity_tier": breakdown.tier.value,
                        "score_breakdown": breakdown.model_dump(),
                        "sla_hours": sla_hours,
                        "updated_at": datetime.now(timezone.utc),
                    }},
                )
                logger.info("severity_scorer: persisted priority_score=%.4f to issue_id=%s", priority_score, issue_id)
            except Exception as db_exc:
                logger.warning("severity_scorer: could not update issue %s in DB: %s", issue_id, db_exc)

        audit["event_type"] = "node_completed"
        audit["data"] = {
            "hazard_type": features.hazard_type,
            "priority_score": priority_score,
            "severity_tier": breakdown.tier.value,
            "sla_hours": sla_hours,
            "score_breakdown": {
                "hazard_weight": breakdown.hazard_weight,
                "road_class_weight": breakdown.road_class_weight,
                "proximity_bonus": breakdown.proximity_bonus,
                "cluster_bonus": breakdown.cluster_bonus,
                "age_penalty": breakdown.age_penalty,
                "total": breakdown.total,
            },
        }

        logger.info(
            "severity_scorer: report_id=%s tier=%s score=%.4f sla=%dh",
            report_id,
            breakdown.tier.value,
            priority_score,
            sla_hours,
        )

        # ── SSE: done ─────────────────────────────────────────────────────────
        await bus.publish(
            report_id,
            ProgressEvent(
                node="severity_scorer",
                status="done",
                message=(
                    f"Severity assessed: {breakdown.tier.value.upper()} "
                    f"(score={priority_score:.2f}, SLA={sla_hours}h)"
                ),
                data={
                    "severity_tier": breakdown.tier.value,
                    "priority_score": priority_score,
                    "sla_hours": sla_hours,
                    "hazard_type": features.hazard_type,
                },
            ),
        )

    except Exception as exc:
        logger.exception("severity_scorer failed for report_id=%s", report_id)
        updates["severity_error"] = str(exc)
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)
        await bus.publish(report_id, ProgressEvent(
            node="severity_scorer", status="error", message="Severity scoring failed."
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates
