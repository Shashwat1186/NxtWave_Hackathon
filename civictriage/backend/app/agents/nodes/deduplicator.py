"""
agents/nodes/deduplicator.py
============================
Node 4: deduplicator

Responsibilities:
- Query open issues within DEDUP_GEO_RADIUS_METERS of the resolved location,
  filtered by the same category (2dsphere $nearSphere + category filter)
- For each geo-candidate, compute embedding cosine similarity against the
  new report's combined_description embedding
- If the highest-similarity candidate exceeds DEDUP_SIMILARITY_THRESHOLD,
  merge: increment report_count, append report_id, recompute embedding average
- Otherwise, create a new issue document with a GeoJSON Point location
- Always write the updated issue to the DB from here (not in dispatcher)

On failure:
- DB query error → set dedup_error; pipeline continues as "create new"
  (safe degradation — we'd rather create a duplicate than block dispatch)
- Embedding error → fall back to geo-only dedup without similarity check

Returns: DeduplicatorOutput with action ("merged" | "created") and issue_id.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.core.database import get_db
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import DeduplicatorOutput
from app.services.embed_service import EmbedService

logger = logging.getLogger(__name__)


# ── Haversine distance helper ─────────────────────────────────────────────────

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in metres between two lat/lng points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


# ── Defect Classification & Similarity Helpers ────────────────────────────────

# Disjoint defect families that should NEVER merge together, even at the same location.
# E.g. a pothole report must NEVER merge with a streetlight report.
DISJOINT_DEFECT_PATTERNS = {
    "pothole": re.compile(
        r"\b(pothole|potholes|crater|craters|asphalt subsidence|road cavity)\b",
        re.IGNORECASE,
    ),
    "road_structural": re.compile(
        r"\b(road collapse|cave-in|cave in|sinkhole|divider broken|median broken|footpath broken)\b",
        re.IGNORECASE,
    ),
    "streetlight": re.compile(
        r"\b(streetlight|streetlights|street light|street lights|street lamp|streetlamp|lamp post|light pole|luminaire|lighting|dangling wire|exposed wire|electric pole|blackout|illumination|junction box|230v)\b",
        re.IGNORECASE,
    ),
    "water_leak": re.compile(
        r"\b(water leak|water leakage|water main|pipeline|pipeline burst|burst pipe|water supply|potable water)\b",
        re.IGNORECASE,
    ),
    "sewage": re.compile(
        r"\b(sewage|sewer|manhole|open manhole|drain overflow|gutter overflow|blackwater|foul smell)\b",
        re.IGNORECASE,
    ),
    "garbage": re.compile(
        r"\b(garbage|trash|waste|dump|dumpster|litter|waste burning|open burning|debris)\b",
        re.IGNORECASE,
    ),
    "flood": re.compile(
        r"\b(flood|flooding|waterlogged|waterlogging|submerged road|inundation)\b",
        re.IGNORECASE,
    ),
    "tree_hazard": re.compile(
        r"\b(fallen tree|uprooted tree|tree hazard|broken branch|hanging branch)\b",
        re.IGNORECASE,
    ),
    "encroachment": re.compile(
        r"\b(encroachment|illegal construction|illegal structure|hawker|blocked footpath)\b",
        re.IGNORECASE,
    ),
    "pollution": re.compile(
        r"\b(toxic smoke|air pollution|chemical effluent|industrial discharge)\b",
        re.IGNORECASE,
    ),
}


def detect_defect_families(text: str, features: list[str] | None = None) -> set[str]:
    """Identify which distinct defect families are present in the report."""
    combined = (text or "") + " " + " ".join(features or [])
    families = set()
    for fam, pat in DISJOINT_DEFECT_PATTERNS.items():
        if pat.search(combined):
            families.add(fam)
    return families


def are_defect_families_compatible(fam1: set[str], fam2: set[str]) -> bool:
    """
    Return False if both reports belong to specific identified defect families
    that are mutually disjoint (e.g. pothole vs streetlight).
    """
    if not fam1 or not fam2:
        return True  # No conflicting identified families
    return bool(fam1.intersection(fam2))


def compute_problem_similarity(text1: str, text2: str) -> float:
    """
    Compute token-level Jaccard similarity on core problem terms,
    filtering out generic location, administrative, and stop words.
    """
    stop_words = {
        "the", "a", "an", "on", "in", "at", "near", "by", "for", "with", "and", "or",
        "of", "to", "from", "is", "was", "are", "were", "been", "has", "have", "had",
        "road", "street", "lane", "colony", "nagar", "ward", "city", "hyderabad",
        "bangalore", "mumbai", "delhi", "chennai", "area", "junction", "route",
        "issue", "problem", "report", "reported", "citizen", "damage", "infrastructure",
        "adjacent", "located", "causing", "severe", "past", "nights", "days", "hours",
    }
    t1 = {w for w in re.findall(r"\w+", (text1 or "").lower()) if len(w) > 2 and w not in stop_words}
    t2 = {w for w in re.findall(r"\w+", (text2 or "").lower()) if len(w) > 2 and w not in stop_words}
    if not t1 or not t2:
        return 0.0
    return len(t1.intersection(t2)) / len(t1.union(t2))


# ── Node ──────────────────────────────────────────────────────────────────────

async def deduplicator(
    state: CivicTriageState,
    *,
    bus: SSEBus,
    db: Any = None,
    embed_service: Optional[EmbedService] = None,
) -> dict[str, Any]:
    """
    LangGraph node function for deduplicator.

    Reads:
        state["perception_output"] — detected_category, combined_description
        state["geo_output"]        — location (GeoPoint), address, ward, city,
                                     road_name, road_class
        state["report_id"]

    Writes:
        state["dedup_output"]  → DeduplicatorOutput
        state["issue_id"]      → str (issue _id as string)
        state["audit_events"]  → appended AuditEvent
    """
    report_id: str = state["report_id"]
    settings = get_settings()

    # ── SSE: start ────────────────────────────────────────────────────────────
    await bus.publish(
        report_id,
        ProgressEvent(
            node="deduplicator",
            status="running",
            message="Checking for duplicate reports in the area…",
        ),
    )

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "deduplicator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        # ── Extract inputs ────────────────────────────────────────────────────
        perception = state.get("perception_output")
        geo_output = state.get("geo_output")

        if perception is None:
            raise ValueError("perception_output is missing from state")
        if geo_output is None:
            raise ValueError("geo_output is missing from state")

        combined_description: str = perception.combined_description
        # IssueCategory is a str-enum; .value gives the raw string ("road_damage", etc.)
        category_value: str = perception.detected_category.value

        location = geo_output.location
        lng: float = location.coordinates[0]
        lat: float = location.coordinates[1]

        # ── Embed the incoming description ────────────────────────────────────
        if embed_service is None:
            embed_service = EmbedService()
        new_embedding: list[float] = await embed_service.embed(combined_description)

        # ── Resolve DB handle ─────────────────────────────────────────────────
        if db is None:
            db = await get_db()

        # ── MongoDB geo-radius query ──────────────────────────────────────────
        try:
            cursor = db.issues.find(
                {
                    "location": {
                        "$nearSphere": {
                            "$geometry": {
                                "type": "Point",
                                "coordinates": [lng, lat],
                            },
                            "$maxDistance": settings.DEDUP_GEO_RADIUS_METERS,
                        }
                    },
                    "category": category_value,
                    "status": {"$ne": "closed"},
                }
            )
            candidates: list[dict] = await cursor.to_list(length=20)
        except Exception as db_exc:
            # Fail-open: log and treat as zero candidates so we create a new issue
            logger.error(
                "deduplicator: MongoDB geo query failed for report_id=%s — %s",
                report_id,
                db_exc,
            )
            candidates = []

        # ── Score candidates ──────────────────────────────────────────────────
        best_candidate: Optional[dict] = None
        best_similarity: float = -1.0
        best_distance_m: Optional[float] = None

        # Extract features and defect families for incoming report
        curr_features = (
            getattr(perception.visual, "damage_features", [])
            if perception and perception.visual
            else []
        )
        curr_families = detect_defect_families(combined_description, curr_features)

        # Maximum physical radius for clustering the SAME defect
        # Two potholes/streetlights further than 100m are distinct physical issues
        MAX_SAME_DEFECT_DISTANCE_METERS = 100.0

        for candidate in candidates:
            # 1. Strict Category Isolation:
            # Prevents merging cross-category complaints (e.g. pothole vs streetlight)
            cand_cat = str(candidate.get("category", "")).lower().strip()
            curr_cat = str(category_value).lower().strip()
            if not cand_cat or not curr_cat or cand_cat != curr_cat:
                logger.warning(
                    "deduplicator: skipping cross-category candidate issue_id=%s "
                    "(candidate=%s, incoming=%s)",
                    candidate.get("_id"),
                    cand_cat,
                    curr_cat,
                )
                continue

            # 2. Distance check: candidate must be within defect radius
            cand_coords = candidate.get("location", {}).get("coordinates", [])
            if len(cand_coords) == 2:
                dist_m = haversine(lat, lng, cand_coords[1], cand_coords[0])
            else:
                dist_m = None

            if dist_m is not None and dist_m > MAX_SAME_DEFECT_DISTANCE_METERS:
                logger.debug(
                    "deduplicator: candidate issue_id=%s too far for same defect (dist=%.1fm > %.1fm)",
                    candidate.get("_id"),
                    dist_m,
                    MAX_SAME_DEFECT_DISTANCE_METERS,
                )
                continue

            # 3. Defect profile compatibility:
            # Ensure reports are not describing mutually disjoint defects
            # (e.g. pothole crater vs dangling electrical wire)
            cand_features = candidate.get("damage_features") or []
            cand_text = candidate.get("combined_description") or candidate.get("raw_description") or ""
            cand_families = detect_defect_families(cand_text, cand_features)

            if not are_defect_families_compatible(curr_families, cand_families):
                logger.warning(
                    "deduplicator: skipping incompatible defect candidate issue_id=%s "
                    "(incoming_families=%s, candidate_families=%s)",
                    candidate.get("_id"),
                    curr_families,
                    cand_families,
                )
                continue

            # 4. Content / Semantic similarity
            cand_emb: list[float] = candidate.get("embedding") or []
            emb_similarity = 0.0
            has_valid_emb = (
                cand_emb
                and len(cand_emb) == len(new_embedding)
                and any(x != 0.0 for x in new_embedding)
                and any(x != 0.0 for x in cand_emb)
            )
            if has_valid_emb:
                emb_similarity = EmbedService.cosine_similarity(new_embedding, cand_emb)

            lex_similarity = compute_problem_similarity(combined_description, cand_text)

            # High embedding similarity could be inflated by matching address/city strings.
            # Require at least one matching defect family or some lexical problem overlap.
            if has_valid_emb and emb_similarity >= settings.DEDUP_SIMILARITY_THRESHOLD:
                # If embeddings match, ensure problem descriptions don't have completely disjoint problem terms
                if curr_families and cand_families and not curr_families.intersection(cand_families):
                    similarity = 0.0
                else:
                    similarity = emb_similarity
            elif not has_valid_emb and lex_similarity >= 0.35 and (dist_m is not None and dist_m <= 50.0):
                # Fallback lexical match when embeddings are zero/offline
                similarity = lex_similarity
            else:
                similarity = 0.0

            if similarity > best_similarity:
                best_similarity = similarity
                best_candidate = candidate
                best_distance_m = dist_m

        # ── Decision: MERGE or CREATE ─────────────────────────────────────────
        now = datetime.now(timezone.utc)
        action: str
        issue_id: str
        cluster_size: int
        similarity_score: Optional[float] = None
        geo_distance_meters: Optional[float] = None

        if (
            best_candidate is not None
            and best_similarity >= settings.DEDUP_SIMILARITY_THRESHOLD
        ):
            # ── MERGE ─────────────────────────────────────────────────────────
            action = "merged"
            similarity_score = round(best_similarity, 4)
            geo_distance_meters = best_distance_m

            # Average old embedding with new embedding
            old_emb: list[float] = best_candidate.get("embedding") or []
            if old_emb and len(old_emb) == len(new_embedding):
                avg_emb: list[float] = [
                    (a + b) / 2 for a, b in zip(old_emb, new_embedding)
                ]
            else:
                avg_emb = new_embedding

            try:
                await db.issues.update_one(
                    {
                        "_id": best_candidate["_id"],
                        "category": category_value,
                        "status": {"$ne": "closed"},
                    },
                    {
                        "$inc": {"report_count": 1},
                        "$push": {"report_ids": report_id},
                        "$set": {
                            "embedding": avg_emb,
                            "updated_at": now,
                            "combined_description": combined_description,
                        },
                    },
                )
            except Exception as upd_exc:
                # Fail-open: log but still record the merge outcome
                logger.error(
                    "deduplicator: merge update failed for report_id=%s — %s",
                    report_id,
                    upd_exc,
                )

            issue_id = str(best_candidate["_id"])
            cluster_size = int(best_candidate.get("report_count", 1)) + 1

            logger.info(
                "deduplicator: MERGE report_id=%s → issue_id=%s sim=%.4f dist=%.1fm",
                report_id,
                issue_id,
                best_similarity,
                best_distance_m or 0.0,
            )

        else:
            # ── CREATE ────────────────────────────────────────────────────────
            action = "created"
            cluster_size = 1

            new_issue: dict = {
                "category": category_value,
                "location": {"type": "Point", "coordinates": [lng, lat]},
                "address": geo_output.address if geo_output else None,
                "ward": geo_output.ward if geo_output else None,
                "city": geo_output.city if geo_output else "",
                "road_name": geo_output.road_name if geo_output else None,
                "road_class": geo_output.road_class if geo_output else None,
                "status": "open",
                "report_count": 1,
                "report_ids": [report_id],
                "embedding": new_embedding,
                "combined_description": combined_description,
                "damage_features": curr_features,
                "hazard_indicators": (
                    getattr(perception.visual, "hazard_indicators", [])
                    if perception and perception.visual
                    else []
                ),
                "raw_description": (
                    getattr(perception.visual, "raw_description", "")
                    if perception and perception.visual
                    else ""
                ),
                "created_at": now,
                "updated_at": now,
            }

            try:
                result = await db.issues.insert_one(new_issue)
                issue_id = str(result.inserted_id)
            except Exception as ins_exc:
                # Fail-open: log; use a surrogate ID so downstream nodes are not blocked
                logger.error(
                    "deduplicator: insert failed for report_id=%s — %s",
                    report_id,
                    ins_exc,
                )
                issue_id = f"fallback:{report_id}"

            logger.info(
                "deduplicator: CREATE report_id=%s → issue_id=%s",
                report_id,
                issue_id,
            )

        # ── Build output ──────────────────────────────────────────────────────
        dedup_output = DeduplicatorOutput(
            action=action,
            issue_id=issue_id,
            cluster_size=cluster_size,
            similarity_score=similarity_score,
            geo_distance_meters=(
                round(geo_distance_meters, 2)
                if geo_distance_meters is not None
                else None
            ),
        )

        updates["dedup_output"] = dedup_output
        updates["issue_id"] = issue_id

        audit["event_type"] = "node_completed"
        audit["data"] = {
            "action": action,
            "issue_id": issue_id,
            "cluster_size": cluster_size,
            "similarity_score": similarity_score,
            "geo_distance_meters": geo_distance_meters,
        }

        # ── SSE: done ─────────────────────────────────────────────────────────
        action_label = "Merged into" if action == "merged" else "Created new"
        sim_part = (
            f", similarity={similarity_score:.4f}" if similarity_score is not None else ""
        )
        await bus.publish(
            report_id,
            ProgressEvent(
                node="deduplicator",
                status="done",
                message=(
                    f"{action_label} issue {issue_id} "
                    f"(cluster_size={cluster_size}{sim_part})"
                ),
                data={
                    "action": action,
                    "issue_id": issue_id,
                    "cluster_size": cluster_size,
                    "similarity_score": similarity_score,
                    "geo_distance_meters": geo_distance_meters,
                },
            ),
        )

    except Exception as exc:
        logger.exception("deduplicator failed for report_id=%s", report_id)
        updates["dedup_error"] = str(exc)
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)

        await bus.publish(
            report_id,
            ProgressEvent(
                node="deduplicator",
                status="error",
                message=f"Deduplication failed: {exc}",
            ),
        )

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates
