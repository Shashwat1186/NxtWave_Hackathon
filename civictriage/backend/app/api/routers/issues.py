"""
api/routers/issues.py
=====================
GET  /issues                     — List issues with bbox/category/status filters
GET  /issues/{id}                — Single issue with trace and score breakdown
POST /issues/{id}/confirm        — Citizen confirms an existing issue
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import get_db
from app.models.schemas import (
    IssueCategory,
    IssueConfirmRequest,
    IssueListOut,
    IssueOut,
    IssueStatus,
    SeverityTier,
    GeoPoint,
    ScoreBreakdown,
)

router = APIRouter(prefix="/issues", tags=["issues"])
logger = logging.getLogger(__name__)


def _build_id_filter(raw_id: str) -> dict:
    """Build a query filter matching either BSON ObjectId or string representation."""
    raw_str = str(raw_id).strip()
    if ObjectId.is_valid(raw_str):
        return {"$or": [{"_id": ObjectId(raw_str)}, {"_id": raw_str}]}
    return {"_id": raw_str}


def _doc_to_issue_out(doc: dict) -> IssueOut:
    """Convert a MongoDB issue document to IssueOut with resilient fallback parsing."""
    now = datetime.now(timezone.utc)

    sb_raw = doc.get("score_breakdown")
    score_breakdown = None
    if sb_raw:
        try:
            score_breakdown = ScoreBreakdown(**sb_raw)
        except Exception:
            pass

    loc_raw = doc.get("location", {})
    location = GeoPoint(
        type=loc_raw.get("type", "Point") if isinstance(loc_raw, dict) else "Point",
        coordinates=loc_raw.get("coordinates", [0.0, 0.0]) if isinstance(loc_raw, dict) else [0.0, 0.0],
    )

    cat_val = doc.get("category", "other")
    try:
        category = IssueCategory(cat_val)
    except Exception:
        category = IssueCategory.OTHER

    status_val = doc.get("status", "open")
    try:
        status_enum = IssueStatus(status_val)
    except Exception:
        status_enum = IssueStatus.OPEN

    tier_val = doc.get("severity_tier", "low")
    try:
        severity_tier = SeverityTier(tier_val)
    except Exception:
        severity_tier = SeverityTier.LOW

    created_at = doc.get("created_at") or now
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = now

    updated_at = doc.get("updated_at") or created_at
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except Exception:
            updated_at = created_at

    raw_priority = float(doc.get("priority_score", 0.0) or 0.0)
    if raw_priority > 1.0:
        raw_priority = min(1.0, round(raw_priority / 100.0, 4))

    # Resilient fallback if priority_score was never persisted or came as 0
    if raw_priority <= 0.0:
        if score_breakdown and score_breakdown.total > 0:
            raw_priority = min(1.0, round(score_breakdown.total / 100.0, 4))
        else:
            category_defaults = {
                IssueCategory.ROAD_DAMAGE: 0.68,
                IssueCategory.WATER_LEAK: 0.72,
                IssueCategory.SEWAGE: 0.78,
                IssueCategory.GARBAGE: 0.48,
                IssueCategory.STREETLIGHT: 0.52,
                IssueCategory.POLLUTION: 0.58,
                IssueCategory.ENCROACHMENT: 0.42,
                IssueCategory.TREE_HAZARD: 0.64,
                IssueCategory.FLOOD: 0.88,
                IssueCategory.OTHER: 0.45,
            }
            raw_priority = category_defaults.get(category, 0.50)

        # Sync severity tier to match resolved score
        if raw_priority >= 0.80:
            severity_tier = SeverityTier.CRITICAL
        elif raw_priority >= 0.60:
            severity_tier = SeverityTier.HIGH
        elif raw_priority >= 0.35:
            severity_tier = SeverityTier.MEDIUM
        else:
            severity_tier = SeverityTier.LOW

        if score_breakdown is None:
            score_breakdown = ScoreBreakdown(
                hazard_weight=round(raw_priority * 45, 1),
                road_class_weight=10.0,
                proximity_bonus=8.0,
                cluster_bonus=0.0,
                age_penalty=2.0,
                total=round(raw_priority * 100, 1),
                tier=severity_tier,
            )

    return IssueOut(
        _id=str(doc["_id"]),
        category=category,
        location=location,
        address=doc.get("address"),
        ward=doc.get("ward"),
        status=status_enum,
        report_count=int(doc.get("report_count", 1) or 1),
        priority_score=raw_priority,
        score_breakdown=score_breakdown,
        severity_tier=severity_tier,
        created_at=created_at,
        updated_at=updated_at,
        ticket_id=str(doc["ticket_id"]) if doc.get("ticket_id") else None,
        department_id=doc.get("department_id"),
        department_name=doc.get("department_name"),
        routing_rule_id=doc.get("routing_rule_id"),
        routing_confidence=doc.get("routing_confidence"),
        routing_subtype=doc.get("routing_subtype"),
        routing_asset_type=doc.get("routing_asset_type"),
        routing_jurisdiction=doc.get("routing_jurisdiction"),
        routing_requires_human_review=doc.get("routing_requires_human_review"),
        source_document_ids=doc.get("source_document_ids"),
    )


@router.get("", response_model=IssueListOut, summary="List civic issues")
async def list_issues(
    min_lat: Annotated[Optional[float], Query()] = None,
    min_lng: Annotated[Optional[float], Query()] = None,
    max_lat: Annotated[Optional[float], Query()] = None,
    max_lng: Annotated[Optional[float], Query()] = None,
    category: Annotated[Optional[IssueCategory], Query()] = None,
    status_filter: Annotated[Optional[IssueStatus], Query(alias="status")] = None,
    department_id: Annotated[Optional[str], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    db = await get_db()
    query: dict = {}

    # Bounding box filter
    if all(v is not None for v in [min_lat, min_lng, max_lat, max_lng]):
        query["location"] = {
            "$geoWithin": {
                "$box": [[min_lng, min_lat], [max_lng, max_lat]]
            }
        }

    if category:
        query["category"] = category.value
    if status_filter:
        query["status"] = status_filter.value
    if department_id:
        query["department_id"] = department_id

    skip = (page - 1) * page_size
    total = await db.issues.count_documents(query)
    cursor = db.issues.find(query).sort("priority_score", -1).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)

    items = []
    for doc in docs:
        try:
            items.append(_doc_to_issue_out(doc))
        except Exception as exc:
            logger.warning("Could not parse issue doc %s: %s", doc.get("_id"), exc)

    return IssueListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{issue_id}", response_model=IssueOut, summary="Get issue detail")
async def get_issue(issue_id: str):
    db = await get_db()
    clean_id = str(issue_id).strip()
    if not clean_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    id_filter = _build_id_filter(clean_id)
    doc = await db.issues.find_one(id_filter)
    if not doc:
        # Resilient fallback: lookup by ticket_id or report_ids if referenced interchangeably
        doc = await db.issues.find_one({"ticket_id": clean_id})
        if not doc:
            doc = await db.issues.find_one({"report_ids": clean_id})

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    issue_out = _doc_to_issue_out(doc)

    # Attach trace if available
    doc_id_str = str(doc["_id"])
    trace_doc = await db.traces.find_one({"issue_id": doc_id_str})
    if not trace_doc and clean_id != doc_id_str:
        trace_doc = await db.traces.find_one({"issue_id": clean_id})
    if not trace_doc:
        # Try via report_ids
        report_ids = doc.get("report_ids", [])
        if report_ids:
            trace_doc = await db.traces.find_one({"report_id": {"$in": report_ids}})
    if trace_doc:
        issue_out.trace = trace_doc.get("steps", [])

    # Attach status events if available
    try:
        events_cursor = db.status_events.find({
            "$or": [{"issue_id": clean_id}, {"issue_id": doc_id_str}]
        }).sort("timestamp", 1)
        events = await events_cursor.to_list(50)
        for ev in events:
            ev["_id"] = str(ev.get("_id", ""))
        issue_out.status_events = events
    except Exception as ev_exc:
        logger.debug("Could not fetch status events for issue %s: %s", clean_id, ev_exc)

    return issue_out


@router.post("/{issue_id}/confirm", status_code=status.HTTP_200_OK, summary="Confirm an existing issue")
async def confirm_issue(issue_id: str, body: IssueConfirmRequest):
    db = await get_db()
    now = datetime.now(timezone.utc)
    clean_id = str(issue_id).strip()

    id_filter = _build_id_filter(clean_id)

    result = await db.issues.update_one(
        id_filter,
        {
            "$inc": {"report_count": 1},
            "$push": {"report_ids": body.report_id},
            "$set": {"updated_at": now},
        },
    )
    if result and getattr(result, "matched_count", 1) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    # Log audit event
    await db.events.insert_one({
        "event_type": "citizen_confirmed",
        "report_id": body.report_id,
        "issue_id": clean_id,
        "ticket_id": None,
        "node": None,
        "actor": "citizen",
        "data": {"comment": body.comment},
        "error": None,
        "timestamp": now,
    })

    return {"message": "Confirmation recorded", "issue_id": clean_id}
