"""
api/routers/admin.py
====================
Password-protected admin endpoints.
Authentication: Bearer token matching ADMIN_TOKEN env var.

PATCH /admin/tickets/{id}          — Update ticket status
POST  /internal/sla-sweep          — Trigger SLA escalation sweep

── Rule-Based Routing Engine endpoints ──────────────────────────────────────
GET   /admin/departments            — List all departments
GET   /admin/routing-rules          — List/filter routing rules
POST  /admin/routing-rules          — Create a new routing rule
PATCH /admin/routing-rules/{id}     — Enable/disable/update a rule
GET   /admin/officer-inbox          — Issues assigned to a department
POST  /admin/tickets/{id}/assign    — Assign ticket to department/officer
POST  /admin/tickets/{id}/status    — Update status + write to statusEvents
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_db
from app.models.schemas import TicketStatus, TicketStatusUpdate

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


def _build_id_filter(raw_id: str) -> dict:
    """Build a query filter matching either BSON ObjectId or string representation."""
    raw_str = str(raw_id).strip()
    if ObjectId.is_valid(raw_str):
        return {"$or": [{"_id": ObjectId(raw_str)}, {"_id": raw_str}]}
    return {"_id": raw_str}


def _require_admin(credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)]) -> None:
    settings = get_settings()
    if credentials.credentials != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


# ── Existing: List tickets (Clubbed by clustered issue) ─────────────────────

@router.get(
    "/admin/tickets",
    status_code=status.HTTP_200_OK,
    summary="List tickets for admin panel (clubbed by clustered issue)",
    dependencies=[Depends(_require_admin)],
)
async def list_tickets(status_filter: str | None = None, limit: int = 50):
    db = await get_db()
    query: dict = {}
    if status_filter:
        query["status"] = status_filter

    # Fetch recent tickets (over-fetch slightly to allow clubbing into unique issues)
    fetch_limit = max(limit * 3, 100)
    cursor = db.tickets.find(query).sort("created_at", -1).limit(fetch_limit)
    raw_tickets = await cursor.to_list(length=fetch_limit)

    # Group tickets by issue_id so clustered/duplicate reports are clubbed into one
    grouped: dict[str, list[dict]] = {}
    for doc in raw_tickets:
        doc["_id"] = str(doc["_id"])
        if "ticket_id" not in doc or not doc["ticket_id"]:
            doc["ticket_id"] = doc["_id"]
        issue_key = str(doc.get("issue_id") or doc["_id"]).strip()
        grouped.setdefault(issue_key, []).append(doc)

    # Fetch corresponding issue docs to enrich with category, address, city, report_count
    issue_ids = [k for k in grouped.keys() if ObjectId.is_valid(k)]
    issue_map: dict[str, dict] = {}
    if issue_ids:
        issue_cursor = db.issues.find({"_id": {"$in": [ObjectId(i) for i in issue_ids]}})
        async for issue_doc in issue_cursor:
            issue_map[str(issue_doc["_id"])] = issue_doc

    str_ids = [k for k in grouped.keys() if k not in issue_map]
    if str_ids:
        issue_cursor_str = db.issues.find({"_id": {"$in": str_ids}})
        async for issue_doc in issue_cursor_str:
            issue_map[str(issue_doc["_id"])] = issue_doc

    clubbed_tickets = []
    for issue_key, ticket_list in grouped.items():
        # Representative ticket: pick the first one (most recent by created_at)
        primary = dict(ticket_list[0])
        issue_doc = issue_map.get(issue_key, {})

        # Merge clustered report IDs across all tickets and the issue doc
        merged_report_ids = set()
        if issue_doc.get("report_ids"):
            merged_report_ids.update(str(r) for r in issue_doc["report_ids"])
        for t in ticket_list:
            if t.get("report_id"):
                merged_report_ids.add(str(t["report_id"]))
            if t.get("clustered_report_ids"):
                for r_id in t["clustered_report_ids"]:
                    merged_report_ids.add(str(r_id))

        total_report_count = max(
            len(merged_report_ids),
            int(issue_doc.get("report_count", 1)),
            int(primary.get("report_count", 1)),
            len(ticket_list),
        )

        # Merge status history
        combined_history = []
        for t in reversed(ticket_list):
            for h in t.get("status_history", []):
                combined_history.append(h)
        # Deduplicate history entries by timestamp + note
        seen_notes = set()
        deduped_history = []
        for h in combined_history:
            sig = (str(h.get("timestamp")), str(h.get("note")))
            if sig not in seen_notes:
                seen_notes.add(sig)
                deduped_history.append(h)

        # Build enriched clubbed ticket document
        primary["issue_id"] = issue_key
        primary["report_count"] = total_report_count
        primary["clustered_report_ids"] = sorted(list(merged_report_ids))
        primary["category"] = issue_doc.get("category") or primary.get("category") or "Civic Infrastructure"
        primary["address"] = issue_doc.get("address") or primary.get("address") or ""
        primary["city"] = issue_doc.get("city") or primary.get("city") or ""
        primary["ward"] = issue_doc.get("ward") or primary.get("ward") or ""
        primary["priority_score"] = max(
            float(primary.get("priority_score") or 0.0),
            float(issue_doc.get("priority_score") or 0.0),
        )
        primary["severity_tier"] = issue_doc.get("severity_tier") or primary.get("severity_tier") or "tier_1"
        if deduped_history:
            primary["status_history"] = deduped_history

        # SLA deadlines: choose the earliest deadline
        sla_deadlines = [t["sla_deadline"] for t in ticket_list if t.get("sla_deadline")]
        if sla_deadlines:
            primary["sla_deadline"] = min(sla_deadlines)

        # If any ticket in the cluster was publicly flagged
        primary["is_publicly_flagged"] = any(t.get("is_publicly_flagged", False) for t in ticket_list)

        clubbed_tickets.append(primary)

    # Sort clubbed tickets by updated_at / created_at descending
    clubbed_tickets.sort(
        key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
        reverse=True,
    )

    return clubbed_tickets[:limit]


# ── Existing: Update ticket status ──────────────────────────────────────────

@router.patch(
    "/admin/tickets/{ticket_id}",
    status_code=status.HTTP_200_OK,
    summary="Update ticket status",
    dependencies=[Depends(_require_admin)],
)
async def update_ticket_status(ticket_id: str, body: TicketStatusUpdate):
    db = await get_db()
    now = datetime.now(timezone.utc)
    clean_id = str(ticket_id).strip()

    id_filter = _build_id_filter(clean_id)

    status_str = body.status.value if hasattr(body.status, "value") else str(body.status)
    history_entry = {
        "status": status_str,
        "timestamp": now,
        "note": body.note,
        "updated_by": body.updated_by,
    }
    result = await db.tickets.update_one(
        id_filter,
        {
            "$set": {"status": status_str, "updated_at": now},
            "$push": {"status_history": history_entry},
        },
    )
    if result and getattr(result, "matched_count", 1) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Fetch updated ticket to retrieve associated issue
    ticket = await db.tickets.find_one(id_filter)
    if not ticket:
        ticket = await db.tickets.find_one({"ticket_id": clean_id})

    # Synchronize issue status so the Public Dashboard immediately shows the update
    issue_status = "resolved" if status_str == "resolved" else "in_progress" if status_str == "in_progress" else status_str
    issue_id = ticket.get("issue_id") if ticket else None

    if issue_id:
        await db.issues.update_one(
            _build_id_filter(str(issue_id)),
            {"$set": {"status": issue_status, "updated_at": now}},
        )
        await db.reports.update_many(
            {"issue_id": str(issue_id)},
            {"$set": {"status": "resolved" if issue_status == "resolved" else "processing", "updated_at": now}},
        )

    # Cross-reference update on issues by ticket_id
    await db.issues.update_one(
        {"ticket_id": clean_id},
        {"$set": {"status": issue_status, "updated_at": now}},
    )
    if ticket and "_id" in ticket:
        await db.issues.update_one(
            {"ticket_id": str(ticket["_id"])},
            {"$set": {"status": issue_status, "updated_at": now}},
        )

    # Write to statusEvents collection
    try:
        await db.status_events.insert_one({
            "event_type": "ticket_status_updated",
            "issue_id": str(issue_id) if issue_id else None,
            "ticket_id": clean_id,
            "actor": body.updated_by,
            "old_status": ticket.get("status") if ticket else None,
            "new_status": status_str,
            "issue_status": issue_status,
            "note": body.note,
            "timestamp": now,
        })
    except Exception as se_exc:
        logger.warning("status_events insert failed: %s", se_exc)

    # Write audit event
    await db.events.insert_one({
        "event_type": "ticket_status_updated",
        "report_id": None,
        "issue_id": str(issue_id) if issue_id else None,
        "ticket_id": clean_id,
        "node": None,
        "actor": body.updated_by,
        "data": {"new_status": status_str, "issue_status": issue_status, "note": body.note},
        "error": None,
        "timestamp": now,
    })

    return {
        "message": "Ticket and associated issue updated",
        "ticket_id": clean_id,
        "new_status": status_str,
        "issue_status": issue_status,
    }


# ── Existing: SLA sweep ──────────────────────────────────────────────────────

@router.post(
    "/internal/sla-sweep",
    status_code=status.HTTP_200_OK,
    summary="Trigger SLA escalation sweep",
    dependencies=[Depends(_require_admin)],
)
async def trigger_sla_sweep():
    from app.agents.sla_escalation_agent import run_sla_sweep
    result = await run_sla_sweep()
    return {"message": "SLA sweep complete", "result": result}


# ════════════════════════════════════════════════════════════════════════════════
# NEW: Rule-Based Routing Engine endpoints
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/admin/departments",
    status_code=status.HTTP_200_OK,
    summary="List all departments",
    dependencies=[Depends(_require_admin)],
)
async def list_departments(active_only: bool = True):
    """List all departments in the routing engine."""
    db = await get_db()
    query = {"is_active": True} if active_only else {}
    cursor = db.departments.find(query).sort("tier", 1)
    docs = await cursor.to_list(100)
    for doc in docs:
        doc["_id"] = str(doc.get("_id", ""))
    return docs


@router.get(
    "/admin/routing-rules",
    status_code=status.HTTP_200_OK,
    summary="List routing rules (optionally filter by category)",
    dependencies=[Depends(_require_admin)],
)
async def list_routing_rules(
    category: Optional[str] = None,
    active_only: bool = True,
    limit: int = 50,
):
    """List routing rules. Filter by category and/or active status."""
    db = await get_db()
    query: dict = {}
    if active_only:
        query["is_active"] = True
    if category:
        query["category"] = category
    cursor = db.routing_rules.find(query).sort("priority", 1).limit(limit)
    docs = await cursor.to_list(limit)
    for doc in docs:
        doc["_id"] = str(doc.get("_id", ""))
    return docs


class RoutingRuleCreate(BaseModel):
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
    source_document_ids: list[str] = Field(default_factory=list)
    routing_justification: str = ""
    is_active: bool = True


@router.post(
    "/admin/routing-rules",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new routing rule",
    dependencies=[Depends(_require_admin)],
)
async def create_routing_rule(body: RoutingRuleCreate):
    """Create a new deterministic routing rule."""
    db = await get_db()
    now = datetime.now(timezone.utc)
    # Check duplicate rule_id
    existing = await db.routing_rules.find_one({"rule_id": body.rule_id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule '{body.rule_id}' already exists. Use PATCH to update.",
        )
    # Verify department exists
    dept = await db.departments.find_one({"department_id": body.department_id})
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Department '{body.department_id}' not found.",
        )
    doc = body.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["_id"] = body.rule_id
    await db.routing_rules.insert_one(doc)
    return {"message": "Routing rule created", "rule_id": body.rule_id}


@router.patch(
    "/admin/routing-rules/{rule_id}",
    status_code=status.HTTP_200_OK,
    summary="Update / enable / disable a routing rule",
    dependencies=[Depends(_require_admin)],
)
async def update_routing_rule(rule_id: str, updates: dict):
    """Partially update a routing rule (e.g. toggle is_active, change priority)."""
    db = await get_db()
    updates.pop("rule_id", None)  # rule_id is immutable
    updates.pop("_id", None)
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db.routing_rules.update_one(
        {"rule_id": rule_id},
        {"$set": updates},
    )
    if result and getattr(result, "matched_count", 1) == 0:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return {"message": "Routing rule updated", "rule_id": rule_id}


@router.get(
    "/admin/officer-inbox",
    status_code=status.HTTP_200_OK,
    summary="Get issues assigned to a department (officer inbox)",
    dependencies=[Depends(_require_admin)],
)
async def officer_inbox(
    department_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
):
    """
    Retrieve open issues routed to a specific department.
    This is the officer inbox — shows what the department is responsible for.
    """
    db = await get_db()
    query: dict = {}
    if department_id:
        query["department_id"] = department_id
    if status_filter:
        query["status"] = status_filter
    else:
        # Default: open + in_progress + assigned issues
        query["status"] = {"$in": ["open", "assigned", "in_progress", "escalated"]}
    cursor = db.issues.find(query).sort("priority_score", -1).limit(limit)
    docs = await cursor.to_list(limit)
    for doc in docs:
        doc["_id"] = str(doc.get("_id", ""))
    return {"issues": docs, "count": len(docs), "department_id": department_id}


@router.post(
    "/admin/tickets/{ticket_id}/assign",
    status_code=status.HTTP_200_OK,
    summary="Assign ticket to a department/officer",
    dependencies=[Depends(_require_admin)],
)
async def assign_ticket(
    ticket_id: str,
    department_id: str,
    officer_id: Optional[str] = None,
    note: Optional[str] = None,
):
    """Assign a ticket to a department and optionally a specific officer."""
    db = await get_db()
    now = datetime.now(timezone.utc)
    id_filter = _build_id_filter(ticket_id)

    ticket = await db.tickets.find_one(id_filter)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Verify department exists
    dept = await db.departments.find_one({"department_id": department_id})
    if not dept:
        raise HTTPException(status_code=422, detail=f"Department '{department_id}' not found")

    update_fields: dict = {
        "department_id": department_id,
        "department_name": dept.get("name", department_id),
        "status": "acknowledged",
        "updated_at": now,
    }
    if officer_id:
        update_fields["assigned_officer_id"] = officer_id

    await db.tickets.update_one(id_filter, {"$set": update_fields})

    # Sync issue status
    issue_id = ticket.get("issue_id")
    if issue_id:
        await db.issues.update_one(
            _build_id_filter(str(issue_id)),
            {"$set": {
                "department_id": department_id,
                "department_name": dept.get("name", department_id),
                "status": "assigned",
                "updated_at": now,
            }},
        )

    # Write statusEvent
    try:
        await db.status_events.insert_one({
            "event_type": "ticket_assigned",
            "issue_id": str(issue_id) if issue_id else None,
            "ticket_id": ticket_id,
            "department_id": department_id,
            "officer_id": officer_id,
            "note": note,
            "timestamp": now,
        })
    except Exception as se_exc:
        logger.warning("status_events insert (assign) failed: %s", se_exc)

    return {
        "message": "Ticket assigned",
        "ticket_id": ticket_id,
        "department_id": department_id,
        "officer_id": officer_id,
    }


@router.post(
    "/admin/tickets/{ticket_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Update ticket status (writes to statusEvents)",
    dependencies=[Depends(_require_admin)],
)
async def update_ticket_status_v2(
    ticket_id: str,
    new_status: str,
    note: Optional[str] = None,
    updated_by: str = "officer",
):
    """
    Update ticket status and write a structured event to the statusEvents collection.
    This is the primary mechanism for officers to update issue progress.
    """
    db = await get_db()
    now = datetime.now(timezone.utc)
    id_filter = _build_id_filter(ticket_id)

    ticket = await db.tickets.find_one(id_filter)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    old_status = ticket.get("status", "unknown")

    await db.tickets.update_one(
        id_filter,
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"status_history": {
                "status": new_status,
                "timestamp": now,
                "note": note,
                "updated_by": updated_by,
            }},
        },
    )

    # Sync issue
    issue_id = ticket.get("issue_id")
    issue_status = "resolved" if new_status == "resolved" else "in_progress" if new_status == "in_progress" else new_status
    if issue_id:
        await db.issues.update_one(
            _build_id_filter(str(issue_id)),
            {"$set": {"status": issue_status, "updated_at": now}},
        )

    # Write to statusEvents
    try:
        await db.status_events.insert_one({
            "event_type": "status_update",
            "issue_id": str(issue_id) if issue_id else None,
            "ticket_id": ticket_id,
            "actor": updated_by,
            "old_status": old_status,
            "new_status": new_status,
            "issue_status": issue_status,
            "note": note,
            "timestamp": now,
        })
    except Exception as se_exc:
        logger.warning("status_events insert (status_v2) failed: %s", se_exc)

    return {
        "message": "Ticket status updated",
        "ticket_id": ticket_id,
        "old_status": old_status,
        "new_status": new_status,
        "issue_status": issue_status,
    }


@router.get(
    "/admin/status-events",
    status_code=status.HTTP_200_OK,
    summary="Get status event history for an issue or ticket",
    dependencies=[Depends(_require_admin)],
)
async def get_status_events(
    issue_id: Optional[str] = None,
    ticket_id: Optional[str] = None,
    limit: int = 50,
):
    """Retrieve the statusEvents audit trail for an issue or ticket."""
    db = await get_db()
    query: dict = {}
    if issue_id:
        query["issue_id"] = issue_id
    elif ticket_id:
        query["ticket_id"] = ticket_id
    else:
        raise HTTPException(status_code=400, detail="Provide issue_id or ticket_id")

    cursor = db.status_events.find(query).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(limit)
    for doc in docs:
        doc["_id"] = str(doc.get("_id", ""))
    return {"events": docs, "count": len(docs)}


@router.post(
    "/admin/database/clear",
    status_code=status.HTTP_200_OK,
    summary="Clear all operational records from database (reports, issues, tickets, events, traces)",
    dependencies=[Depends(_require_admin)],
)
async def clear_database_records(reseed_rules: bool = True):
    """
    Deletes all issues, reports, tickets, audit events, traces, and status events.
    Optionally re-seeds clean routing rules and departments so the engine is immediately ready.
    """
    from seed.clean_db import clean_database
    deleted = await clean_database(delete_reference_rules=not reseed_rules)
    return {
        "status": "success",
        "message": "All operational records cleared",
        "deleted_records": deleted,
    }

