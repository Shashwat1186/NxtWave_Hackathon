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

    pipeline = [
        {"$group": {
            "_id": "$authority_id",
            "authority_name": {"$first": "$authority_name"},
            "total_tickets": {"$sum": 1},
            "resolved_tickets": {"$sum": {
                "$cond": [{"$in": ["$status", ["resolved", "closed"]]}, 1, 0]
            }},
            "sla_breach_count": {"$sum": {
                "$cond": ["$is_publicly_flagged", 1, 0]
            }},
            "avg_resolution_ms": {"$avg": {
                "$cond": [
                    {"$in": ["$status", ["resolved", "closed"]]},
                    {"$subtract": ["$updated_at", "$created_at"]},
                    None,
                ]
            }},
        }},
        {"$sort": {"total_tickets": -1}},
    ]

    cursor = db.tickets.aggregate(pipeline)
    docs = await cursor.to_list(length=100)

    entries = []
    for doc in docs:
        total = doc.get("total_tickets", 0)
        resolved = doc.get("resolved_tickets", 0)
        breaches = doc.get("sla_breach_count", 0)
        avg_ms = doc.get("avg_resolution_ms")
        avg_hours = round(avg_ms / 3600000, 1) if avg_ms else None

        # Score: 0-100, reduced by 10 per breach
        resolution_rate = resolved / total if total > 0 else 0
        score = max(0.0, round((resolution_rate * 100) - (breaches * 10), 1))

        entries.append(AuthorityLeaderboardEntry(
            authority_id=doc["_id"] or "unknown",
            authority_name=doc.get("authority_name", "Unknown"),
            total_tickets=total,
            resolved_tickets=resolved,
            avg_resolution_hours=avg_hours,
            sla_breach_count=breaches,
            score=score,
        ))

    # Sort by score descending
    entries.sort(key=lambda e: e.score, reverse=True)
    return entries
