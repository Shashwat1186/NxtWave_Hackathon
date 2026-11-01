"""
services/sla_service.py
========================
SLA sweep logic for the sla_escalation_agent.
Finds overdue tickets, escalates to parent authority, flags publicly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.core.config import get_settings
from app.core.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

_ESCALATION_SYSTEM = (
    "You are a government accountability officer. "
    "Draft a formal escalation notice for an overdue civic complaint. "
    "Be firm, factual, and professional. Return only the letter body."
)

_ESCALATION_PROMPT = """
The following civic complaint has breached its SLA deadline and is being escalated.

Original Reference: {ref}
Issue Category: {category}
Location: {address}
Original Authority: {orig_authority}
Escalating to: {new_authority}
Original SLA Deadline: {orig_deadline}
Overdue by: {overdue_hours:.1f} hours
Escalation Number: {escalation_count}
Original Complaint Summary:
{complaint_preview}

Write an escalation notice demanding immediate action from the higher authority,
referencing the original complaint and the SLA breach. Keep it under 300 words.
"""


class SLAService:
    def __init__(self, db, llm: LLMClient):
        self._db = db
        self._llm = llm
        self._settings = get_settings()

    async def sweep(self) -> dict:
        """Find overdue tickets, escalate, and flag publicly."""
        now = datetime.now(timezone.utc)
        overdue = await self._find_overdue(now)
        escalated = 0
        flagged = 0

        for ticket in overdue:
            try:
                await self._escalate(ticket, now)
                escalated += 1
                if ticket.get("escalation_count", 0) >= 1:
                    await self._flag_publicly(ticket)
                    flagged += 1
            except Exception as exc:
                logger.exception("SLA escalation failed for ticket %s: %s", ticket.get("_id"), exc)

        logger.info("SLA sweep complete: found=%d escalated=%d flagged=%d",
                    len(overdue), escalated, flagged)
        return {"swept": len(overdue), "escalated": escalated, "flagged": flagged}

    async def _find_overdue(self, now: datetime) -> list[dict]:
        cursor = self._db.tickets.find({
            "sla_deadline": {"$lt": now},
            "status": {"$nin": ["resolved", "closed", "escalated"]},
        })
        return await cursor.to_list(length=200)

    async def _escalate(self, ticket: dict, now: datetime) -> None:
        """Escalate to parent authority tier."""
        current_authority_id = ticket.get("authority_id") or ticket.get("department_id")
        auth_doc = await self._db.authorities.find_one(
            {"name": {"$regex": ticket.get("authority_name", ""), "$options": "i"}}
        )
        parent_id = auth_doc.get("escalation_parent_id") if auth_doc else None

        if parent_id:
            try:
                parent_doc = await self._db.authorities.find_one({"_id": ObjectId(parent_id)})
            except Exception:
                parent_doc = None
        else:
            # Find a tier-2 authority as default escalation target
            parent_doc = await self._db.authorities.find_one(
                {"tier": 2, "is_active": True}
            )

        new_authority_name = parent_doc["name"] if parent_doc else "District Collector Office"
        new_authority_id = str(parent_doc["_id"]) if parent_doc else "district_default"

        # Compute overdue hours
        sla_deadline = ticket.get("sla_deadline")
        overdue_hours = ((now - sla_deadline).total_seconds() / 3600) if sla_deadline else 0

        # Generate escalation complaint
        complaint_preview = (ticket.get("complaint_text") or "")[:300]
        escalation_prompt = _ESCALATION_PROMPT.format(
            ref=f"CT-ESC-{str(ticket.get('_id', ''))[:8].upper()}",
            category=ticket.get("authority_id", "civic issue"),
            address="(see original complaint)",
            orig_authority=ticket.get("authority_name", "Unknown"),
            new_authority=new_authority_name,
            orig_deadline=sla_deadline.strftime("%d %B %Y %H:%M") if sla_deadline else "Unknown",
            overdue_hours=overdue_hours,
            escalation_count=ticket.get("escalation_count", 0) + 1,
            complaint_preview=complaint_preview,
        )
        try:
            escalation_text = await self._llm.generate_text(
                prompt=escalation_prompt,
                system=_ESCALATION_SYSTEM,
                temperature=0.3,
            )
        except LLMError:
            escalation_text = (
                f"ESCALATION NOTICE\n\n"
                f"Ticket for {ticket.get('authority_name')} is overdue by {overdue_hours:.1f} hours. "
                f"Immediate action required from {new_authority_name}."
            )

        # Compute new SLA deadline (48h from now for escalated tickets)
        new_sla = now + timedelta(hours=48)
        history_entry = {
            "status": "escalated",
            "timestamp": now,
            "note": f"Escalated to {new_authority_name} after {overdue_hours:.1f}h SLA breach",
            "updated_by": "sla_escalation_agent",
        }

        await self._db.tickets.update_one(
            {"_id": ticket["_id"]},
            {
                "$set": {
                    "status": "escalated",
                    "authority_id": new_authority_id,
                    "authority_name": new_authority_name,
                    "tier": (ticket.get("tier", 1) + 1),
                    "sla_deadline": new_sla,
                    "complaint_text": escalation_text,
                    "updated_at": now,
                },
                "$inc": {"escalation_count": 1},
                "$push": {"status_history": history_entry},
            },
        )

        # Write audit event
        await self._db.events.insert_one({
            "event_type": "ticket_escalated",
            "report_id": None,
            "issue_id": ticket.get("issue_id"),
            "ticket_id": str(ticket["_id"]),
            "node": "sla_escalation_agent",
            "actor": "system",
            "data": {
                "from_authority": ticket.get("authority_name"),
                "to_authority": new_authority_name,
                "overdue_hours": overdue_hours,
            },
            "error": None,
            "timestamp": now,
        })

    async def _flag_publicly(self, ticket: dict) -> None:
        """Mark ticket as publicly flagged on the leaderboard."""
        await self._db.tickets.update_one(
            {"_id": ticket["_id"]},
            {"$set": {"is_publicly_flagged": True}},
        )
        logger.info("Ticket %s flagged publicly", ticket.get("_id"))
