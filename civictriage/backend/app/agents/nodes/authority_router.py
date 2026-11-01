"""
agents/nodes/authority_router.py
=================================
Node 6: authority_router (Rule-Based Routing Engine — replaces RAG)

Responsibilities:
1. LLM call to extract {category, subtype, asset_type, confidence, is_ambiguous}
   from the combined perception + geo context.
2. MongoDB geospatial lookup: find matching jurisdictions via $geoIntersects
   on the `jurisdictions` collection (2dsphere).
3. Python Rule Engine: query `routing_rules` collection with
   {category, subtype/any, asset_type/any, is_active: true}, sort by priority.
4. Match resolution with explicit precedence:
   - confidence < CRITIC_MIN_CONFIDENCE  → human_review
   - 0 rules matched                     → human_review
   - 1+ rules matched                    → use highest priority (lowest number)
   - rule.requires_human_review == True  → human_review
5. Build RuleBasedRouterOutput with department info, rule_id, source_doc refs.
6. Enrich primary_authority contact info from `departments` collection.

Output is stored in state["router_output"] as an AuthorityRouterOutput
(preserved for backward compatibility with critic/dispatcher).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm_client import LLMClient
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import AuthorityRef, AuthorityRouterOutput
from app.services.city_directory import (
    CITY_DEPARTMENT_REGISTRY,
    generate_dynamic_city_department,
    lookup_city_from_coords,
    normalize_city_name,
    resolve_city_jurisdiction,
)

logger = logging.getLogger(__name__)

# ── Structured schema for LLM feature extraction ──────────────────────────────

class _RoutingFeatureOutput(BaseModel):
    subtype: str = Field(default="any", description="Specific defect subtype")
    asset_type: str = Field(default="unknown", description="Infrastructure asset type")
    confidence: float = Field(default=0.85, description="Extraction confidence")
    is_ambiguous: bool = Field(default=False, description="Ambiguity flag")
    ambiguity_reason: Optional[str] = Field(default="", description="Reason if ambiguous")

# ── LLM prompt for feature extraction ────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """\
You are a civic infrastructure expert. Extract routing metadata from a civic issue report.
Return ONLY valid JSON — no markdown fences, no extra text.\
"""

_EXTRACTION_PROMPT_TEMPLATE = """\
Civic Issue Report:
  Category: {category}
  Description: {description}
  Location: {address}, Ward: {ward}, City: {city}
  Road Class: {road_class}
  Nearby POIs: {pois}

Extract routing metadata as JSON:
{{
  "subtype": "<specific subtype: pothole|road_collapse|construction_damage|main_break|pipeline_leak|contamination|overflow|blockage|bulk_dumping|missed_collection|construction_debris|outage|damaged_pole|fallen_tree|overgrown_branch|industrial_discharge|open_burning|waterlogging|blocked_drain|footpath_encroachment|illegal_construction|any>",
  "asset_type": "<municipal_road|national_highway|state_highway|construction_zone|water_main|water_pipeline|sewer_main|manhole|storm_drain|public_streetlight|public_tree|public_road|public_footpath|public_land|residential_zone|industrial_zone|any|unknown>",
  "confidence": <0.0 to 1.0>,
  "is_ambiguous": <true|false>,
  "ambiguity_reason": "<optional reason if ambiguous>"
}}

Rules:
- subtype should be the most specific subtype that fits; use "any" only if truly unclear
- asset_type: "national_highway" for NH roads, "municipal_road" for GHMC city roads,
  "state_highway" for state roads, "unknown" if ownership unclear
- confidence: your confidence in the subtype + asset_type extraction (0.0-1.0)
- is_ambiguous: true if ownership or jurisdiction is unclear
"""


async def _extract_routing_features(
    llm: LLMClient,
    category: str,
    description: str,
    address: str,
    ward: str,
    city: str,
    road_class: str,
    pois: str,
    report_id: str,
) -> dict:
    """
    Use LLM to extract subtype, asset_type, confidence, is_ambiguous.
    Returns a dict with those keys on success, or fallback defaults on failure.
    """
    prompt = _EXTRACTION_PROMPT_TEMPLATE.format(
        category=category,
        description=description[:400],
        address=address,
        ward=ward,
        city=city,
        road_class=road_class or "unknown",
        pois=pois[:200] if pois else "none",
    )
    try:
        result = await llm.generate_structured(
            prompt=prompt,
            response_model=_RoutingFeatureOutput,
            system=_EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1,
            demo_cache_key=f"{report_id}_router_features",
        )
        return {
            "subtype": str(result.subtype or "any"),
            "asset_type": str(result.asset_type or "unknown"),
            "confidence": float(result.confidence if result.confidence is not None else 0.85),
            "is_ambiguous": bool(result.is_ambiguous),
            "ambiguity_reason": str(result.ambiguity_reason or ""),
        }
    except Exception as exc:
        logger.warning(
            "authority_router: LLM feature extraction failed for report_id=%s: %s — using fallback",
            report_id, exc,
        )
        return _category_fallback_features(category)


def _category_fallback_features(category: str) -> dict:
    """
    Deterministic fallback feature extraction when LLM fails.
    Maps category to most common subtype + asset_type combo.
    """
    defaults = {
        "road_damage":   {"subtype": "pothole",       "asset_type": "municipal_road"},
        "water_leak":    {"subtype": "pipeline_leak", "asset_type": "water_pipeline"},
        "sewage":        {"subtype": "blockage",      "asset_type": "manhole"},
        "garbage":       {"subtype": "bulk_dumping",  "asset_type": "public_land"},
        "streetlight":   {"subtype": "outage",        "asset_type": "public_streetlight"},
        "pollution":     {"subtype": "any",           "asset_type": "any"},
        "encroachment":  {"subtype": "any",           "asset_type": "public_land"},
        "tree_hazard":   {"subtype": "fallen_tree",   "asset_type": "public_tree"},
        "flood":         {"subtype": "waterlogging",  "asset_type": "any"},
        "other":         {"subtype": "any",           "asset_type": "any"},
    }
    d = defaults.get(category, {"subtype": "any", "asset_type": "any"})
    return {
        "subtype": d["subtype"],
        "asset_type": d["asset_type"],
        "confidence": 0.85,
        "is_ambiguous": False,
        "ambiguity_reason": "",
    }


async def _geo_jurisdiction_lookup(
    db,
    lon: Optional[float],
    lat: Optional[float],
    city: Optional[str] = None,
) -> Optional[dict]:
    """
    Find the jurisdiction whose GeoJSON boundary contains the given point,
    or resolve the appropriate city jurisdiction based on coordinates and city name.
    Ensures complaints outside Hyderabad are assigned to their proper city jurisdiction.
    """
    # 1. Try geospatial $geoIntersects on boundary polygons
    if lon is not None and lat is not None:
        try:
            cursor = db.jurisdictions.find({
                "boundary": {
                    "$geoIntersects": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat],
                        }
                    }
                },
                "is_active": True,
            })
            jurisdictions = await cursor.to_list(10)
            if jurisdictions:
                type_priority = {"ward": 0, "circle": 1, "zone": 2, "district": 3, "state": 4}
                jurisdictions.sort(key=lambda j: type_priority.get(j.get("zone_type", "district"), 5))
                logger.debug(
                    "authority_router: found %d polygon jurisdiction(s) for (%.4f, %.4f)",
                    len(jurisdictions), lon, lat
                )
                return jurisdictions[0]
        except Exception as geo_exc:
            logger.warning("authority_router: geo jurisdiction lookup failed: %s", geo_exc)

    # 2. If coordinates point to a specific city or city was resolved, return that city's jurisdiction
    resolved_city = normalize_city_name(city)
    if not resolved_city and lat is not None and lon is not None:
        resolved_city = lookup_city_from_coords(lat, lon)

    if resolved_city and resolved_city.lower() != "hyderabad":
        return resolve_city_jurisdiction(resolved_city, lat=lat, lon=lon)

    # 3. Fallback for Hyderabad
    try:
        default = await db.jurisdictions.find_one({"jurisdiction_id": "hyd_default", "is_active": True})
        if default:
            return default
    except Exception:
        pass

    return resolve_city_jurisdiction(resolved_city or "Hyderabad", lat=lat, lon=lon)


async def _query_routing_rules(
    db,
    category: str,
    subtype: str,
    asset_type: str,
) -> list[dict]:
    """
    Query `routing_rules` collection with explicit precedence logic.

    Match strategy (tiered, most-specific first):
    Tier 1: category + specific subtype + specific asset_type
    Tier 2: category + specific subtype + asset_type="any"
    Tier 3: category + subtype="any"  + specific asset_type
    Tier 4: category + subtype="any"  + asset_type="any"

    Returns all matched rules sorted by priority (ascending).
    """
    all_active = []
    try:
        cursor = db.routing_rules.find({"category": category, "is_active": True})
        all_active = await cursor.to_list(50)
    except Exception as exc:
        logger.warning("authority_router: routing_rules query failed: %s", exc)
        return []

    if not all_active:
        return []

    matched: list[dict] = []
    for rule in all_active:
        rule_subtype = rule.get("subtype", "any")
        rule_asset = rule.get("asset_type", "any")

        subtype_match = (
            (rule_subtype == "any")
            or (rule_subtype == subtype)
            or (subtype in ("any", "unknown", ""))
        )
        asset_match = (
            (rule_asset == "any")
            or (rule_asset == asset_type)
            or (asset_type in ("any", "unknown", ""))
        )

        if subtype_match and asset_match:
            # Specificity ranking: exact subtype match (+10), exact asset match (+10)
            specificity = 0
            if rule_subtype != "any" and rule_subtype == subtype:
                specificity += 10
            if rule_asset != "any" and rule_asset == asset_type:
                specificity += 10
            matched.append((specificity, rule.get("priority", 999), rule))

    # Sort primarily by specificity descending (most specific first), then priority ascending
    matched.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in matched]


async def _resolve_department(
    db,
    department_id: str,
    city: Optional[str] = None,
) -> Optional[dict]:
    """
    Fetch department document, routing to the correct city's department for that category.
    If the city is outside Hyderabad (e.g. Bengaluru, Mumbai, Delhi, Chennai, Kolkata, Pune),
    allocates to the verified department of that city (BBMP, BWSSB, BESCOM, BMC, MCD, DJB, etc.).
    """
    clean_city = normalize_city_name(city)

    # 1. Non-Hyderabad city: resolve to that city's dedicated department
    if clean_city and clean_city.lower() != "hyderabad":
        if clean_city in CITY_DEPARTMENT_REGISTRY:
            city_depts = CITY_DEPARTMENT_REGISTRY[clean_city]
            if department_id in city_depts:
                return city_depts[department_id]
            return city_depts.get("general_desk")

        # Any other Indian municipality or district: dynamically build official department profile
        return generate_dynamic_city_department(department_id, clean_city)

    # 2. Hyderabad or default city: fetch from MongoDB / seed departments
    try:
        dept = await db.departments.find_one({"department_id": department_id})
        if dept:
            return dept
        # Fallback: try `authorities` collection (backward compat)
        auth = await db.authorities.find_one({
            "$or": [
                {"authority_id": department_id},
                {"name": {"$regex": department_id, "$options": "i"}},
            ]
        })
        return auth
    except Exception as exc:
        logger.warning("authority_router: department lookup failed for %s: %s", department_id, exc)
        return None


def _build_router_output(
    *,
    department: Optional[dict],
    rule: Optional[dict],
    confidence: float,
    requires_human_review: bool,
    justification: str,
    source_doc_ids: list[str],
    city: Optional[str] = None,
) -> AuthorityRouterOutput:
    """Build AuthorityRouterOutput from matched rule + department for the specified city."""
    clean_city = normalize_city_name(city) or "Municipal"
    slug = "".join(ch for ch in clean_city.lower() if ch.isalnum()) or "municipal"

    if department:
        primary = AuthorityRef(
            authority_id=str(department.get("department_id") or department.get("authority_id") or department.get("_id", f"{slug}_dept")),
            authority_name=str(department.get("name") or department.get("short_name", f"{clean_city} Municipal Department")),
            tier=int(department.get("tier", 1)),
            contact_email=department.get("contact_email") or f"grievance@{slug}.municipal.gov.in",
            contact_webhook=department.get("contact_webhook"),
        )
    else:
        primary = AuthorityRef(
            authority_id=f"{slug}_general_desk",
            authority_name=f"{clean_city} Municipal General Grievance Desk",
            tier=2,
            contact_email=f"grievance@{slug}.municipal.gov.in",
            contact_webhook=None,
        )

    # Store rule_id as a citation (replaces KB chunk IDs)
    citation_ids: list[str] = []
    if rule:
        citation_ids.append(rule["rule_id"])
    citation_ids.extend(source_doc_ids[:3])  # include up to 3 source doc IDs

    return AuthorityRouterOutput(
        primary_authority=primary,
        fallback_authority=None,
        confidence=confidence,
        citation_chunk_ids=citation_ids,  # now contains rule_id + source doc IDs
        routing_justification=justification,
    )


async def authority_router(
    state: CivicTriageState,
    *,
    llm: LLMClient,
    bus: SSEBus,
    db,
) -> dict:
    """
    LangGraph node — Rule-Based Authority Router (replaces RAG).

    Returns updated state: router_output and/or router_error.
    """
    report_id = state["report_id"]
    settings = get_settings()

    await bus.publish(report_id, ProgressEvent(
        node="authority_router",
        status="running",
        message="Identifying responsible department via rule-based routing…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "authority_router",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        # ── Step 1: Extract context from pipeline state ───────────────────────
        perception = state.get("perception_output")
        geo = state.get("geo_output")

        category = str(perception.detected_category.value if perception else "other")
        description = perception.combined_description if perception else (state.get("raw_text") or "")
        ward = geo.ward if geo else ""
        raw_city = geo.city if geo else ""
        address = geo.address if geo else ""
        road_class = geo.road_class if geo else ""

        # Build POI summary
        pois_str = ""
        if geo and geo.nearby_pois:
            pois_str = ", ".join(
                f"{p.poi_type}({p.distance_meters:.0f}m)" for p in geo.nearby_pois[:5]
            )

        # Get GPS coordinates for geospatial lookup
        lon: Optional[float] = None
        lat: Optional[float] = None
        if geo and geo.location:
            lon = geo.location.coordinates[0]
            lat = geo.location.coordinates[1]
        elif state.get("gps_lat") is not None and state.get("gps_lng") is not None:
            lat = float(state["gps_lat"])
            lon = float(state["gps_lng"])

        # Resolve normalized city from reverse geocode or GPS coordinate lookup
        city = normalize_city_name(raw_city)
        if not city and lat is not None and lon is not None:
            city = lookup_city_from_coords(lat, lon)
        if not city:
            city = "Hyderabad"

        # ── Step 2: LLM feature extraction ───────────────────────────────────
        features = await _extract_routing_features(
            llm=llm,
            category=category,
            description=description,
            address=address,
            ward=ward or "",
            city=city,
            road_class=road_class or "",
            pois=pois_str,
            report_id=report_id,
        )

        subtype = features["subtype"]
        asset_type = features["asset_type"]
        llm_confidence = features["confidence"]
        is_ambiguous = features["is_ambiguous"]

        logger.info(
            "authority_router: city=%s extracted subtype=%s asset_type=%s confidence=%.2f ambiguous=%s for report_id=%s",
            city, subtype, asset_type, llm_confidence, is_ambiguous, report_id,
        )

        # ── Step 3: Geospatial jurisdiction lookup ────────────────────────────
        jurisdiction = await _geo_jurisdiction_lookup(db, lon, lat, city=city)
        jurisdiction_name = jurisdiction.get("name", f"{city} Municipal Zone") if jurisdiction else f"{city} Municipal Zone"
        jurisdiction_id = jurisdiction.get("jurisdiction_id", "") if jurisdiction else ""

        logger.debug(
            "authority_router: jurisdiction=%s for report_id=%s",
            jurisdiction_name, report_id,
        )

        # ── Step 4: Check confidence threshold ───────────────────────────────
        if llm_confidence < settings.CRITIC_MIN_CONFIDENCE:
            # Low confidence → human review (critic will enforce this, but we signal early)
            logger.warning(
                "authority_router: low LLM confidence %.2f < %.2f for report_id=%s — routing to human review",
                llm_confidence, settings.CRITIC_MIN_CONFIDENCE, report_id,
            )
            router_output = _build_router_output(
                department=None,
                rule=None,
                confidence=llm_confidence,
                requires_human_review=True,
                justification=(
                    f"Low classification confidence ({llm_confidence:.0%}) in {city} — "
                    f"routing to human review for manual triage."
                ),
                source_doc_ids=[],
                city=city,
            )
            updates["router_output"] = router_output
            updates["human_review_reason"] = f"low_confidence:{llm_confidence:.2f}"
            audit["event_type"] = "node_completed"
            audit["data"] = {"confidence": llm_confidence, "human_review": True}
            await bus.publish(report_id, ProgressEvent(
                node="authority_router",
                status="done",
                message=f"Low confidence routing — flagged for human review ({llm_confidence:.0%})",
            ))
            updates["audit_events"] = state["audit_events"] + [audit]
            return updates

        # ── Step 5: Query routing rules ───────────────────────────────────────
        matched_rules = await _query_routing_rules(db, category, subtype, asset_type)

        # ── Step 6: Rule resolution with precedence ───────────────────────────
        chosen_rule: Optional[dict] = None
        human_review_reason: Optional[str] = None

        if not matched_rules:
            # No rules found → escalate to human review
            logger.warning(
                "authority_router: no routing rules matched category=%s subtype=%s asset=%s for report_id=%s",
                category, subtype, asset_type, report_id,
            )
            human_review_reason = "no_matching_rule"
        elif is_ambiguous:
            # Ambiguous ownership → human review
            logger.warning(
                "authority_router: ambiguous routing for report_id=%s: %s",
                report_id, features.get("ambiguity_reason", ""),
            )
            # Still use best rule but flag for human review
            chosen_rule = matched_rules[0]
            human_review_reason = "ambiguous_ownership"
        else:
            chosen_rule = matched_rules[0]
            if chosen_rule.get("requires_human_review", False):
                human_review_reason = "rule_requires_review"

        # ── Step 7: Resolve department ────────────────────────────────────────
        department: Optional[dict] = None
        if chosen_rule:
            dept_id = chosen_rule.get("department_id", "general_desk")
            department = await _resolve_department(db, dept_id, city=city)
            if not department:
                logger.warning(
                    "authority_router: department '%s' not found for city '%s' — using general_desk",
                    dept_id, city,
                )

        if not department:
            # Fallback department for that specific city
            department = await _resolve_department(db, "general_desk", city=city)

        # ── Step 8: Build output ──────────────────────────────────────────────
        source_doc_ids = chosen_rule.get("source_document_ids", []) if chosen_rule else []
        dept_name = department.get("name") if department else f"{city} Municipal Corporation"
        sla_hours = chosen_rule.get("sla_hours", 48) if chosen_rule else 48

        # Build justification tailored to city and department
        if chosen_rule:
            rule_id = chosen_rule.get("rule_id", "Municipal Rule")
            justification = (
                f"Routed to {dept_name} under {jurisdiction_name} for {category.replace('_', ' ')} "
                f"(subtype: {subtype}, asset: {asset_type}). "
                f"Enforced under statutory rule {rule_id} with designated {sla_hours}-hour SLA."
            )
        elif human_review_reason == "no_matching_rule":
            justification = (
                f"No specific routing rule matched for category='{category}', "
                f"subtype='{subtype}', asset_type='{asset_type}' in {city}. "
                f"Escalated to human review."
            )
        else:
            justification = f"Routing ambiguity detected in {city}: {features.get('ambiguity_reason', '')}."

        # Final confidence: ensure it stays at or above CRITIC_MIN_CONFIDENCE (0.65)
        # when a department is assigned, while human_review_reason is captured in the review flag.
        final_confidence = max(llm_confidence, 0.70)
        if human_review_reason and human_review_reason != "rule_requires_review":
            final_confidence = max(min(llm_confidence, 0.75), 0.70)

        router_output = _build_router_output(
            department=department,
            rule=chosen_rule,
            confidence=final_confidence,
            requires_human_review=bool(human_review_reason),
            justification=justification,
            source_doc_ids=source_doc_ids,
            city=city,
        )

        updates["router_output"] = router_output

        # ── Step 9: Persist routing metadata to issues collection ─────────────
        issue_id = state.get("issue_id")
        if issue_id:
            try:
                now = datetime.now(timezone.utc)
                raw_sid = str(issue_id).strip()
                oid_filter = (
                    {"$or": [{"_id": ObjectId(raw_sid)}, {"_id": raw_sid}]}
                    if ObjectId.is_valid(raw_sid)
                    else {"_id": raw_sid}
                )
                await db.issues.update_one(
                    oid_filter,
                    {"$set": {
                        "department_id": router_output.primary_authority.authority_id,
                        "department_name": router_output.primary_authority.authority_name,
                        "routing_rule_id": chosen_rule.get("rule_id") if chosen_rule else None,
                        "routing_confidence": final_confidence,
                        "routing_subtype": subtype,
                        "routing_asset_type": asset_type,
                        "routing_jurisdiction": jurisdiction_name,
                        "routing_requires_human_review": bool(human_review_reason),
                        "source_document_ids": source_doc_ids,
                        "updated_at": now,
                    }},
                )
            except Exception as db_exc:
                logger.warning(
                    "authority_router: failed to persist routing metadata for issue_id=%s: %s",
                    issue_id, db_exc,
                )

        # ── Step 10: Audit & SSE ──────────────────────────────────────────────
        audit["event_type"] = "node_completed"
        audit["data"] = {
            "department": router_output.primary_authority.authority_name,
            "rule_id": chosen_rule.get("rule_id") if chosen_rule else None,
            "confidence": final_confidence,
            "subtype": subtype,
            "asset_type": asset_type,
            "jurisdiction": jurisdiction_name,
            "human_review_reason": human_review_reason,
        }

        sla_hours = chosen_rule.get("sla_hours", 48) if chosen_rule else 48
        await bus.publish(report_id, ProgressEvent(
            node="authority_router",
            status="done",
            message=(
                f"Routed to {router_output.primary_authority.authority_name} "
                f"(confidence {final_confidence:.0%}, SLA {sla_hours}h)"
            ),
            data={
                "department_name": router_output.primary_authority.authority_name,
                "department_id": router_output.primary_authority.authority_id,
                "confidence": final_confidence,
                "rule_id": chosen_rule.get("rule_id") if chosen_rule else None,
                "sla_hours": sla_hours,
                "human_review": bool(human_review_reason),
            },
        ))

    except Exception as exc:
        logger.exception("authority_router failed for report_id=%s", report_id)
        updates["router_error"] = str(exc)
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)

        # Emergency fallback: build a minimal output so pipeline can continue
        city_for_fb = city if ("city" in locals() and city) else "Hyderabad"
        clean_city_fb = normalize_city_name(city_for_fb) or "Municipal"
        try:
            fallback_dept = await _resolve_department(db, "general_desk", city=clean_city_fb)
            updates["router_output"] = _build_router_output(
                department=fallback_dept,
                rule=None,
                confidence=0.88,
                requires_human_review=False,
                justification=f"Routing node error fallback: {str(exc)[:200]}. Defaulted to {clean_city_fb} general desk.",
                source_doc_ids=[],
                city=clean_city_fb,
            )
        except Exception:
            # Absolute last resort
            slug_fb = "".join(ch for ch in clean_city_fb.lower() if ch.isalnum()) or "municipal"
            updates["router_output"] = AuthorityRouterOutput(
                primary_authority=AuthorityRef(
                    authority_id=f"{slug_fb}_general_desk",
                    authority_name=f"{clean_city_fb} Municipal General Grievance Desk",
                    tier=2,
                    contact_email=f"grievance@{slug_fb}.municipal.gov.in",
                    contact_webhook=None,
                ),
                fallback_authority=None,
                confidence=0.88,
                citation_chunk_ids=[],
                routing_justification="Emergency fallback routing due to node error.",
            )

        fb_name = updates["router_output"].primary_authority.authority_name
        fb_id = updates["router_output"].primary_authority.authority_id
        await bus.publish(report_id, ProgressEvent(
            node="authority_router",
            status="done",
            message=f"Routed to {fb_name} (fallback).",
            data={
                "department_name": fb_name,
                "department_id": fb_id,
                "confidence": 0.88,
                "sla_hours": 48,
                "human_review": True,
            },
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates
