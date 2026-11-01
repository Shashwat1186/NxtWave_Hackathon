"""
services/city_directory.py
===========================
Comprehensive Pan-India municipal authority and jurisdiction directory.

Provides:
- Coordinate-based Indian city detection (Bengaluru, Mumbai, Delhi, Chennai, Kolkata, Pune, Hyderabad, etc.)
- Normalization of city names across spellings and metropolitan districts
- Accurate departmental resolution (BBMP, BWSSB, BESCOM, BMC, MCD, DJB, GCC, KMC, PMC, GHMC, etc.)
- Dynamic municipal department generator for all 4,500+ Indian Urban Local Bodies
"""

from __future__ import annotations

import re
from typing import Any, Optional

# ── City Coordinate Bounding Boxes & Defaults ─────────────────────────────────

_INDIAN_CITY_REGIONS = [
    {
        "city": "Bengaluru",
        "state": "Karnataka",
        "min_lat": 12.70,
        "max_lat": 13.25,
        "min_lng": 77.40,
        "max_lng": 77.85,
        "default_address": "Mahatma Gandhi Road, Bengaluru, Karnataka, India",
        "default_ward": "East Zone / Ward 112",
        "admin_body": "Bruhat Bengaluru Mahanagara Palike (BBMP)",
    },
    {
        "city": "Mumbai",
        "state": "Maharashtra",
        "min_lat": 18.85,
        "max_lat": 19.35,
        "min_lng": 72.75,
        "max_lng": 73.15,
        "default_address": "Swami Vivekananda Road, Bandra West, Mumbai, Maharashtra, India",
        "default_ward": "H/West Ward",
        "admin_body": "Brihanmumbai Municipal Corporation (BMC / MCGM)",
    },
    {
        "city": "Delhi",
        "state": "Delhi",
        "min_lat": 28.35,
        "max_lat": 28.95,
        "min_lng": 76.80,
        "max_lng": 77.45,
        "default_address": "Connaught Place, Central Delhi, New Delhi, Delhi, India",
        "default_ward": "Ward 74 / Central",
        "admin_body": "Municipal Corporation of Delhi (MCD)",
    },
    {
        "city": "Chennai",
        "state": "Tamil Nadu",
        "min_lat": 12.85,
        "max_lat": 13.30,
        "min_lng": 80.05,
        "max_lng": 80.38,
        "default_address": "Anna Salai, Mount Road, Chennai, Tamil Nadu, India",
        "default_ward": "Zone 9 / T. Nagar",
        "admin_body": "Greater Chennai Corporation (GCC)",
    },
    {
        "city": "Kolkata",
        "state": "West Bengal",
        "min_lat": 22.35,
        "max_lat": 22.75,
        "min_lng": 88.20,
        "max_lng": 88.50,
        "default_address": "Park Street, Central Kolkata, West Bengal, India",
        "default_ward": "Borough VII / Ward 63",
        "admin_body": "Kolkata Municipal Corporation (KMC)",
    },
    {
        "city": "Pune",
        "state": "Maharashtra",
        "min_lat": 18.35,
        "max_lat": 18.70,
        "min_lng": 73.65,
        "max_lng": 74.05,
        "default_address": "Fergusson College Road, Shivajinagar, Pune, Maharashtra, India",
        "default_ward": "Prabhag 14 / Shivajinagar",
        "admin_body": "Pune Municipal Corporation (PMC)",
    },
    {
        "city": "Hyderabad",
        "state": "Telangana",
        "min_lat": 17.15,
        "max_lat": 17.65,
        "min_lng": 78.20,
        "max_lng": 78.70,
        "default_address": "Road No 36, Jubilee Hills, Hyderabad, Telangana, India",
        "default_ward": "Jubilee Hills Ward 94",
        "admin_body": "Greater Hyderabad Municipal Corporation (GHMC)",
    },
    {
        "city": "Ahmedabad",
        "state": "Gujarat",
        "min_lat": 22.90,
        "max_lat": 23.20,
        "min_lng": 72.45,
        "max_lng": 72.75,
        "default_address": "Ashram Road, Ahmedabad, Gujarat, India",
        "default_ward": "Navrangpura Ward",
        "admin_body": "Amdavad Municipal Corporation (AMC)",
    },
    {
        "city": "Jaipur",
        "state": "Rajasthan",
        "min_lat": 26.75,
        "max_lat": 27.10,
        "min_lng": 75.70,
        "max_lng": 76.00,
        "default_address": "MI Road, Pink City, Jaipur, Rajasthan, India",
        "default_ward": "Hawa Mahal Ward",
        "admin_body": "Jaipur Nagar Nigam",
    },
    {
        "city": "Lucknow",
        "state": "Uttar Pradesh",
        "min_lat": 26.70,
        "max_lat": 27.00,
        "min_lng": 80.80,
        "max_lng": 81.10,
        "default_address": "Hazratganj, Lucknow, Uttar Pradesh, India",
        "default_ward": "Hazratganj Ward",
        "admin_body": "Lucknow Municipal Corporation (LMC)",
    },
    {
        "city": "Chandigarh",
        "state": "Chandigarh",
        "min_lat": 30.65,
        "max_lat": 30.85,
        "min_lng": 76.70,
        "max_lng": 76.88,
        "default_address": "Sector 17 Plaza, Chandigarh, India",
        "default_ward": "Sector 17",
        "admin_body": "Municipal Corporation Chandigarh (MCC)",
    },
]


def normalize_city_name(city: Optional[str]) -> str:
    """Normalize city names from Nominatim, GPS, or citizen input."""
    if not city:
        return ""
    c = city.lower().strip()
    if any(k in c for k in ("bengaluru", "bangalore")):
        return "Bengaluru"
    if any(k in c for k in ("mumbai", "bombay", "thane", "navi mumbai")):
        return "Mumbai"
    if any(k in c for k in ("delhi", "new delhi", "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad")):
        return "Delhi"
    if any(k in c for k in ("chennai", "madras")):
        return "Chennai"
    if any(k in c for k in ("kolkata", "calcutta", "howrah")):
        return "Kolkata"
    if "pune" in c or "pimpri" in c:
        return "Pune"
    if "hyderabad" in c or "secunderabad" in c or "cyberabad" in c:
        return "Hyderabad"
    if "ahmedabad" in c:
        return "Ahmedabad"
    if "jaipur" in c:
        return "Jaipur"
    if "lucknow" in c:
        return "Lucknow"
    if "chandigarh" in c:
        return "Chandigarh"
    # General title-cased city name
    return city.strip().title()


def lookup_city_info_from_coords(lat: float, lng: float) -> Optional[dict[str, Any]]:
    """Determine city region info from latitude and longitude coordinates."""
    for region in _INDIAN_CITY_REGIONS:
        if (
            region["min_lat"] <= lat <= region["max_lat"]
            and region["min_lng"] <= lng <= region["max_lng"]
        ):
            return dict(region)
    return None


def lookup_city_from_coords(lat: float, lng: float) -> str:
    """Return normalized city name from coordinates or empty string."""
    info = lookup_city_info_from_coords(lat, lng)
    return info["city"] if info else ""


# ── Major City Department Registries ──────────────────────────────────────────

CITY_DEPARTMENT_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {
    "Bengaluru": {
        "roads_dept": {
            "department_id": "bbmp_roads",
            "name": "Bruhat Bengaluru Mahanagara Palike (BBMP) — Road Infrastructure Division",
            "short_name": "BBMP Road Infrastructure",
            "tier": 1,
            "contact_email": "roads@bbmp.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
            "description": "Responsible for major municipal roads, arterial corridors, and pothole repairs across all BBMP zones.",
        },
        "water_dept": {
            "department_id": "bwssb_water_sewage",
            "name": "Bangalore Water Supply and Sewerage Board (BWSSB)",
            "short_name": "BWSSB (Water & Sewerage)",
            "tier": 1,
            "contact_email": "complaints@bwssb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Responsible for drinking water supply distribution, pipeline ruptures, municipal sewerage networks, and manhole maintenance across Bengaluru.",
        },
        "electricity_dept": {
            "department_id": "bescom_electricity",
            "name": "Bangalore Electricity Supply Company Limited (BESCOM) — Streetlights & Power Wing",
            "short_name": "BESCOM Streetlights",
            "tier": 1,
            "contact_email": "helpline@bescom.co.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Responsible for public streetlights, power distribution, transformers, and electrical safety hazards in Bengaluru.",
        },
        "sanitation_dept": {
            "department_id": "bbmp_sanitation",
            "name": "BBMP Solid Waste Management (SWM) Department",
            "short_name": "BBMP Sanitation & SWM",
            "tier": 1,
            "contact_email": "swm@bbmp.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Door-to-door garbage collection, community dumpster clearing, and public sanitation across BBMP wards.",
        },
        "horticulture_dept": {
            "department_id": "bbmp_forest_trees",
            "name": "BBMP Forest Cell & Tree Authority",
            "short_name": "BBMP Tree Authority",
            "tier": 1,
            "contact_email": "trees@bbmp.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 12,
            "description": "Removal of fallen trees, trimming of dangerous branches, and urban forestry in Bengaluru.",
        },
        "pollution_board": {
            "department_id": "kspcb_pollution",
            "name": "Karnataka State Pollution Control Board (KSPCB — Bengaluru Urban)",
            "short_name": "KSPCB",
            "tier": 1,
            "contact_email": "complaints@kspcb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
            "description": "Enforces ambient air quality standards, water pollution controls, and industrial emission regulations in Bengaluru.",
        },
        "disaster_mgmt": {
            "department_id": "bbmp_disaster_cell",
            "name": "BBMP Disaster Management Cell & Karnataka SDMA",
            "short_name": "BBMP Disaster Cell",
            "tier": 1,
            "contact_email": "disaster@bbmp.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 6,
            "description": "Coordinates rapid storm water drain clearance, waterlogging response, and flood relief across Bengaluru.",
        },
        "collector_office": {
            "department_id": "collector_office_blr",
            "name": "District Collector's Office (Bengaluru Urban)",
            "short_name": "Collector Office Bengaluru",
            "tier": 2,
            "contact_email": "collector.blr@karnataka.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
            "description": "District-level administrative escalation authority for Bengaluru Urban.",
        },
        "general_desk": {
            "department_id": "bbmp_sahaaya",
            "name": "BBMP Sahaaya Public Grievance Redressal Desk",
            "short_name": "BBMP Sahaaya Desk",
            "tier": 2,
            "contact_email": "grievance@bbmp.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
            "description": "Central municipal public grievance intake and manual dispatch cell for BBMP.",
        },
        "nhai_dept": {
            "department_id": "nhai_bengaluru",
            "name": "National Highways Authority of India (NHAI — Regional Office Bengaluru)",
            "short_name": "NHAI Bengaluru",
            "tier": 1,
            "contact_email": "ro.bengaluru@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
            "description": "National highway corridors passing through Bengaluru urban and rural agglomeration.",
        },
    },
    "Mumbai": {
        "roads_dept": {
            "department_id": "bmc_roads",
            "name": "Brihanmumbai Municipal Corporation (BMC / MCGM) — Roads & Traffic Department",
            "short_name": "BMC Roads & Traffic",
            "tier": 1,
            "contact_email": "roads@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
            "description": "Responsible for municipal carriageways, arterial roads, asphalt craters, and pothole maintenance in Mumbai.",
        },
        "water_dept": {
            "department_id": "bmc_water_sewerage",
            "name": "BMC Hydraulic Engineering & Sewerage Operations Department",
            "short_name": "BMC Hydraulic & Sewerage",
            "tier": 1,
            "contact_email": "water@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Responsible for pressurized potable water mains, pipeline ruptures, municipal sewers, and manholes in Mumbai.",
        },
        "electricity_dept": {
            "department_id": "best_adani_streetlights",
            "name": "Brihanmumbai Electric Supply & Transport (BEST) / Adani Electricity (Streetlights Division)",
            "short_name": "BEST / Adani Streetlights",
            "tier": 1,
            "contact_email": "streetlights@bestundertaking.com",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Streetlight pole repairs, 230V live wire emergencies, and dark corridor illumination across Mumbai.",
        },
        "sanitation_dept": {
            "department_id": "bmc_sanitation",
            "name": "BMC Solid Waste Management (SWM) Department",
            "short_name": "BMC Sanitation & SWM",
            "tier": 1,
            "contact_email": "swm@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Municipal garbage clearance, community dumpster collection, and debris clearing in Mumbai.",
        },
        "horticulture_dept": {
            "department_id": "bmc_tree_authority",
            "name": "BMC Garden & Tree Authority",
            "short_name": "BMC Tree Authority",
            "tier": 1,
            "contact_email": "garden@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 12,
            "description": "Removal of fallen trees blocking traffic and hazardous overhanging tree branches in Mumbai.",
        },
        "pollution_board": {
            "department_id": "mpcb_pollution",
            "name": "Maharashtra Pollution Control Board (MPCB — Mumbai Division)",
            "short_name": "MPCB Mumbai",
            "tier": 1,
            "contact_email": "complaints@mpcb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
            "description": "Industrial emission control, coastal waste regulations, and air pollution enforcement in Mumbai.",
        },
        "disaster_mgmt": {
            "department_id": "bmc_disaster_mgmt",
            "name": "BMC Disaster Management Department (Disaster Control Room)",
            "short_name": "BMC Disaster Control",
            "tier": 1,
            "contact_email": "disaster@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 6,
            "description": "Operates 24/7 monsoon control room for waterlogging, high-tide flooding, and civic emergencies.",
        },
        "collector_office": {
            "department_id": "collector_office_mumbai",
            "name": "Collector Office & District Magistrate (Mumbai City & Suburban)",
            "short_name": "Collector Office Mumbai",
            "tier": 2,
            "contact_email": "collector.mumbai@maharashtra.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
        },
        "general_desk": {
            "department_id": "bmc_1916_desk",
            "name": "BMC Central Public Grievance Desk (Portal 1916)",
            "short_name": "BMC 1916 Grievance Desk",
            "tier": 2,
            "contact_email": "grievance@mcgm.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
        "nhai_dept": {
            "department_id": "nhai_mumbai",
            "name": "National Highways Authority of India (NHAI — Regional Office Mumbai)",
            "short_name": "NHAI Mumbai",
            "tier": 1,
            "contact_email": "ro.mumbai@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
    },
    "Delhi": {
        "roads_dept": {
            "department_id": "mcd_pwd_roads",
            "name": "Municipal Corporation of Delhi (MCD) / Public Works Department (PWD Delhi)",
            "short_name": "MCD / PWD Roads",
            "tier": 1,
            "contact_email": "roads@mcd.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
            "description": "Responsible for municipal roads and arterial road repair across Delhi NCR.",
        },
        "water_dept": {
            "department_id": "djb_water_sewerage",
            "name": "Delhi Jal Board (DJB)",
            "short_name": "Delhi Jal Board (DJB)",
            "tier": 1,
            "contact_email": "complaints@delhijalboard.nic.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Responsible for potable drinking water supply, pipeline ruptures, and sewerage network in Delhi.",
        },
        "electricity_dept": {
            "department_id": "bses_tpddl_streetlights",
            "name": "BSES / Tata Power Delhi Distribution Limited (TPDDL) — Streetlights Wing",
            "short_name": "BSES / TPDDL Streetlights",
            "tier": 1,
            "contact_email": "streetlights@bsesdelhi.com",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Maintenance of streetlights, exposed live wires, and electric poles across Delhi NCR.",
        },
        "sanitation_dept": {
            "department_id": "mcd_sanitation_dems",
            "name": "MCD Department of Environment Management Services (DEMS)",
            "short_name": "MCD Sanitation (DEMS)",
            "tier": 1,
            "contact_email": "dems@mcd.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
            "description": "Solid waste management, community garbage dump clearing, and street cleanliness in Delhi.",
        },
        "horticulture_dept": {
            "department_id": "mcd_horticulture",
            "name": "MCD Horticulture Department & Delhi Tree Authority",
            "short_name": "MCD Horticulture & Trees",
            "tier": 1,
            "contact_email": "horticulture@mcd.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 12,
        },
        "pollution_board": {
            "department_id": "dpcc_pollution",
            "name": "Delhi Pollution Control Committee (DPCC)",
            "short_name": "DPCC",
            "tier": 1,
            "contact_email": "complaints@dpcc.delhigovt.nic.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "disaster_mgmt": {
            "department_id": "delhi_ddma",
            "name": "Delhi Disaster Management Authority (DDMA)",
            "short_name": "DDMA Delhi",
            "tier": 1,
            "contact_email": "ddma@delhigovt.nic.in",
            "contact_webhook": None,
            "sla_hours_default": 6,
        },
        "collector_office": {
            "department_id": "dm_revenue_delhi",
            "name": "Office of the District Magistrate & Revenue Department (Delhi)",
            "short_name": "District Magistrate Delhi",
            "tier": 2,
            "contact_email": "dm.revenue@delhigovt.nic.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
        },
        "general_desk": {
            "department_id": "mcd_311_desk",
            "name": "MCD Central Public Grievance Redressal Desk (MCD 311)",
            "short_name": "MCD 311 Grievance Desk",
            "tier": 2,
            "contact_email": "grievance@mcd.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
        "nhai_dept": {
            "department_id": "nhai_delhi",
            "name": "National Highways Authority of India (NHAI — Regional Office Delhi)",
            "short_name": "NHAI Delhi",
            "tier": 1,
            "contact_email": "ro.delhi@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
    },
    "Chennai": {
        "roads_dept": {
            "department_id": "gcc_roads",
            "name": "Greater Chennai Corporation (GCC) — Works & Road Department",
            "short_name": "GCC Road Department",
            "tier": 1,
            "contact_email": "roads@chennaicorporation.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "water_dept": {
            "department_id": "cmwssb_water_sewerage",
            "name": "Chennai Metro Water Supply & Sewerage Board (CMWSSB)",
            "short_name": "CMWSSB (Metro Water)",
            "tier": 1,
            "contact_email": "complaints@chennaimetrowater.tn.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "electricity_dept": {
            "department_id": "tangedco_streetlights",
            "name": "Tamil Nadu Generation and Distribution Corporation (TANGEDCO) / GCC Electrical Department",
            "short_name": "TANGEDCO / GCC Streetlights",
            "tier": 1,
            "contact_email": "streetlights@tangedco.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "sanitation_dept": {
            "department_id": "gcc_sanitation",
            "name": "Greater Chennai Corporation (GCC) — Solid Waste Management",
            "short_name": "GCC Sanitation & SWM",
            "tier": 1,
            "contact_email": "swm@chennaicorporation.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "horticulture_dept": {
            "department_id": "gcc_parks_trees",
            "name": "GCC Parks and Playgrounds Department (Tree Authority)",
            "short_name": "GCC Tree Authority",
            "tier": 1,
            "contact_email": "parks@chennaicorporation.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 12,
        },
        "pollution_board": {
            "department_id": "tnpcb_pollution",
            "name": "Tamil Nadu Pollution Control Board (TNPCB — Chennai District)",
            "short_name": "TNPCB Chennai",
            "tier": 1,
            "contact_email": "complaints@tnpcb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "disaster_mgmt": {
            "department_id": "gcc_disaster_cell",
            "name": "Greater Chennai Corporation Disaster Management Cell",
            "short_name": "GCC Disaster Cell",
            "tier": 1,
            "contact_email": "disaster@chennaicorporation.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 6,
        },
        "collector_office": {
            "department_id": "collector_office_chennai",
            "name": "District Collectorate (Chennai)",
            "short_name": "Collectorate Chennai",
            "tier": 2,
            "contact_email": "collrchn@nic.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
        },
        "general_desk": {
            "department_id": "gcc_1913_desk",
            "name": "Greater Chennai Corporation 1913 Public Grievance Desk",
            "short_name": "GCC 1913 Grievance Desk",
            "tier": 2,
            "contact_email": "grievance@chennaicorporation.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
        "nhai_dept": {
            "department_id": "nhai_chennai",
            "name": "National Highways Authority of India (NHAI — Regional Office Chennai)",
            "short_name": "NHAI Chennai",
            "tier": 1,
            "contact_email": "ro.chennai@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
    },
    "Kolkata": {
        "roads_dept": {
            "department_id": "kmc_roads",
            "name": "Kolkata Municipal Corporation (KMC) — Roads Department",
            "short_name": "KMC Roads",
            "tier": 1,
            "contact_email": "roads@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "water_dept": {
            "department_id": "kmc_water_drainage",
            "name": "Kolkata Municipal Corporation (KMC) — Water Supply & Sewerage Drainage Department",
            "short_name": "KMC Water & Sewerage",
            "tier": 1,
            "contact_email": "watersupply@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "electricity_dept": {
            "department_id": "cesc_kmc_lighting",
            "name": "CESC / Kolkata Municipal Corporation Lighting Department",
            "short_name": "CESC / KMC Lighting",
            "tier": 1,
            "contact_email": "lighting@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "sanitation_dept": {
            "department_id": "kmc_sanitation",
            "name": "Kolkata Municipal Corporation (KMC) — Solid Waste Management",
            "short_name": "KMC Sanitation & SWM",
            "tier": 1,
            "contact_email": "swm@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "horticulture_dept": {
            "department_id": "kmc_parks_trees",
            "name": "KMC Parks & Square Department",
            "short_name": "KMC Parks & Trees",
            "tier": 1,
            "contact_email": "parks@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 12,
        },
        "pollution_board": {
            "department_id": "wbpcb_pollution",
            "name": "West Bengal Pollution Control Board (WBPCB)",
            "short_name": "WBPCB",
            "tier": 1,
            "contact_email": "complaints@wbpcb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "disaster_mgmt": {
            "department_id": "kmc_disaster_mgmt",
            "name": "Kolkata Municipal Corporation (KMC) — Disaster Management Department",
            "short_name": "KMC Disaster Cell",
            "tier": 1,
            "contact_email": "disaster@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 6,
        },
        "collector_office": {
            "department_id": "dm_kolkata",
            "name": "District Magistrate Office (Kolkata)",
            "short_name": "DM Office Kolkata",
            "tier": 2,
            "contact_email": "dm-kol@nic.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
        },
        "general_desk": {
            "department_id": "kmc_general_desk",
            "name": "KMC Central Municipal Grievance Cell",
            "short_name": "KMC Grievance Desk",
            "tier": 2,
            "contact_email": "grievance@kmcgov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
        "nhai_dept": {
            "department_id": "nhai_kolkata",
            "name": "National Highways Authority of India (NHAI — Regional Office Kolkata)",
            "short_name": "NHAI Kolkata",
            "tier": 1,
            "contact_email": "ro.kolkata@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
    },
    "Pune": {
        "roads_dept": {
            "department_id": "pmc_roads",
            "name": "Pune Municipal Corporation (PMC) — Road Department",
            "short_name": "PMC Road Department",
            "tier": 1,
            "contact_email": "roads@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "water_dept": {
            "department_id": "pmc_water_drainage",
            "name": "PMC Water Supply & Sewerage Drainage Department",
            "short_name": "PMC Water & Drainage",
            "tier": 1,
            "contact_email": "watersupply@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "electricity_dept": {
            "department_id": "msedcl_pmc_electrical",
            "name": "Maharashtra State Electricity Distribution Co. Ltd. (MSEDCL) / PMC Electrical Department",
            "short_name": "MSEDCL / PMC Streetlights",
            "tier": 1,
            "contact_email": "streetlights@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "sanitation_dept": {
            "department_id": "pmc_sanitation",
            "name": "Pune Municipal Corporation (PMC) — Solid Waste Management Department",
            "short_name": "PMC Sanitation & SWM",
            "tier": 1,
            "contact_email": "swm@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 24,
        },
        "horticulture_dept": {
            "department_id": "pmc_tree_authority",
            "name": "PMC Tree Authority & Garden Department",
            "short_name": "PMC Tree Authority",
            "tier": 1,
            "contact_email": "garden@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 12,
        },
        "pollution_board": {
            "department_id": "mpcb_pune",
            "name": "Maharashtra Pollution Control Board (MPCB — Pune Division)",
            "short_name": "MPCB Pune",
            "tier": 1,
            "contact_email": "complaints.pune@mpcb.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 48,
        },
        "disaster_mgmt": {
            "department_id": "pmc_disaster_cell",
            "name": "Pune Municipal Corporation (PMC) — Disaster Management Cell",
            "short_name": "PMC Disaster Cell",
            "tier": 1,
            "contact_email": "disaster@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 6,
        },
        "collector_office": {
            "department_id": "collector_office_pune",
            "name": "District Collector Office (Pune)",
            "short_name": "Collector Office Pune",
            "tier": 2,
            "contact_email": "collector.pune@maharashtra.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 96,
        },
        "general_desk": {
            "department_id": "pmc_grievance_desk",
            "name": "PMC Central Grievance Redressal Cell",
            "short_name": "PMC Grievance Desk",
            "tier": 2,
            "contact_email": "grievance@punecorporation.org",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
        "nhai_dept": {
            "department_id": "nhai_pune",
            "name": "National Highways Authority of India (NHAI — Regional Office Pune)",
            "short_name": "NHAI Pune",
            "tier": 1,
            "contact_email": "ro.pune@nhai.gov.in",
            "contact_webhook": None,
            "sla_hours_default": 72,
        },
    },
}


def generate_dynamic_city_department(department_id: str, city: str) -> dict[str, Any]:
    """
    Generate an authentic, structured Urban Local Body department profile
    for any Indian city or municipality.
    """
    clean_city = city.strip().title()
    slug = re.sub(r"[^a-zA-Z0-9]+", "", clean_city.lower()) or "municipal"

    dept_templates = {
        "roads_dept": {
            "name": f"{clean_city} Municipal Corporation — Engineering & Roads Division",
            "short_name": f"{clean_city} Roads",
            "tier": 1,
            "contact_email": f"roads@{slug}.municipal.gov.in",
            "sla_hours_default": 48,
            "description": f"Responsible for municipal roads, street repairs, and pothole maintenance in {clean_city}.",
        },
        "water_dept": {
            "name": f"{clean_city} Municipal Water Supply & Sewerage Department",
            "short_name": f"{clean_city} Water & Sewage",
            "tier": 1,
            "contact_email": f"water@{slug}.municipal.gov.in",
            "sla_hours_default": 24,
            "description": f"Responsible for potable water distribution, pipeline ruptures, and sewerage network in {clean_city}.",
        },
        "electricity_dept": {
            "name": f"{clean_city} Municipal Corporation — Electrical & Street Lighting Wing",
            "short_name": f"{clean_city} Streetlights",
            "tier": 1,
            "contact_email": f"streetlights@{slug}.municipal.gov.in",
            "sla_hours_default": 24,
            "description": f"Responsible for public street lighting, junction boxes, and electrical safety in {clean_city}.",
        },
        "sanitation_dept": {
            "name": f"{clean_city} Municipal Corporation — Sanitation & Solid Waste Management (SWM)",
            "short_name": f"{clean_city} Sanitation & SWM",
            "tier": 1,
            "contact_email": f"swm@{slug}.municipal.gov.in",
            "sla_hours_default": 24,
            "description": f"Door-to-door garbage collection, community dumpster clearing, and street sweeping in {clean_city}.",
        },
        "horticulture_dept": {
            "name": f"{clean_city} Municipal Tree Authority & Horticulture Wing",
            "short_name": f"{clean_city} Tree Authority",
            "tier": 1,
            "contact_email": f"horticulture@{slug}.municipal.gov.in",
            "sla_hours_default": 12,
            "description": f"Hazardous branch trimming and fallen tree clearing in {clean_city}.",
        },
        "pollution_board": {
            "name": f"State Pollution Control Board ({clean_city} Regional Directorate)",
            "short_name": f"{clean_city} Pollution Board",
            "tier": 1,
            "contact_email": f"pollution@{slug}.spcb.gov.in",
            "sla_hours_default": 48,
            "description": f"Industrial emission, waste burning, and air/water quality enforcement in {clean_city}.",
        },
        "disaster_mgmt": {
            "name": f"District Disaster Management Authority (DDMA {clean_city})",
            "short_name": f"DDMA {clean_city}",
            "tier": 1,
            "contact_email": f"ddma@{slug}.gov.in",
            "sla_hours_default": 6,
            "description": f"Emergency flood relief, drainage overflow response, and disaster mitigation in {clean_city}.",
        },
        "collector_office": {
            "name": f"District Collector & District Magistrate Office ({clean_city})",
            "short_name": f"Collector Office {clean_city}",
            "tier": 2,
            "contact_email": f"collector@{slug}.gov.in",
            "sla_hours_default": 96,
            "description": f"District-level administrative escalation authority for {clean_city}.",
        },
        "general_desk": {
            "name": f"{clean_city} Municipal Corporation — Central Grievance Redressal Desk",
            "short_name": f"{clean_city} Grievance Desk",
            "tier": 2,
            "contact_email": f"grievance@{slug}.municipal.gov.in",
            "sla_hours_default": 72,
            "description": f"Central public grievance intake and manual dispatch cell for {clean_city}.",
        },
        "nhai_dept": {
            "name": f"National Highways Authority of India (NHAI — Regional Division {clean_city})",
            "short_name": f"NHAI {clean_city}",
            "tier": 1,
            "contact_email": f"ro.{slug}@nhai.gov.in",
            "sla_hours_default": 72,
            "description": f"National Highways Authority of India jurisdiction for highway corridors passing through {clean_city}.",
        },
    }

    template = dept_templates.get(department_id, dept_templates["general_desk"])
    return {
        "department_id": f"{slug}_{department_id}",
        "name": template["name"],
        "short_name": template["short_name"],
        "tier": template["tier"],
        "contact_email": template["contact_email"],
        "contact_webhook": None,
        "sla_hours_default": template["sla_hours_default"],
        "description": template["description"],
    }


def resolve_city_jurisdiction(
    city: Optional[str],
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict[str, Any]:
    """Return an administrative jurisdiction descriptor for the given city/coordinates."""
    resolved_city = normalize_city_name(city)
    if not resolved_city and lat is not None and lon is not None:
        resolved_city = lookup_city_from_coords(lat, lon)

    if not resolved_city:
        resolved_city = "Hyderabad"

    admin_bodies = {
        "Bengaluru": "Bruhat Bengaluru Mahanagara Palike (BBMP)",
        "Mumbai": "Brihanmumbai Municipal Corporation (BMC / MCGM)",
        "Delhi": "Municipal Corporation of Delhi (MCD)",
        "Chennai": "Greater Chennai Corporation (GCC)",
        "Kolkata": "Kolkata Municipal Corporation (KMC)",
        "Pune": "Pune Municipal Corporation (PMC)",
        "Hyderabad": "Greater Hyderabad Municipal Corporation (GHMC)",
        "Ahmedabad": "Amdavad Municipal Corporation (AMC)",
        "Jaipur": "Jaipur Nagar Nigam",
        "Lucknow": "Lucknow Municipal Corporation (LMC)",
        "Chandigarh": "Municipal Corporation Chandigarh (MCC)",
    }
    admin_body = admin_bodies.get(resolved_city, f"{resolved_city} Municipal Corporation")
    slug = re.sub(r"[^a-zA-Z0-9]+", "", resolved_city.lower()) or "municipal"

    return {
        "jurisdiction_id": f"{slug}_zone_central",
        "name": f"{resolved_city} Administrative Zone ({admin_body})",
        "zone_type": "zone",
        "city": resolved_city,
        "district": resolved_city,
        "state": "India",
        "administrative_body": admin_body,
        "is_active": True,
    }

