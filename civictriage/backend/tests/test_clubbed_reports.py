"""
tests/test_clubbed_reports.py
=============================
Unit tests verifying:
1. Clustered reports for the same issue are clubbed into ONE ticket in dispatcher.
2. Admin /admin/tickets API clubs clustered reports into one entry with report count and IDs.
3. Pan-India routing correctly resolves municipal authorities across different cities.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from bson import ObjectId

from app.core.database import InMemoryDatabase
from app.api.routers.admin import list_tickets
from app.services.city_directory import (
    lookup_city_info_from_coords,
    resolve_city_jurisdiction,
    normalize_city_name,
)


@pytest.mark.asyncio
async def test_admin_list_tickets_clubs_clustered_reports():
    """Verify that multiple reports or tickets referencing the same issue are clubbed into one ticket."""
    db = InMemoryDatabase()

    issue_id = str(ObjectId())
    now = datetime.now(timezone.utc)

    # 1. Create the issue document in db.issues with 3 clustered reports
    await db.issues.insert_one({
        "_id": ObjectId(issue_id),
        "category": "pothole",
        "city": "Bengaluru",
        "address": "Outer Ring Road, Bellandur, Bengaluru",
        "ward": "Ward 150 - Bellandur",
        "status": "open",
        "report_count": 3,
        "report_ids": ["rep_blr_001", "rep_blr_002", "rep_blr_003"],
        "priority_score": 0.88,
        "severity_tier": "tier_1",
        "combined_description": "Severe pothole cluster causing vehicle slowdowns near Bellandur flyover.",
        "created_at": now,
        "updated_at": now,
    })

    # 2. Simulate historical / separate ticket entries for that issue
    await db.tickets.insert_one({
        "_id": ObjectId(),
        "issue_id": issue_id,
        "report_id": "rep_blr_001",
        "clustered_report_ids": ["rep_blr_001"],
        "report_count": 1,
        "authority_name": "BBMP Roads & Infrastructure",
        "department_id": "bbmp_roads",
        "tier": 1,
        "sla_deadline": now,
        "status": "open",
        "status_history": [{"status": "open", "timestamp": now, "note": "Dispatched", "updated_by": "system"}],
        "created_at": now,
        "updated_at": now,
    })

    # Second report entry for same issue
    await db.tickets.insert_one({
        "_id": ObjectId(),
        "issue_id": issue_id,
        "report_id": "rep_blr_002",
        "clustered_report_ids": ["rep_blr_002"],
        "report_count": 1,
        "authority_name": "BBMP Roads & Infrastructure",
        "department_id": "bbmp_roads",
        "tier": 1,
        "sla_deadline": now,
        "status": "open",
        "status_history": [{"status": "open", "timestamp": now, "note": "Clustered report 2", "updated_by": "system"}],
        "created_at": now,
        "updated_at": now,
    })

    # Also create a completely separate issue in Mumbai
    mumbai_issue_id = str(ObjectId())
    await db.issues.insert_one({
        "_id": ObjectId(mumbai_issue_id),
        "category": "garbage_dump",
        "city": "Mumbai",
        "address": "Dadar West, Mumbai",
        "ward": "Ward G/North",
        "status": "open",
        "report_count": 1,
        "report_ids": ["rep_mum_001"],
        "priority_score": 0.65,
        "severity_tier": "tier_2",
        "created_at": now,
        "updated_at": now,
    })
    await db.tickets.insert_one({
        "_id": ObjectId(),
        "issue_id": mumbai_issue_id,
        "report_id": "rep_mum_001",
        "clustered_report_ids": ["rep_mum_001"],
        "report_count": 1,
        "authority_name": "BMC Solid Waste Management",
        "department_id": "bmc_swm",
        "tier": 1,
        "sla_deadline": now,
        "status": "open",
        "status_history": [{"status": "open", "timestamp": now, "note": "Dispatched", "updated_by": "system"}],
        "created_at": now,
        "updated_at": now,
    })

    # Call list_tickets via mocking get_db
    import app.api.routers.admin as admin_module
    orig_get_db = admin_module.get_db

    async def _mock_get_db():
        return db

    admin_module.get_db = _mock_get_db

    try:
        clubbed = await list_tickets()
        # Out of 3 ticket docs in db.tickets, they should be clubbed into exactly 2 rows!
        assert len(clubbed) == 2, f"Expected 2 clubbed rows, got {len(clubbed)}"

        # Find the Bengaluru ticket
        blr_ticket = next(t for t in clubbed if t["issue_id"] == issue_id)
        assert blr_ticket["report_count"] == 3
        assert set(blr_ticket["clustered_report_ids"]) == {"rep_blr_001", "rep_blr_002", "rep_blr_003"}
        assert blr_ticket["category"] == "pothole"
        assert blr_ticket["city"] == "Bengaluru"
        assert "BBMP" in blr_ticket["authority_name"]

        # Find the Mumbai ticket
        mum_ticket = next(t for t in clubbed if t["issue_id"] == mumbai_issue_id)
        assert mum_ticket["report_count"] == 1
        assert mum_ticket["city"] == "Mumbai"
        assert "BMC" in mum_ticket["authority_name"]
    finally:
        admin_module.get_db = orig_get_db


def test_pan_india_city_routing_resolution():
    """Verify city directory and jurisdiction resolver across multiple Indian cities."""
    # Bengaluru Bellandur
    blr = lookup_city_info_from_coords(12.9260, 77.6762)
    assert blr["city"] == "Bengaluru"

    # Mumbai Dadar
    mum = lookup_city_info_from_coords(19.0178, 72.8478)
    assert mum["city"] == "Mumbai"

    # Delhi Connaught Place
    delhi = lookup_city_info_from_coords(28.6315, 77.2167)
    assert delhi["city"] == "Delhi"

    # Chennai T. Nagar
    chn = lookup_city_info_from_coords(13.0418, 80.2341)
    assert chn["city"] == "Chennai"

    # Kolkata Park Street
    kol = lookup_city_info_from_coords(22.5535, 88.3518)
    assert kol["city"] == "Kolkata"

    # Pune Shivaji Nagar
    pune = lookup_city_info_from_coords(18.5314, 73.8446)
    assert pune["city"] == "Pune"

    # Hyderabad Jubilee Hills
    hyd = lookup_city_info_from_coords(17.4319, 78.4087)
    assert hyd["city"] == "Hyderabad"

    # Test department jurisdiction resolution
    blr_jurisdiction = resolve_city_jurisdiction("Bengaluru", 12.9260, 77.6762)
    assert blr_jurisdiction["city"] == "Bengaluru"
    assert "BBMP" in blr_jurisdiction["administrative_body"]

    mum_jurisdiction = resolve_city_jurisdiction("Mumbai", 19.0178, 72.8478)
    assert mum_jurisdiction["city"] == "Mumbai"
    assert "BMC" in mum_jurisdiction["administrative_body"]

    delhi_jurisdiction = resolve_city_jurisdiction("Delhi", 28.6315, 77.2167)
    assert delhi_jurisdiction["city"] == "Delhi"
    assert "MCD" in delhi_jurisdiction["administrative_body"]

    # Test tier-2 / tier-3 dynamic ULB generation
    lucknow_jurisdiction = resolve_city_jurisdiction("Lucknow", 26.8467, 80.9462)
    assert "Lucknow" in lucknow_jurisdiction["administrative_body"]


if __name__ == "__main__":
    test_pan_india_city_routing_resolution()
    print("[PASS] Pan-India city directory & jurisdiction tests passed!")
    asyncio.run(test_admin_list_tickets_clubs_clustered_reports())
    print("[PASS] Admin list_tickets clustered report clubbing tests passed!")
