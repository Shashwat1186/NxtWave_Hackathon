"""
seed/seed_rules.py
==================
Seeds the Rule-Based Routing Engine collections into MongoDB.

Collections created/seeded:
  - departments           (replaces authorities for routing)
  - routing_rules         (15–25 deterministic routing rules with precedence)
  - jurisdictions         (GeoJSON ward/zone boundaries for $geoIntersects)
  - reporting_destinations (officer inboxes, email, webhook endpoints)
  - source_documents      (provenance/evidence URLs backing each rule)

Usage:
    cd civictriage/backend
    python -m seed.seed_rules
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_rules")

_NOW = datetime.now(timezone.utc)

# ═══════════════════════════════════════════════════════════════════════════════
# DEPARTMENTS
# ═══════════════════════════════════════════════════════════════════════════════

DEPARTMENTS = [
    {
        "department_id": "roads_dept",
        "name": "Roads & Buildings Department (GHMC / Municipal Corporation)",
        "short_name": "Roads & Buildings",
        "tier": 1,
        "categories": ["road_damage", "encroachment"],
        "contact_email": "roads@municipal.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 48,
        "is_active": True,
        "description": (
            "Responsible for municipal road maintenance, pothole repairs, "
            "road-cutting permissions, and encroachment removals within GHMC limits."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "nhai_dept",
        "name": "National Highways Authority of India (NHAI)",
        "short_name": "NHAI",
        "tier": 1,
        "categories": ["road_damage"],
        "contact_email": "helpdesk@nhai.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 72,
        "is_active": True,
        "description": (
            "Manages national highways (NH) and expressways. Responsible for "
            "road damage on NH-65, NH-163 and other national highways through urban areas."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "water_dept",
        "name": "Hyderabad Metropolitan Water Supply & Sewerage Board (HMWSSB)",
        "short_name": "Water & Sewerage Board",
        "tier": 1,
        "categories": ["water_leak", "sewage"],
        "contact_email": "complaints@hmwssb.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 24,
        "is_active": True,
        "description": (
            "Responsible for water supply, pipeline maintenance, sewage treatment, "
            "and sewerage network across Hyderabad Metropolitan area."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "sanitation_dept",
        "name": "Sanitation & Solid Waste Management Department (GHMC)",
        "short_name": "Sanitation & SWM",
        "tier": 1,
        "categories": ["garbage", "pollution"],
        "contact_email": "swm@ghmc.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 24,
        "is_active": True,
        "description": (
            "Door-to-door garbage collection, bulk waste removal, sweeping, "
            "and solid waste management across all GHMC zones."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "electricity_dept",
        "name": "TS Southern Power Distribution Company (TSSPDCL)",
        "short_name": "TSSPDCL / Streetlights",
        "tier": 1,
        "categories": ["streetlight"],
        "contact_email": "helpdesk@tsspdcl.co.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 24,
        "is_active": True,
        "description": (
            "Manages electricity distribution and street lighting infrastructure "
            "across southern Telangana including Hyderabad."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "horticulture_dept",
        "name": "Horticulture & Tree Authority (GHMC)",
        "short_name": "Horticulture & Trees",
        "tier": 1,
        "categories": ["tree_hazard"],
        "contact_email": "horticulture@ghmc.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 12,
        "is_active": True,
        "description": (
            "Manages urban forestry, tree trimming, fallen tree removal, "
            "and hazardous tree assessments in GHMC jurisdiction."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "pollution_board",
        "name": "Telangana State Pollution Control Board (TSPCB)",
        "short_name": "Pollution Control Board",
        "tier": 1,
        "categories": ["pollution"],
        "contact_email": "complaints@tspcb.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 48,
        "is_active": True,
        "description": (
            "Regulates air, water, and soil pollution. Handles industrial effluent "
            "complaints, noise pollution, and environmental violations."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "disaster_mgmt",
        "name": "District Disaster Management Authority (DDMA) / Revenue Department",
        "short_name": "Disaster Management",
        "tier": 1,
        "categories": ["flood"],
        "contact_email": "ddma@telangana.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 6,
        "is_active": True,
        "description": (
            "Coordinates flood relief, waterlogging response, and disaster management "
            "operations across Hyderabad district."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "collector_office",
        "name": "District Collector's Office & DDMA (Hyderabad)",
        "short_name": "Collector's Office",
        "tier": 2,
        "categories": [
            "road_damage", "water_leak", "sewage", "garbage",
            "streetlight", "pollution", "encroachment", "tree_hazard", "flood", "other",
        ],
        "contact_email": "collector.hyd@telangana.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": None,
        "sla_hours_default": 96,
        "is_active": True,
        "description": (
            "District-level escalation authority. Handles complaints beyond tier-1 "
            "jurisdiction or inter-departmental disputes."
        ),
        "created_at": _NOW,
    },
    {
        "department_id": "general_desk",
        "name": "Municipal General Grievance Desk",
        "short_name": "General Desk",
        "tier": 2,
        "categories": ["other"],
        "contact_email": "grievance@ghmc.gov.in",
        "contact_webhook": None,
        "escalation_parent_id": "collector_office",
        "sla_hours_default": 72,
        "is_active": True,
        "description": (
            "Catch-all desk for civic grievances that do not match a specific department. "
            "Routes internally after manual triage."
        ),
        "created_at": _NOW,
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE DOCUMENTS (provenance/evidence for rules)
# ═══════════════════════════════════════════════════════════════════════════════

SOURCE_DOCUMENTS = [
    {
        "doc_id": "ghmc_roads_charter",
        "title": "GHMC Engineering Charter — Roads & Buildings",
        "section": "Section 4(a): Pothole Repair SLA",
        "url": "https://www.ghmc.gov.in/roads-charter",
        "authority": "roads_dept",
        "description": "GHMC engineering standards mandating 48-hour pothole repair SLA for municipal roads.",
        "created_at": _NOW,
    },
    {
        "doc_id": "motor_vehicles_act_198a",
        "title": "Motor Vehicles (Amendment) Act 2019 — Section 198A",
        "section": "§ 198A: Liability for road accidents due to negligence",
        "url": "https://indiacode.nic.in/handle/123456789/13233",
        "authority": "roads_dept",
        "description": "Strict statutory liability on municipal authority and highway contractors for dangerous road surfaces.",
        "created_at": _NOW,
    },
    {
        "doc_id": "nhai_road_safety_manual",
        "title": "NHAI Road Safety Manual — Section 6: Road Defect Reporting",
        "section": "Section 6.3: Emergency Repair Protocol",
        "url": "https://nhai.gov.in/road-safety-manual",
        "authority": "nhai_dept",
        "description": "NHAI protocol for emergency pothole and road defect repair on national highways.",
        "created_at": _NOW,
    },
    {
        "doc_id": "hmwssb_service_charter",
        "title": "HMWSSB Citizen Service Charter",
        "section": "Section 3: Complaint Redressal — Water Leak & Sewage",
        "url": "https://www.hmwssb.gov.in/service-charter",
        "authority": "water_dept",
        "description": "HMWSSB charter mandating 24-hour response for water main breaks and 48-hour for sewage blockages.",
        "created_at": _NOW,
    },
    {
        "doc_id": "ghmc_swm_bylaws",
        "title": "GHMC Solid Waste Management Bye-Laws 2016",
        "section": "Bye-Law 12: Bulk Garbage Complaint Redressal",
        "url": "https://ghmc.gov.in/swm-byelaws-2016",
        "authority": "sanitation_dept",
        "description": "Mandates 24-hour response for bulk garbage complaints and weekly sweeping schedules.",
        "created_at": _NOW,
    },
    {
        "doc_id": "tsspdcl_streetlight_charter",
        "title": "TSSPDCL Streetlight Maintenance Charter",
        "section": "Section 2: Fault Reporting & Repair SLA",
        "url": "https://tsspdcl.co.in/streetlight-charter",
        "authority": "electricity_dept",
        "description": "TSSPDCL mandates 24-hour repair for reported streetlight outages.",
        "created_at": _NOW,
    },
    {
        "doc_id": "ghmc_tree_authority_order",
        "title": "GHMC Tree Authority — Emergency Tree Hazard Protocol",
        "section": "Order No. HRT/2019/04: Fallen Tree Emergency Response",
        "url": "https://ghmc.gov.in/tree-authority-orders",
        "authority": "horticulture_dept",
        "description": "GHMC protocol for emergency response to fallen or hazardous trees — 12-hour SLA.",
        "created_at": _NOW,
    },
    {
        "doc_id": "tspcb_pollution_act",
        "title": "Environment Protection Act 1986 & Air/Water Pollution Acts",
        "section": "Rule 5: Complaint Registration and Response",
        "url": "https://tspcb.cgg.gov.in/complaint-rules",
        "authority": "pollution_board",
        "description": "TSPCB mandated complaint response under Environment Protection Act, Air Act 1981, Water Act 1974.",
        "created_at": _NOW,
    },
    {
        "doc_id": "telangana_sdma_act",
        "title": "Telangana State Disaster Management Act 2005",
        "section": "Section 34: Local Authority Flood Response Obligations",
        "url": "https://www.telangana.gov.in/sdma-act-2005",
        "authority": "disaster_mgmt",
        "description": "SDMA mandates immediate flood response and waterlogging mitigation by municipal authorities.",
        "created_at": _NOW,
    },
    {
        "doc_id": "74th_constitutional_amendment",
        "title": "74th Constitutional Amendment — 12th Schedule",
        "section": "Items 3 & 4: Roads and Bridges; Water Supply",
        "url": "https://indiacode.nic.in/constitution-74th-amendment",
        "authority": "roads_dept",
        "description": "Constitutional mandate placing roads, water supply, and urban services under Urban Local Bodies.",
        "created_at": _NOW,
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTING RULES (25 deterministic rules with explicit precedence)
# Priority: lower number = higher precedence
# ═══════════════════════════════════════════════════════════════════════════════

ROUTING_RULES = [
    # ── ROAD DAMAGE ──────────────────────────────────────────────────────────
    {
        "rule_id": "rule_001",
        "name": "Municipal Road — Pothole",
        "category": "road_damage",
        "subtype": "pothole",
        "asset_type": "municipal_road",
        "department_id": "roads_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 48,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_roads_charter", "motor_vehicles_act_198a"],
        "routing_justification": (
            "Potholes on GHMC municipal roads fall under Roads & Buildings Department "
            "per GHMC Engineering Charter Section 4(a). 48-hour SLA mandated."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_002",
        "name": "National Highway — Road Damage",
        "category": "road_damage",
        "subtype": "pothole",
        "asset_type": "national_highway",
        "department_id": "nhai_dept",
        "jurisdiction_type": "national",
        "priority": 5,
        "sla_hours": 72,
        "requires_human_review": False,
        "source_document_ids": ["nhai_road_safety_manual", "motor_vehicles_act_198a"],
        "routing_justification": (
            "Potholes on National Highways (NH) are under NHAI jurisdiction per "
            "NHAI Road Safety Manual Section 6.3. 72-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_003",
        "name": "Road Collapse / Sinkhole — Emergency",
        "category": "road_damage",
        "subtype": "road_collapse",
        "asset_type": "any",
        "department_id": "roads_dept",
        "jurisdiction_type": "municipal",
        "priority": 3,
        "sla_hours": 6,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_roads_charter", "motor_vehicles_act_198a"],
        "routing_justification": (
            "Road collapse/sinkhole is a public safety emergency requiring immediate barricading. "
            "Routed to Roads & Buildings for emergency response within 6 hours."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_004",
        "name": "State Highway — Road Damage",
        "category": "road_damage",
        "subtype": "pothole",
        "asset_type": "state_highway",
        "department_id": "roads_dept",
        "jurisdiction_type": "state",
        "priority": 8,
        "sla_hours": 72,
        "requires_human_review": False,
        "source_document_ids": ["motor_vehicles_act_198a", "74th_constitutional_amendment"],
        "routing_justification": (
            "State highways within municipal limits fall under State PWD / GHMC Roads jurisdiction "
            "per 74th Constitutional Amendment (12th Schedule, Item 3)."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_005",
        "name": "Road Damage — Construction Zone",
        "category": "road_damage",
        "subtype": "construction_damage",
        "asset_type": "construction_zone",
        "department_id": "roads_dept",
        "jurisdiction_type": "municipal",
        "priority": 12,
        "sla_hours": 48,
        "requires_human_review": True,
        "source_document_ids": ["ghmc_roads_charter", "motor_vehicles_act_198a"],
        "routing_justification": (
            "Construction zone road damage may involve contractor liability. "
            "Routed to Roads & Buildings with human review to identify the responsible contractor."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_006",
        "name": "Road Damage — Unknown Road Type",
        "category": "road_damage",
        "subtype": "any",
        "asset_type": "unknown",
        "department_id": "roads_dept",
        "jurisdiction_type": "any",
        "priority": 20,
        "sla_hours": 48,
        "requires_human_review": True,
        "source_document_ids": ["ghmc_roads_charter"],
        "routing_justification": (
            "Road damage on unknown/unverified road type. Routed to Roads & Buildings "
            "for asset ownership verification before repair dispatch."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── WATER LEAK ───────────────────────────────────────────────────────────
    {
        "rule_id": "rule_007",
        "name": "Water Main Break — Emergency",
        "category": "water_leak",
        "subtype": "main_break",
        "asset_type": "water_main",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 5,
        "sla_hours": 12,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter", "74th_constitutional_amendment"],
        "routing_justification": (
            "Water main breaks are a public safety emergency. HMWSSB handles all water "
            "supply infrastructure per Service Charter Section 3. 12-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_008",
        "name": "Water Contamination — Emergency",
        "category": "water_leak",
        "subtype": "contamination",
        "asset_type": "water_pipeline",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 3,
        "sla_hours": 6,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter", "tspcb_pollution_act"],
        "routing_justification": (
            "Water contamination is a public health emergency. HMWSSB handles with "
            "TSPCB oversight. Immediate 6-hour response required."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_009",
        "name": "General Pipeline Leak",
        "category": "water_leak",
        "subtype": "pipeline_leak",
        "asset_type": "water_pipeline",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter"],
        "routing_justification": (
            "Pipeline leaks in HMWSSB network handled by Water & Sewerage Board "
            "per Citizen Service Charter. 24-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── SEWAGE ───────────────────────────────────────────────────────────────
    {
        "rule_id": "rule_010",
        "name": "Sewage Overflow — Emergency",
        "category": "sewage",
        "subtype": "overflow",
        "asset_type": "sewer_main",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 5,
        "sla_hours": 12,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter"],
        "routing_justification": (
            "Sewage overflow is a public health emergency. HMWSSB handles sewerage network "
            "per Service Charter. 12-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_011",
        "name": "Manhole Blockage / Sewage Backup",
        "category": "sewage",
        "subtype": "blockage",
        "asset_type": "manhole",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter"],
        "routing_justification": (
            "Manhole blockages are HMWSSB responsibility for sewerage network maintenance. "
            "24-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── GARBAGE ──────────────────────────────────────────────────────────────
    {
        "rule_id": "rule_012",
        "name": "Bulk Garbage / Illegal Dumping",
        "category": "garbage",
        "subtype": "bulk_dumping",
        "asset_type": "public_land",
        "department_id": "sanitation_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_swm_bylaws"],
        "routing_justification": (
            "Illegal bulk dumping on public land handled by GHMC SWM Department "
            "per Solid Waste Management Bye-Laws 2016, Bye-Law 12."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_013",
        "name": "Missed Garbage Collection",
        "category": "garbage",
        "subtype": "missed_collection",
        "asset_type": "residential_zone",
        "department_id": "sanitation_dept",
        "jurisdiction_type": "municipal",
        "priority": 15,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_swm_bylaws"],
        "routing_justification": (
            "Missed door-to-door garbage collection is GHMC Sanitation's responsibility "
            "per SWM Bye-Laws 2016. 24-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_014",
        "name": "Construction Debris Dumping",
        "category": "garbage",
        "subtype": "construction_debris",
        "asset_type": "public_road",
        "department_id": "sanitation_dept",
        "jurisdiction_type": "municipal",
        "priority": 12,
        "sla_hours": 48,
        "requires_human_review": True,
        "source_document_ids": ["ghmc_swm_bylaws"],
        "routing_justification": (
            "Construction debris dumping on public roads — GHMC SWM handles removal, "
            "human review required to identify liable contractor."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── STREETLIGHT ──────────────────────────────────────────────────────────
    {
        "rule_id": "rule_015",
        "name": "Streetlight Outage",
        "category": "streetlight",
        "subtype": "outage",
        "asset_type": "public_streetlight",
        "department_id": "electricity_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["tsspdcl_streetlight_charter"],
        "routing_justification": (
            "Streetlight outages handled by TSSPDCL per Streetlight Maintenance Charter "
            "Section 2. 24-hour repair SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_016",
        "name": "Damaged Streetlight Pole — Safety Hazard",
        "category": "streetlight",
        "subtype": "damaged_pole",
        "asset_type": "public_streetlight",
        "department_id": "electricity_dept",
        "jurisdiction_type": "municipal",
        "priority": 5,
        "sla_hours": 12,
        "requires_human_review": False,
        "source_document_ids": ["tsspdcl_streetlight_charter"],
        "routing_justification": (
            "Damaged streetlight poles are an immediate safety hazard. "
            "TSSPDCL emergency repair required within 12 hours."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── TREE HAZARD ──────────────────────────────────────────────────────────
    {
        "rule_id": "rule_017",
        "name": "Fallen Tree Blocking Road — Emergency",
        "category": "tree_hazard",
        "subtype": "fallen_tree",
        "asset_type": "public_road",
        "department_id": "horticulture_dept",
        "jurisdiction_type": "municipal",
        "priority": 3,
        "sla_hours": 6,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_tree_authority_order"],
        "routing_justification": (
            "Fallen trees blocking roads are a public safety emergency. "
            "GHMC Tree Authority handles per Emergency Protocol Order HRT/2019/04. 6-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_018",
        "name": "Hazardous Overhanging Tree Branch",
        "category": "tree_hazard",
        "subtype": "overgrown_branch",
        "asset_type": "public_tree",
        "department_id": "horticulture_dept",
        "jurisdiction_type": "municipal",
        "priority": 15,
        "sla_hours": 48,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_tree_authority_order"],
        "routing_justification": (
            "Overgrown or hazardous tree branches on public property are GHMC "
            "Horticulture responsibility. 48-hour SLA."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── POLLUTION ────────────────────────────────────────────────────────────
    {
        "rule_id": "rule_019",
        "name": "Industrial Pollution — Air/Water Discharge",
        "category": "pollution",
        "subtype": "industrial_discharge",
        "asset_type": "industrial_zone",
        "department_id": "pollution_board",
        "jurisdiction_type": "any",
        "priority": 5,
        "sla_hours": 48,
        "requires_human_review": False,
        "source_document_ids": ["tspcb_pollution_act"],
        "routing_justification": (
            "Industrial pollution complaints regulated by TSPCB under Environment "
            "Protection Act 1986, Air Act 1981, and Water Act 1974."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_020",
        "name": "Open Waste Burning / Air Pollution",
        "category": "pollution",
        "subtype": "open_burning",
        "asset_type": "any",
        "department_id": "sanitation_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 24,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_swm_bylaws", "tspcb_pollution_act"],
        "routing_justification": (
            "Open burning of waste is primarily a GHMC SWM violation with TSPCB oversight. "
            "GHMC Sanitation enforces and files TSPCB complaint if required."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── FLOOD ────────────────────────────────────────────────────────────────
    {
        "rule_id": "rule_021",
        "name": "Flooding / Waterlogging — Emergency",
        "category": "flood",
        "subtype": "waterlogging",
        "asset_type": "any",
        "department_id": "disaster_mgmt",
        "jurisdiction_type": "any",
        "priority": 2,
        "sla_hours": 6,
        "requires_human_review": False,
        "source_document_ids": ["telangana_sdma_act"],
        "routing_justification": (
            "Flooding and waterlogging are disaster events handled by DDMA per "
            "Telangana SDMA Act 2005, Section 34. 6-hour emergency response."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_022",
        "name": "Blocked Storm Drain — Flood Risk",
        "category": "flood",
        "subtype": "blocked_drain",
        "asset_type": "storm_drain",
        "department_id": "water_dept",
        "jurisdiction_type": "municipal",
        "priority": 8,
        "sla_hours": 12,
        "requires_human_review": False,
        "source_document_ids": ["hmwssb_service_charter", "telangana_sdma_act"],
        "routing_justification": (
            "Blocked storm drains causing flood risk handled by HMWSSB drainage division. "
            "12-hour SLA to prevent escalation."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── ENCROACHMENT ─────────────────────────────────────────────────────────
    {
        "rule_id": "rule_023",
        "name": "Footpath / Public Space Encroachment",
        "category": "encroachment",
        "subtype": "footpath_encroachment",
        "asset_type": "public_footpath",
        "department_id": "roads_dept",
        "jurisdiction_type": "municipal",
        "priority": 15,
        "sla_hours": 72,
        "requires_human_review": False,
        "source_document_ids": ["ghmc_roads_charter", "74th_constitutional_amendment"],
        "routing_justification": (
            "Footpath encroachments fall under Roads & Buildings Department enforcement "
            "per GHMC charter and 74th Constitutional Amendment."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "rule_id": "rule_024",
        "name": "Illegal Construction / Building Encroachment",
        "category": "encroachment",
        "subtype": "illegal_construction",
        "asset_type": "public_land",
        "department_id": "roads_dept",
        "jurisdiction_type": "municipal",
        "priority": 10,
        "sla_hours": 48,
        "requires_human_review": True,
        "source_document_ids": ["74th_constitutional_amendment"],
        "routing_justification": (
            "Illegal construction requires enforcement officer verification. "
            "Routed to Roads & Buildings with human review flag for physical inspection."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
    # ── OTHER / CATCH-ALL ────────────────────────────────────────────────────
    {
        "rule_id": "rule_025",
        "name": "General Civic Complaint — Catch-All",
        "category": "other",
        "subtype": "any",
        "asset_type": "any",
        "department_id": "general_desk",
        "jurisdiction_type": "any",
        "priority": 100,
        "sla_hours": 72,
        "requires_human_review": True,
        "source_document_ids": [],
        "routing_justification": (
            "Unclassified civic complaints routed to Municipal General Grievance Desk "
            "for manual categorization and departmental dispatch."
        ),
        "is_active": True,
        "created_at": _NOW,
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# JURISDICTIONS (simplified GeoJSON for Hyderabad — demo data)
# ═══════════════════════════════════════════════════════════════════════════════

JURISDICTIONS = [
    {
        "jurisdiction_id": "hyd_zone_lb_nagar",
        "name": "LB Nagar Zone",
        "zone_type": "zone",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.5300, 17.3200], [78.6000, 17.3200],
                [78.6000, 17.3800], [78.5300, 17.3800],
                [78.5300, 17.3200],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "jurisdiction_id": "hyd_zone_serilingampally",
        "name": "Serilingampally Zone",
        "zone_type": "zone",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.2900, 17.4200], [78.4200, 17.4200],
                [78.4200, 17.5100], [78.2900, 17.5100],
                [78.2900, 17.4200],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "jurisdiction_id": "hyd_zone_kukatpally",
        "name": "Kukatpally Zone",
        "zone_type": "zone",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.3900, 17.4600], [78.5000, 17.4600],
                [78.5000, 17.5400], [78.3900, 17.5400],
                [78.3900, 17.4600],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "jurisdiction_id": "hyd_zone_secunderabad",
        "name": "Secunderabad Zone",
        "zone_type": "zone",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.4700, 17.4300], [78.5800, 17.4300],
                [78.5800, 17.5100], [78.4700, 17.5100],
                [78.4700, 17.4300],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "jurisdiction_id": "hyd_zone_charminar",
        "name": "Charminar Zone",
        "zone_type": "zone",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.4600, 17.3400], [78.5200, 17.3400],
                [78.5200, 17.4100], [78.4600, 17.4100],
                [78.4600, 17.3400],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "jurisdiction_id": "hyd_default",
        "name": "Hyderabad District (Default Catch-All)",
        "zone_type": "district",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "administrative_body": "GHMC",
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [78.2500, 17.2000], [78.7000, 17.2000],
                [78.7000, 17.6000], [78.2500, 17.6000],
                [78.2500, 17.2000],
            ]],
        },
        "is_active": True,
        "created_at": _NOW,
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# REPORTING DESTINATIONS
# ═══════════════════════════════════════════════════════════════════════════════

REPORTING_DESTINATIONS = [
    {
        "destination_id": "dest_roads_ward_engineer",
        "name": "Ward Engineer Inbox — Roads & Buildings",
        "department_id": "roads_dept",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "ward.engineer@ghmc.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_nhai_helpdesk",
        "name": "NHAI Helpdesk — Hyderabad RO",
        "department_id": "nhai_dept",
        "type": "email",
        "endpoint": None,
        "contact_email": "ro-hyd@nhai.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_hmwssb_control_room",
        "name": "HMWSSB 24×7 Control Room",
        "department_id": "water_dept",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "controlroom@hmwssb.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_swm_zone_supervisor",
        "name": "SWM Zone Supervisor Inbox",
        "department_id": "sanitation_dept",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "swm.zone@ghmc.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_tsspdcl_streetlight",
        "name": "TSSPDCL Streetlight Control Center",
        "department_id": "electricity_dept",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "streetlight.control@tsspdcl.co.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_horticulture_tree",
        "name": "GHMC Tree Authority — Emergency Line",
        "department_id": "horticulture_dept",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "tree.emergency@ghmc.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_tspcb_complaint",
        "name": "TSPCB Online Complaint System",
        "department_id": "pollution_board",
        "type": "webhook",
        "endpoint": "https://tspcb.cgg.gov.in/api/complaints",
        "contact_email": "complaints@tspcb.gov.in",
        "contact_webhook": "https://tspcb.cgg.gov.in/api/complaints",
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_ddma_control",
        "name": "DDMA Emergency Operations Center",
        "department_id": "disaster_mgmt",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "eoc@ddma.telangana.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_general_grievance",
        "name": "Municipal General Grievance Cell",
        "department_id": "general_desk",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "grievance@ghmc.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
    {
        "destination_id": "dest_collector_escalation",
        "name": "District Collector Escalation Portal",
        "department_id": "collector_office",
        "type": "internal",
        "endpoint": "officer_portal",
        "contact_email": "collector.hyd@telangana.gov.in",
        "contact_webhook": None,
        "is_active": True,
        "created_at": _NOW,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SEEDING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def seed_departments(db) -> int:
    count = 0
    for dept in DEPARTMENTS:
        await db.departments.update_one(
            {"department_id": dept["department_id"]},
            {"$set": dept},
            upsert=True,
        )
        count += 1
    return count


async def seed_routing_rules(db) -> int:
    count = 0
    for rule in ROUTING_RULES:
        await db.routing_rules.update_one(
            {"rule_id": rule["rule_id"]},
            {"$set": rule},
            upsert=True,
        )
        count += 1
    return count


async def seed_jurisdictions(db) -> int:
    count = 0
    for jur in JURISDICTIONS:
        await db.jurisdictions.update_one(
            {"jurisdiction_id": jur["jurisdiction_id"]},
            {"$set": jur},
            upsert=True,
        )
        count += 1
    return count


async def seed_source_documents(db) -> int:
    count = 0
    for doc in SOURCE_DOCUMENTS:
        await db.source_documents.update_one(
            {"doc_id": doc["doc_id"]},
            {"$set": doc},
            upsert=True,
        )
        count += 1
    return count


async def seed_reporting_destinations(db) -> int:
    count = 0
    for dest in REPORTING_DESTINATIONS:
        await db.reporting_destinations.update_one(
            {"destination_id": dest["destination_id"]},
            {"$set": dest},
            upsert=True,
        )
        count += 1
    return count


async def run_seed():
    from app.core.database import connect_db, get_db
    await connect_db()
    db = await get_db()

    logger.info("═" * 60)
    logger.info("CivicTriage — Rule-Based Routing Engine Seeder")
    logger.info("═" * 60)

    n = await seed_departments(db)
    logger.info("✓ Seeded %d departments", n)

    n = await seed_routing_rules(db)
    logger.info("✓ Seeded %d routing rules", n)

    n = await seed_jurisdictions(db)
    logger.info("✓ Seeded %d jurisdictions (GeoJSON)", n)

    n = await seed_source_documents(db)
    logger.info("✓ Seeded %d source documents", n)

    n = await seed_reporting_destinations(db)
    logger.info("✓ Seeded %d reporting destinations", n)

    logger.info("═" * 60)
    logger.info("Seed complete.")


if __name__ == "__main__":
    asyncio.run(run_seed())

