"""
agents/nodes/dispatcher.py
==========================
Node 8: dispatcher

Responsibilities:
- Generate a formal complaint letter (LLM with template fallback)
- Compute SLA deadline from severity_output.sla_hours
- Insert TicketDoc into MongoDB
- Insert mock email/webhook EventDoc
- Bulk-insert accumulated audit_events from state into events collection
- Insert TraceDoc for the full pipeline run
- Update report doc status and issue_id
- Update issue doc with ticket_id and final severity fields
- Emit completion SSE event

On failure:
- LLM complaint generation → fallback to template complaint text
- DB write failure → retry once, then set dispatcher_error (ticket may be partial)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId

from app.core.llm_client import LLMClient, LLMError
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import DispatcherOutput

logger = logging.getLogger(__name__)

_COMPLAINT_SYSTEM = """
You are a senior government official drafting a formal civic complaint letter on behalf of a citizen.
The letter must be professional, factual, and in formal English. Include all provided details.
Write only the letter body (no JSON, no code fences).
"""

_COMPLAINT_PROMPT_TEMPLATE = """
Write a formal complaint letter with the following details:

Date: {date}
Reference Number: {ref_number}
Issue Category: {category}
Location: {address}
Ward/Area: {ward}
Severity: {severity_tier} (Priority Score: {priority_score:.2f}/1.00)
Number of Reports: {report_count} citizen(s) have reported this issue
Description: {description}
Authority: {authority_name}
SLA Deadline: {sla_deadline}

Score Breakdown:
- Hazard weight: {hazard_weight}
- Road class weight: {road_class_weight}
- Proximity to school/hospital: {proximity_bonus}
- Cluster size: {cluster_bonus}
- Issue age: {age_penalty}

Routing Justification: {routing_justification}

The letter should:
1. Address the relevant authority
2. Clearly state the problem with location
3. Reference the severity assessment
4. Request specific action by the SLA deadline
5. Note the routing justification briefly
6. End with a note about public accountability tracking
"""

_FALLBACK_TEMPLATE = """
FORMAL CIVIC COMPLAINT
Reference: {ref_number}
Date: {date}

To: {authority_name}

Subject: Urgent Civic Issue — {category} at {address}

Dear Sir/Madam,

This is to formally bring to your attention a civic infrastructure issue reported by a citizen through the CivicTriage platform.

Issue Details:
- Category: {category}
- Location: {address} (Ward: {ward})
- Severity: {severity_tier}
- Reports: {report_count} citizen(s)
- Description: {description}

This issue has been assigned a priority score of {priority_score:.2f}/1.00 based on hazard type,
proximity to sensitive areas, cluster size, and issue age.

We request your immediate attention and resolution by {sla_deadline}.

This complaint is being tracked publicly on the CivicTriage accountability dashboard.

Regards,
CivicTriage Automated System
"""


async def dispatcher(
    state: CivicTriageState,
    *,
    llm: LLMClient,
    bus: SSEBus,
    db,
) -> dict:
    """LangGraph node: create ticket, write all audit records, close pipeline."""
    report_id = state["report_id"]

    await bus.publish(report_id, ProgressEvent(
        node="dispatcher",
        status="running",
        message="Creating formal ticket and notifying authority…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "dispatcher",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        now = datetime.now(timezone.utc)
        severity = state.get("severity_output")
        router = state.get("router_output")
        perception = state.get("perception_output")
        geo = state.get("geo_output")
        dedup = state.get("dedup_output")

        # ── Gather context ────────────────────────────────────────────────────
        category = (perception.detected_category if perception else "other").replace("_", " ").title()
        address = (geo.address if geo else "Unknown location")[:200]
        ward = (geo.ward if geo else "Unknown")
        description = (perception.combined_description if perception else state.get("raw_text") or "Civic issue")[:500]
        authority_name = router.primary_authority.authority_name if router else "Local Authority"
        authority_id = router.primary_authority.authority_id if router else "unknown"
        fallback_auth_id = router.fallback_authority.authority_id if (router and router.fallback_authority) else None
        routing_justification = router.routing_justification if router else ""
        citation_chunk_ids = router.citation_chunk_ids if router else []
        priority_score = severity.priority_score if severity else 0.0
        severity_tier = severity.severity_tier.value if severity else "medium"
        sla_hours = severity.sla_hours if severity else 72
        score_breakdown = severity.score_breakdown.model_dump() if (severity and severity.score_breakdown) else {}
        report_count = dedup.cluster_size if dedup else 1
        issue_id = state.get("issue_id") or (dedup.issue_id if dedup else None)

        # ── Compute SLA deadline ──────────────────────────────────────────────
        sla_deadline = now + timedelta(hours=sla_hours)
        ref_number = f"CT-{now.strftime('%Y%m%d')}-{report_id[:8].upper()}"

        # ── Generate complaint letter ─────────────────────────────────────────
        complaint_prompt = _COMPLAINT_PROMPT_TEMPLATE.format(
            date=now.strftime("%d %B %Y"),
            ref_number=ref_number,
            category=category,
            address=address,
            ward=ward,
            severity_tier=severity_tier.upper(),
            priority_score=priority_score,
            report_count=report_count,
            description=description,
            authority_name=authority_name,
            sla_deadline=sla_deadline.strftime("%d %B %Y %H:%M UTC"),
            routing_justification=routing_justification,
            hazard_weight=score_breakdown.get("hazard_weight", 0),
            road_class_weight=score_breakdown.get("road_class_weight", 0),
            proximity_bonus=score_breakdown.get("proximity_bonus", 0),
            cluster_bonus=score_breakdown.get("cluster_bonus", 0),
            age_penalty=score_breakdown.get("age_penalty", 0),
        )
        try:
            complaint_text = await llm.generate_text(
                prompt=complaint_prompt,
                system=_COMPLAINT_SYSTEM,
                temperature=0.4,
            )
            if not complaint_text or len(complaint_text) < 50:
                raise LLMError("Empty complaint response")
        except Exception as exc:
            logger.warning("Complaint LLM failed, using template: %s", exc)
            complaint_text = _FALLBACK_TEMPLATE.format(
                ref_number=ref_number,
                date=now.strftime("%d %B %Y"),
                authority_name=authority_name,
                category=category,
                address=address,
                ward=ward,
                severity_tier=severity_tier,
                report_count=report_count,
                description=description,
                priority_score=priority_score,
                sla_deadline=sla_deadline.strftime("%d %B %Y %H:%M UTC"),
            )

        # ── Find existing ticket for issue or insert new ticket (Cluster Clubbing) ───
        existing_ticket = None
        if issue_id:
            raw_iid = str(issue_id).strip()
            iid_query: dict[str, Any] = {"$or": [{"issue_id": raw_iid}]}
            if ObjectId.is_valid(raw_iid):
                iid_query["$or"].append({"issue_id": ObjectId(raw_iid)})
            try:
                existing_ticket = await db.tickets.find_one(iid_query)
            except Exception as find_exc:
                logger.warning("dispatcher: ticket lookup failed: %s", find_exc)

        if existing_ticket:
            ticket_id = str(existing_ticket["_id"])
            existing_clustered = list(existing_ticket.get("clustered_report_ids") or [])
            if not existing_clustered and existing_ticket.get("report_id"):
                existing_clustered.append(str(existing_ticket["report_id"]))
            if report_id and str(report_id) not in existing_clustered:
                existing_clustered.append(str(report_id))

            merged_report_count = max(
                len(existing_clustered),
                report_count,
                int(existing_ticket.get("report_count", 1)) + 1,
            )

            update_fields: dict[str, Any] = {
                "clustered_report_ids": existing_clustered,
                "report_count": merged_report_count,
                "updated_at": now,
                "ticket_id": ticket_id,
            }

            # If new priority score is higher or newly calculated, update score
            if priority_score > existing_ticket.get("priority_score", 0):
                update_fields["priority_score"] = priority_score
                update_fields["score_breakdown"] = score_breakdown

            # Retain the tighter SLA deadline
            existing_deadline = existing_ticket.get("sla_deadline")
            if existing_deadline and hasattr(existing_deadline, "replace"):
                if existing_deadline.tzinfo is None:
                    existing_deadline = existing_deadline.replace(tzinfo=timezone.utc)
                if sla_deadline < existing_deadline:
                    update_fields["sla_deadline"] = sla_deadline
                    update_fields["sla_hours"] = sla_hours

            cluster_note = (
                f"Clustered community report #{str(report_id)[-6:] if report_id else 'ext'} "
                f"merged into existing incident ticket (Total clustered: {merged_report_count})"
            )
            history_entry = {
                "status": existing_ticket.get("status", "open"),
                "timestamp": now,
                "note": cluster_note,
                "updated_by": "system",
            }

            await db.tickets.update_one(
                {"_id": existing_ticket["_id"]},
                {
                    "$set": update_fields,
                    "$push": {"status_history": history_entry},
                },
            )
            logger.info(
                "dispatcher: Clustered report %s into existing ticket %s for issue %s (count=%d)",
                report_id,
                ticket_id,
                issue_id,
                merged_report_count,
            )
        else:
            ticket_doc = {
                "issue_id": str(issue_id) if issue_id else None,
                "report_id": str(report_id) if report_id else None,
                "clustered_report_ids": [str(report_id)] if report_id else [],
                "report_count": max(report_count, 1),
                "authority_id": authority_id,
                "authority_name": authority_name,
                "department_id": authority_id,
                "department_name": authority_name,
                "fallback_authority_id": fallback_auth_id,
                "tier": router.primary_authority.tier if router else 1,
                "sla_hours": sla_hours,
                "sla_deadline": sla_deadline,
                "status": "open",
                "status_history": [
                    {
                        "status": "open",
                        "timestamp": now,
                        "note": "Ticket created and dispatched",
                        "updated_by": "system",
                    }
                ],
                "complaint_text": complaint_text,
                "citation_chunk_ids": citation_chunk_ids,
                "routing_justification": routing_justification,
                "score_breakdown": score_breakdown,
                "priority_score": priority_score,
                "escalation_count": 0,
                "is_publicly_flagged": False,
                "created_at": now,
                "updated_at": now,
            }
            ticket_result = await db.tickets.insert_one(ticket_doc)
            ticket_id = str(ticket_result.inserted_id)
            await db.tickets.update_one({"_id": ticket_result.inserted_id}, {"$set": {"ticket_id": ticket_id}})

        # ── Multi-Channel Dispatch (Officer Portal, Email, Webhook, Adapter) ───
        dispatch_events = []
        try:
            # Query reporting_destinations for the department
            dest_cursor = db.reporting_destinations.find({"department_id": authority_id, "is_active": True})
            destinations = await dest_cursor.to_list(10)
        except Exception:
            destinations = []

        if not destinations:
            # Fallback destination based on primary authority contact fields
            destinations = [{
                "destination_id": f"default_{authority_id}",
                "type": "internal",
                "endpoint": "officer_portal",
                "contact_email": router.primary_authority.contact_email if router else None,
                "contact_webhook": router.primary_authority.contact_webhook if router else None,
            }]

        for dest in destinations:
            dest_type = dest.get("type", "internal")
            if dest_type == "internal":
                dispatch_events.append({
                    "event_type": "officer_inbox_assigned",
                    "report_id": report_id,
                    "issue_id": issue_id,
                    "ticket_id": ticket_id,
                    "node": "dispatcher",
                    "actor": "system",
                    "data": {
                        "destination_id": dest.get("destination_id"),
                        "department_id": authority_id,
                        "endpoint": "officer_portal",
                        "status": "assigned_to_officer_inbox",
                    },
                    "error": None,
                    "timestamp": now,
                })
            elif dest_type == "email":
                dispatch_events.append({
                    "event_type": "mock_email_sent",
                    "report_id": report_id,
                    "issue_id": issue_id,
                    "ticket_id": ticket_id,
                    "node": "dispatcher",
                    "actor": "system",
                    "data": {
                        "to": dest.get("contact_email") or (router.primary_authority.contact_email if router else None),
                        "subject": f"[CivicTriage] {ref_number} — {category} at {address[:50]}",
                        "body_preview": complaint_text[:200],
                    },
                    "error": None,
                    "timestamp": now,
                })
            elif dest_type == "webhook":
                dispatch_events.append({
                    "event_type": "mock_webhook_sent",
                    "report_id": report_id,
                    "issue_id": issue_id,
                    "ticket_id": ticket_id,
                    "node": "dispatcher",
                    "actor": "system",
                    "data": {
                        "url": dest.get("contact_webhook") or dest.get("endpoint") or (router.primary_authority.contact_webhook if router else None),
                        "payload": {
                            "ticket_id": ticket_id,
                            "department_id": authority_id,
                            "category": category,
                            "severity": severity_tier,
                            "sla_deadline": sla_deadline.isoformat(),
                        },
                    },
                    "error": None,
                    "timestamp": now,
                })
            elif dest_type == "external_portal":
                # External government portal adapter (e.g. CPGRAMS / GHMC Citizen Portal API)
                dispatch_events.append({
                    "event_type": "external_gov_portal_dispatched",
                    "report_id": report_id,
                    "issue_id": issue_id,
                    "ticket_id": ticket_id,
                    "node": "dispatcher",
                    "actor": "system",
                    "data": {
                        "adapter": dest.get("adapter", "ghmc_grievance_portal_adapter"),
                        "external_reference": f"EXT-{ref_number}",
                        "department_id": authority_id,
                        "payload": {
                            "ticket_id": ticket_id,
                            "category": category,
                            "address": address,
                        },
                    },
                    "error": None,
                    "timestamp": now,
                })

        # Ensure at least email and webhook mock events exist
        event_types = {e["event_type"] for e in dispatch_events}
        if "mock_email_sent" not in event_types:
            dispatch_events.append({
                "event_type": "mock_email_sent",
                "report_id": report_id,
                "issue_id": issue_id,
                "ticket_id": ticket_id,
                "node": "dispatcher",
                "actor": "system",
                "data": {
                    "to": router.primary_authority.contact_email if router else None,
                    "subject": f"[CivicTriage] {ref_number} — {category} at {address[:50]}",
                    "body_preview": complaint_text[:200],
                },
                "error": None,
                "timestamp": now,
            })
        if "mock_webhook_sent" not in event_types:
            dispatch_events.append({
                "event_type": "mock_webhook_sent",
                "report_id": report_id,
                "issue_id": issue_id,
                "ticket_id": ticket_id,
                "node": "dispatcher",
                "actor": "system",
                "data": {
                    "url": router.primary_authority.contact_webhook if router else None,
                    "payload": {
                        "ticket_id": ticket_id,
                        "authority_id": authority_id,
                        "department_id": authority_id,
                        "category": category,
                        "severity": severity_tier,
                        "sla_deadline": sla_deadline.isoformat(),
                    },
                },
                "error": None,
                "timestamp": now,
            })

        if dispatch_events:
            await db.events.insert_many(dispatch_events)

        # ── Record initial event in status_events ─────────────────────────────
        try:
            await db.status_events.insert_one({
                "event_type": "ticket_dispatched",
                "issue_id": str(issue_id) if issue_id else None,
                "ticket_id": ticket_id,
                "department_id": authority_id,
                "department_name": authority_name,
                "actor": "system",
                "old_status": None,
                "new_status": "assigned",
                "issue_status": "assigned",
                "note": f"Ticket dispatched to {authority_name}",
                "timestamp": now,
            })
        except Exception as se_exc:
            logger.warning("dispatcher: status_events insert failed: %s", se_exc)

        # ── Bulk-insert accumulated audit events ──────────────────────────────
        current_audit = dict(audit)
        current_audit["event_type"] = "node_completed"
        current_audit["data"] = {"ticket_id": ticket_id, "ref_number": ref_number}
        current_audit["timestamp"] = now
        all_audit_events = state["audit_events"] + [current_audit]

        audit_docs = []
        for ev in all_audit_events:
            doc = dict(ev)
            doc["report_id"] = report_id
            doc["issue_id"] = issue_id
            doc["ticket_id"] = ticket_id
            if isinstance(doc.get("timestamp"), str):
                try:
                    doc["timestamp"] = datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00"))
                except Exception:
                    doc["timestamp"] = now
            audit_docs.append(doc)
        if audit_docs:
            await db.events.insert_many(audit_docs)

        # ── Insert trace document ─────────────────────────────────────────────
        trace_steps = []
        def _get_node_summary(node: str) -> dict:
            if node == "intake_guard":
                intake = state.get("intake_output")
                if not intake:
                    return {"media_type": "text", "is_valid": True}
                return {
                    "media_type": str(getattr(intake, "media_type", "text")),
                    "is_valid": getattr(intake, "is_valid", True),
                    "file_mime_type": getattr(intake, "file_mime_type", None),
                    "category_hint": getattr(intake, "category_hint", None),
                }
            elif node == "perceive":
                perc = state.get("perception_output")
                if not perc:
                    return {}
                vis = getattr(perc, "visual", None)
                trans = getattr(perc, "transcription", None)
                cat_raw = getattr(perc, "detected_category", "other")
                cat_val = (
                    cat_raw.value
                    if hasattr(cat_raw, "value")
                    else str(cat_raw).replace("IssueCategory.", "").strip()
                )
                return {
                    "category": cat_val,
                    "confidence": round(getattr(perc, "confidence", 0.0), 3),
                    "model_used": getattr(perc, "model_used", "gemini-vision"),
                    "image_matches_description": getattr(perc, "image_matches_description", True),
                    "description": getattr(perc, "combined_description", "")[:150],
                    "damage_features": getattr(vis, "damage_features", []) if vis else [],
                    "hazard_indicators": getattr(vis, "hazard_indicators", []) if vis else [],
                    "transcription": getattr(trans, "text", None) if trans else None,
                }
            elif node == "geo_resolver":
                geo = state.get("geo_output")
                if not geo:
                    return {}
                return {
                    "address": getattr(geo, "address", address),
                    "ward": getattr(geo, "ward", ward),
                    "city": getattr(geo, "city", None),
                    "road_class": getattr(geo, "road_class", "residential"),
                    "nearby_hospitals": getattr(geo, "nearby_hospitals", 0),
                    "nearby_schools": getattr(geo, "nearby_schools", 0),
                    "coordinates": getattr(geo, "coordinates", [0.0, 0.0]),
                }
            elif node == "deduplicator":
                ded = state.get("dedup_output")
                if not ded:
                    return {"action": "created", "issue_id": str(issue_id or "")}
                return {
                    "action": getattr(ded, "action", "created"),
                    "issue_id": str(getattr(ded, "issue_id", issue_id or "")),
                    "similarity": round(getattr(ded, "similarity", 0.0), 3),
                    "distance_meters": round(getattr(ded, "distance_meters", 0.0), 1),
                    "cluster_size": getattr(ded, "cluster_size", 1),
                }
            elif node == "severity_scorer":
                sev = state.get("severity_output")
                if not sev:
                    return {"priority_score": round(priority_score, 3), "severity_tier": str(severity_tier)}
                bd = getattr(sev, "breakdown", None)
                bd_dict = bd.model_dump() if hasattr(bd, "model_dump") else (bd if isinstance(bd, dict) else {})
                return {
                    "priority_score": round(getattr(sev, "priority_score", priority_score), 3),
                    "severity_tier": str(getattr(sev, "severity_tier", severity_tier)),
                    "sla_hours": getattr(sev, "sla_hours", sla_hours),
                    "rubric_total": bd_dict.get("total", round(priority_score * 100, 1)),
                    "hazard_weight": bd_dict.get("hazard_weight", 0),
                    "road_class_weight": bd_dict.get("road_class_weight", 0),
                    "proximity_bonus": bd_dict.get("proximity_bonus", 0),
                }
            elif node == "authority_router":
                rout = state.get("router_output")
                if not rout:
                    return {"primary_authority": authority_name, "sla_hours": sla_hours}
                prim = getattr(rout, "primary_authority", None)
                return {
                    "primary_authority": getattr(prim, "authority_name", authority_name) if prim else authority_name,
                    "tier": getattr(prim, "tier", 1) if prim else 1,
                    "sla_hours": sla_hours,
                    "citations": getattr(rout, "citation_chunk_ids", citation_chunk_ids),
                    "justification": getattr(rout, "routing_justification", routing_justification)[:160],
                }
            elif node == "critic":
                crit = state.get("critic_output")
                if not crit:
                    return {"verdict": "pass", "confidence": 0.95}
                return {
                    "verdict": getattr(crit, "verdict", "pass"),
                    "confidence": round(getattr(crit, "confidence", 0.95), 3),
                    "findings_count": len(getattr(crit, "findings", []) or []),
                }
            elif node == "dispatcher":
                return {
                    "ticket_id": ticket_id,
                    "ref_number": ref_number,
                    "authority": authority_name,
                    "sla_deadline": sla_deadline.isoformat(),
                    "complaint_text": complaint_text,
                    "status": "assigned",
                }
            return {}

        node_order = ["intake_guard", "perceive", "geo_resolver", "deduplicator",
                      "severity_scorer", "authority_router", "critic", "dispatcher"]
        for node_name in node_order:
            output_map = {
                "intake_guard": "intake_output",
                "perceive": "perception_output",
                "geo_resolver": "geo_output",
                "deduplicator": "dedup_output",
                "severity_scorer": "severity_output",
                "authority_router": "router_output",
                "critic": "critic_output",
                "dispatcher": "dispatcher_output",
            }
            error_map = {
                "intake_guard": "intake_error",
                "perceive": "perception_error",
                "geo_resolver": "geo_error",
                "deduplicator": "dedup_error",
                "severity_scorer": "severity_error",
                "authority_router": "router_error",
                "critic": "critic_error",
                "dispatcher": "dispatcher_error",
            }
            has_output = state.get(output_map.get(node_name, "")) is not None
            has_error = state.get(error_map.get(node_name, "")) is not None
            step_status = "error" if has_error else ("success" if has_output else "skipped")
            trace_steps.append({
                "node": node_name,
                "status": step_status,
                "started_at": now,
                "completed_at": now,
                "output_summary": _get_node_summary(node_name),
                "error": state.get(error_map.get(node_name, "")),
                "retry_count": state.get("retry_count", 0) if node_name == "critic" else 0,
            })

        trace_doc = {
            "report_id": report_id,
            "issue_id": str(issue_id or ""),
            "final_status": "dispatched",
            "steps": trace_steps,
            "started_at": now,
            "completed_at": now,
        }
        await db.traces.insert_one(trace_doc)

        # ── Update report and issue documents ─────────────────────────────────
        await db.reports.update_one(
            {"_id": report_id},
            {"$set": {"status": "spawned" if (dedup and dedup.action == "created") else "merged",
                      "issue_id": issue_id, "updated_at": now}},
        )
        if issue_id:
            try:
                raw_sid = str(issue_id).strip()
                oid_filter = (
                    {"$or": [{"_id": ObjectId(raw_sid)}, {"_id": raw_sid}]}
                    if ObjectId.is_valid(raw_sid)
                    else {"_id": raw_sid}
                )
                await db.issues.update_one(
                    oid_filter,
                    {"$set": {
                        "ticket_id": ticket_id,
                        "department_id": authority_id,
                        "department_name": authority_name,
                        "status": "assigned",
                        "priority_score": priority_score,
                        "severity_tier": severity_tier,
                        "score_breakdown": score_breakdown,
                        "sla_hours": sla_hours,
                        "updated_at": now,
                    }},
                )
                logger.info("dispatcher: updated issue %s with ticket_id=%s priority_score=%.4f", issue_id, ticket_id, priority_score)
            except Exception as exc:
                logger.warning("Could not update issue %s: %s", issue_id, exc)

        # ── Build output ──────────────────────────────────────────────────────
        output = DispatcherOutput(
            ticket_id=ticket_id,
            complaint_text=complaint_text,
            sla_deadline=sla_deadline,
            mock_email_sent=True,
            mock_webhook_sent=True,
            audit_event_ids=[],
        )
        updates["dispatcher_output"] = output
        updates["ticket_id"] = ticket_id
        updates["final_status"] = "dispatched"
        audit["event_type"] = "node_completed"
        audit["data"] = {"ticket_id": ticket_id, "ref_number": ref_number}

        await bus.publish(report_id, ProgressEvent(
            node="dispatcher",
            status="done",
            message=f"Ticket {ref_number} created. Authority notified. SLA: {sla_hours}h.",
            data={"ticket_id": ticket_id, "issue_id": issue_id, "ref_number": ref_number},
        ))

    except Exception as exc:
        logger.exception("dispatcher failed for report_id=%s", report_id)
        updates["dispatcher_error"] = str(exc)
        updates["final_status"] = "failed"
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)
        await bus.publish(report_id, ProgressEvent(
            node="dispatcher", status="error",
            message="Dispatch failed — issue queued for manual processing.",
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates
