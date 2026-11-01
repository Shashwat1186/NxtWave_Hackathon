"""
tests/test_clustering_dedup.py
==============================
Automated tests verifying clustering & deduplication logic:
  1. Only similar problems at the same location merge into clusters.
  2. Pothole vs Streetlight at the exact same GPS coordinates must NEVER merge.
  3. Water leak vs Garbage at the exact same location must NEVER merge.
  4. Same defect far apart (> 100 meters) must NOT merge.
  5. Same defect close together (<= 50 meters) DOES merge and increments cluster_size.
  6. Defect taxonomy extraction and disjoint compatibility checks.
"""

from __future__ import annotations

import asyncio
from app.agents.nodes.deduplicator import (
    deduplicator,
    haversine,
    are_defect_families_compatible,
    detect_defect_families,
    compute_problem_similarity,
)
from app.core.database import InMemoryDatabase
from app.core.sse_bus import SSEBus
from app.models.schemas import IssueCategory, PerceptionOutput, VisualObservation, GeoResolverOutput, GeoPoint


class MockEmbedService:
    """Mock embed service generating predictable vectors based on text features."""
    async def embed(self, text: str) -> list[float]:
        txt = text.lower()
        if "pothole" in txt or "crater" in txt:
            return [1.0, 0.0, 0.0, 0.0] + [0.0] * 3068
        elif "streetlight" in txt or "lamp" in txt or "wire" in txt:
            return [0.0, 1.0, 0.0, 0.0] + [0.0] * 3068
        elif "water" in txt or "pipe" in txt:
            return [0.0, 0.0, 1.0, 0.0] + [0.0] * 3068
        elif "garbage" in txt or "waste" in txt:
            return [0.0, 0.0, 0.0, 1.0] + [0.0] * 3068
        return [0.5, 0.5, 0.0, 0.0] + [0.0] * 3068


def test_pothole_and_streetlight_same_location_do_not_merge():
    """Verify that a pothole and a streetlight at the exact same GPS coordinates create 2 separate issues."""
    async def _run():
        db = InMemoryDatabase()
        bus = SSEBus()
        embed_svc = MockEmbedService()

        # Report 1: Pothole at Apollo Hospital Jubilee Hills (17.4319, 78.4087)
        state1 = {
            "report_id": "rep_pothole_1",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.ROAD_DAMAGE,
                combined_description="Deep crater-like pothole on 4-lane arterial road Jubilee Hills Near Apollo Hospital Hyderabad",
                confidence=0.95,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.ROAD_DAMAGE,
                    damage_features=["pothole", "cracked_asphalt"],
                    hazard_indicators=["vehicle_damage"],
                    confidence=0.95,
                    raw_description="Deep pothole in asphalt roadway.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.4087, 17.4319]),
                address="Road No. 36, Near Apollo Hospital",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                road_name="Road No. 36",
                road_class="primary",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res1 = await deduplicator(state1, bus=bus, db=db, embed_service=embed_svc)
        assert res1["dedup_output"].action == "created"
        assert res1["dedup_output"].cluster_size == 1
        issue1_id = res1["dedup_output"].issue_id

        # Report 2: Streetlight at the EXACT same GPS coordinates (17.4319, 78.4087)
        state2 = {
            "report_id": "rep_streetlight_2",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.STREETLIGHT,
                combined_description="Series of LED streetlights dead with exposed 230V live wire Near Apollo Hospital Hyderabad",
                confidence=0.95,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.STREETLIGHT,
                    damage_features=["broken_light_pole", "exposed_wire"],
                    hazard_indicators=["electrical_hazard"],
                    confidence=0.95,
                    raw_description="Broken streetlight and exposed dangling wire.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.4087, 17.4319]),
                address="Road No. 36, Near Apollo Hospital",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                road_name="Road No. 36",
                road_class="primary",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res2 = await deduplicator(state2, bus=bus, db=db, embed_service=embed_svc)

        # Must NOT merge: must create a new issue with a distinct issue_id
        assert res2["dedup_output"].action == "created", "Streetlight must not merge into pothole cluster"
        assert res2["dedup_output"].cluster_size == 1
        assert res2["dedup_output"].issue_id != issue1_id, "Different issues must have distinct issue IDs"

        # Verify both issues exist in database
        issues_list = await db.issues.find().to_list(10)
        assert len(issues_list) == 2, "Database must store 2 distinct issues"
        categories = {iss["category"] for iss in issues_list}
        assert categories == {"road_damage", "streetlight"}

    asyncio.run(_run())


def test_two_similar_potholes_same_location_do_merge():
    """Verify that two reports of the same pothole at the same location merge into a cluster."""
    async def _run():
        db = InMemoryDatabase()
        bus = SSEBus()
        embed_svc = MockEmbedService()

        # Report 1: Pothole
        state1 = {
            "report_id": "rep_pothole_a",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.ROAD_DAMAGE,
                combined_description="Dangerous deep crater pothole near Apollo Hospital Road 36 Jubilee Hills",
                confidence=0.92,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.ROAD_DAMAGE,
                    damage_features=["pothole", "cracked_asphalt"],
                    hazard_indicators=["traffic_hazard"],
                    confidence=0.92,
                    raw_description="Deep pothole in roadway.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.4087, 17.4319]),
                address="Road No. 36, Near Apollo Hospital",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                road_name="Road No. 36",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res1 = await deduplicator(state1, bus=bus, db=db, embed_service=embed_svc)
        assert res1["dedup_output"].action == "created"
        issue1_id = res1["dedup_output"].issue_id

        # Report 2: Citizen 2 reports the same pothole 15 meters away
        state2 = {
            "report_id": "rep_pothole_b",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.ROAD_DAMAGE,
                combined_description="Large asphalt pothole causing severe vehicle swerving near Apollo Hospital Road 36",
                confidence=0.90,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.ROAD_DAMAGE,
                    damage_features=["pothole", "surface_subsidence"],
                    hazard_indicators=["swerving_hazard"],
                    confidence=0.90,
                    raw_description="Large pothole on the road.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                # ~15 meters away
                location=GeoPoint(type="Point", coordinates=[78.4088, 17.4320]),
                address="Road No. 36, Near Apollo Hospital",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                road_name="Road No. 36",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res2 = await deduplicator(state2, bus=bus, db=db, embed_service=embed_svc)
        assert res2["dedup_output"].action == "merged", "Second pothole report must merge into existing cluster"
        assert res2["dedup_output"].issue_id == issue1_id
        assert res2["dedup_output"].cluster_size == 2

        # Verify report_count in DB is 2
        issue_doc = await db.issues.find_one({"_id": issue1_id})
        assert issue_doc["report_count"] == 2
        assert "rep_pothole_a" in issue_doc["report_ids"]
        assert "rep_pothole_b" in issue_doc["report_ids"]

    asyncio.run(_run())


def test_potholes_far_apart_do_not_merge():
    """Verify that two potholes far apart (> 100 meters) along the same road are NOT merged."""
    async def _run():
        db = InMemoryDatabase()
        bus = SSEBus()
        embed_svc = MockEmbedService()

        # Pothole 1 at 17.4319, 78.4087
        state1 = {
            "report_id": "rep_pothole_near",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.ROAD_DAMAGE,
                combined_description="Pothole near Apollo Hospital Road 36",
                confidence=0.9,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.ROAD_DAMAGE,
                    damage_features=["pothole"],
                    hazard_indicators=["hazard"],
                    confidence=0.9,
                    raw_description="Pothole.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.4087, 17.4319]),
                address="Road No. 36",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                confidence=0.9,
                source="gps",
            ),
            "audit_events": [],
        }

        res1 = await deduplicator(state1, bus=bus, db=db, embed_service=embed_svc)
        assert res1["dedup_output"].action == "created"

        # Pothole 2 at 17.4350, 78.4120 (~480 meters away)
        dist = haversine(17.4319, 78.4087, 17.4350, 78.4120)
        assert dist > 100.0

        state2 = {
            "report_id": "rep_pothole_far",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.ROAD_DAMAGE,
                combined_description="Another pothole further down Road 36",
                confidence=0.9,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.ROAD_DAMAGE,
                    damage_features=["pothole"],
                    hazard_indicators=["hazard"],
                    confidence=0.9,
                    raw_description="Another pothole.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.4120, 17.4350]),
                address="Road No. 36",
                ward="Jubilee Hills",
                city="Hyderabad",
                country="India",
                confidence=0.9,
                source="gps",
            ),
            "audit_events": [],
        }

        res2 = await deduplicator(state2, bus=bus, db=db, embed_service=embed_svc)
        assert res2["dedup_output"].action == "created", "Potholes 480m apart must NOT merge"
        assert res2["dedup_output"].issue_id != res1["dedup_output"].issue_id

    asyncio.run(_run())


def test_water_leak_and_garbage_same_location_do_not_merge():
    """Verify that a water leak and garbage dump at the same location do NOT merge."""
    async def _run():
        db = InMemoryDatabase()
        bus = SSEBus()
        embed_svc = MockEmbedService()

        state1 = {
            "report_id": "rep_water_1",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.WATER_LEAK,
                combined_description="High-pressure potable water pipeline burst flooding the road in Madhapur",
                confidence=0.94,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.WATER_LEAK,
                    damage_features=["water_leakage", "water_main_break"],
                    hazard_indicators=["flooding_risk"],
                    confidence=0.94,
                    raw_description="Water pipe burst.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.3750, 17.4485]),
                address="Madhapur Main Road",
                ward="Madhapur",
                city="Hyderabad",
                country="India",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res1 = await deduplicator(state1, bus=bus, db=db, embed_service=embed_svc)
        assert res1["dedup_output"].action == "created"

        state2 = {
            "report_id": "rep_garbage_2",
            "perception_output": PerceptionOutput(
                detected_category=IssueCategory.GARBAGE,
                combined_description="Overflowing municipal garbage dumpster and open waste burning",
                confidence=0.92,
                model_used="test",
                visual=VisualObservation(
                    issue_type=IssueCategory.GARBAGE,
                    damage_features=["garbage_heap", "overflowing_waste"],
                    hazard_indicators=["health_hazard"],
                    confidence=0.92,
                    raw_description="Garbage dump overflowing.",
                ),
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(type="Point", coordinates=[78.3750, 17.4485]),
                address="Madhapur Main Road",
                ward="Madhapur",
                city="Hyderabad",
                country="India",
                confidence=0.95,
                source="gps",
            ),
            "audit_events": [],
        }

        res2 = await deduplicator(state2, bus=bus, db=db, embed_service=embed_svc)
        assert res2["dedup_output"].action == "created", "Water leak and garbage dump must not merge"
        assert res2["dedup_output"].issue_id != res1["dedup_output"].issue_id

    asyncio.run(_run())


def test_defect_family_detection_and_compatibility():
    """Unit test defect taxonomy extraction and disjoint checks."""
    fam_pothole = detect_defect_families("Deep crater pothole in asphalt", ["pothole"])
    assert "pothole" in fam_pothole
    assert "streetlight" not in fam_pothole

    fam_light = detect_defect_families("Series of streetlights dead with exposed 230v wire", ["exposed_wire"])
    assert "streetlight" in fam_light
    assert "pothole" not in fam_light

    assert not are_defect_families_compatible(fam_pothole, fam_light), "Pothole and streetlight must be incompatible"

    fam_pothole_2 = detect_defect_families("Large asphalt cavity on the avenue", ["pothole"])
    assert are_defect_families_compatible(fam_pothole, fam_pothole_2), "Two pothole reports must be compatible"

    # Test problem similarity
    sim_same = compute_problem_similarity(
        "Deep crater pothole in asphalt road",
        "Large dangerous pothole with asphalt subsidence"
    )
    assert sim_same > 0.2

    sim_diff = compute_problem_similarity(
        "Deep crater pothole in asphalt road",
        "Broken streetlight luminaire exposed live wire"
    )
    assert sim_diff == 0.0
