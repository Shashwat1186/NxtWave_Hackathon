"""
api/routers/dashboard.py
=========================
GET /dashboard/stats           — Aggregate statistics
GET /authorities/leaderboard   — Authority performance ranking
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.core.database import get_db
from app.models.schemas import AuthorityLeaderboardEntry, DashboardStats

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.get("/dashboard/stats", response_model=DashboardStats, summary="Public dashboard statistics")
async def get_dashboard_stats():
    db = await get_db()

    total_reports = await db.reports.count_documents({})
    open_issues = await db.issues.count_documents({"status": {"$in": ["open", "assigned", "in_progress"]}})
    resolved_issues = await db.issues.count_documents({"status": {"$in": ["resolved", "closed"]}})
    critical_issues = await db.issues.count_documents({"severity_tier": "critical"})

    # Average resolution time (hours) from resolved tickets
    pipeline_avg = [
        {"$match": {"status": {"$in": ["resolved", "closed"]}}},
        {"$project": {
            "hours": {
                "$divide": [
                    {"$subtract": ["$updated_at", "$created_at"]},
                    3600000,  # ms → hours
                ]
            }
        }},
        {"$group": {"_id": None, "avg_hours": {"$avg": "$hours"}}},
    ]
    avg_cursor = db.tickets.aggregate(pipeline_avg)
    avg_doc = await avg_cursor.to_list(length=1)
    avg_resolution = round(avg_doc[0]["avg_hours"], 1) if avg_doc else None

    # Top categories
    cat_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
        {"$project": {"category": "$_id", "count": 1, "_id": 0}},
    ]
    cat_cursor = db.issues.aggregate(cat_pipeline)
    top_categories = await cat_cursor.to_list(length=5)

    return DashboardStats(
        total_reports=total_reports,
        open_issues=open_issues,
        resolved_issues=resolved_issues,
        critical_issues=critical_issues,
        avg_resolution_hours=avg_resolution,
        top_categories=top_categories,
    )


@router.get(
    "/authorities/leaderboard",
    response_model=list[AuthorityLeaderboardEntry],
    summary="Authority accountability leaderboard",
)
async def get_authority_leaderboard():
    db = await get_db()

    # Fetch all tickets and aggregate in Python to support both real MongoDB
    # and the InMemoryDatabase fallback used during network outages.
    try:
        cursor = db.tickets.find({}).sort("created_at", -1)
        all_tickets = await cursor.to_list(length=500)
    except Exception:
        all_tickets = []

    # Group by authority_id (or department_id as fallback)
    grouped: dict[str, dict] = {}
    for t in all_tickets:
        auth_id = str(t.get("authority_id") or t.get("department_id") or "").strip()
        if not auth_id:
            continue
        if auth_id not in grouped:
            grouped[auth_id] = {
                "authority_id": auth_id,
                "authority_name": str(
                    t.get("authority_name") or t.get("department_name") or auth_id
                ),
                "total_tickets": 0,
                "resolved_tickets": 0,
                "sla_breach_count": 0,
                "resolution_ms_list": [],
            }
        g = grouped[auth_id]
        g["total_tickets"] += 1
        if t.get("status") in ("resolved", "closed"):
            g["resolved_tickets"] += 1
            created = t.get("created_at")
            updated = t.get("updated_at")
            if created and updated:
                try:
                    diff_ms = (updated - created).total_seconds() * 1000
                    g["resolution_ms_list"].append(diff_ms)
                except Exception:
                    pass
        if t.get("is_publicly_flagged"):
            g["sla_breach_count"] += 1

    entries = []
    for g in grouped.values():
        total = g["total_tickets"]
        resolved = g["resolved_tickets"]
        breaches = g["sla_breach_count"]
        ms_list = g["resolution_ms_list"]
        avg_hours = round(sum(ms_list) / len(ms_list) / 3600000, 1) if ms_list else None

        resolution_rate = resolved / total if total > 0 else 0
        score = max(0.0, round((resolution_rate * 100) - (breaches * 10), 1))

        entries.append(AuthorityLeaderboardEntry(
            authority_id=g["authority_id"],
            authority_name=g["authority_name"],
            total_tickets=total,
            resolved_tickets=resolved,
            avg_resolution_hours=avg_hours,
            sla_breach_count=breaches,
            score=score,
        ))

    entries.sort(key=lambda e: e.score, reverse=True)
    return entries
