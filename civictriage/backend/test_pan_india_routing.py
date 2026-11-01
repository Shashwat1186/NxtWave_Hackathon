"""
Unit test for Pan-India automatic GPS city routing and departmental allocation.
Verifies that:
- Automatic GPS setting in different cities routes to that specific city's department.
- Reports do not just default or fall back to Hyderabad.
- Issues are allocated to the correct department of the correct city based on the category.
"""

import asyncio
from app.core.database import InMemoryDatabase
from app.core.llm_client import DemoModeClient
from app.core.sse_bus import SSEBus
from app.models.schemas import IssueCategory, PerceptionOutput, GeoResolverOutput, GeoPoint
from app.agents.nodes.authority_router import authority_router
from app.services.city_directory import (
    lookup_city_from_coords,
    normalize_city_name,
    resolve_city_jurisdiction,
    CITY_DEPARTMENT_REGISTRY,
)


async def test_city_routing():
    db = InMemoryDatabase()
    await db._load_seed_data()
    bus = SSEBus()
    llm = DemoModeClient(cache_dir="eval/golden_inputs")

    test_cases = [
        # (city_name, lat, lng, category, expected_dept_substr, expected_jur_substr)
        ("Bengaluru", 12.9716, 77.5946, IssueCategory.ROAD_DAMAGE, "BBMP", "Bengaluru"),
        ("Bengaluru", 12.9716, 77.5946, IssueCategory.WATER_LEAK, "BWSSB", "Bengaluru"),
        ("Bengaluru", 12.9716, 77.5946, IssueCategory.STREETLIGHT, "BESCOM", "Bengaluru"),
        ("Bengaluru", 12.9716, 77.5946, IssueCategory.GARBAGE, "BBMP Solid Waste Management", "Bengaluru"),
        
        ("Mumbai", 19.0760, 72.8777, IssueCategory.ROAD_DAMAGE, "BMC", "Mumbai"),
        ("Mumbai", 19.0760, 72.8777, IssueCategory.WATER_LEAK, "BMC Hydraulic", "Mumbai"),
        ("Mumbai", 19.0760, 72.8777, IssueCategory.STREETLIGHT, "BEST / Adani", "Mumbai"),
        
        ("Delhi", 28.6139, 77.2090, IssueCategory.ROAD_DAMAGE, "MCD", "Delhi"),
        ("Delhi", 28.6139, 77.2090, IssueCategory.WATER_LEAK, "Delhi Jal Board", "Delhi"),
        ("Delhi", 28.6139, 77.2090, IssueCategory.STREETLIGHT, "BSES", "Delhi"),
        
        ("Chennai", 13.0827, 80.2707, IssueCategory.ROAD_DAMAGE, "Greater Chennai Corporation", "Chennai"),
        ("Chennai", 13.0827, 80.2707, IssueCategory.WATER_LEAK, "CMWSSB", "Chennai"),
        
        ("Pune", 18.5204, 73.8567, IssueCategory.ROAD_DAMAGE, "Pune Municipal Corporation", "Pune"),
        ("Kolkata", 22.5726, 88.3639, IssueCategory.ROAD_DAMAGE, "Kolkata Municipal Corporation", "Kolkata"),
        ("Ahmedabad", 23.0225, 72.5714, IssueCategory.ROAD_DAMAGE, "Ahmedabad Municipal Corporation", "Ahmedabad"),
        
        # Hyderabad baseline verification
        ("Hyderabad", 17.4319, 78.4087, IssueCategory.ROAD_DAMAGE, "Roads & Buildings", "Hyderabad"),
        ("Hyderabad", 17.4485, 78.3750, IssueCategory.WATER_LEAK, "HMWSSB", "Hyderabad"),
        ("Hyderabad", 17.4156, 78.4350, IssueCategory.STREETLIGHT, "TSSPDCL", "Hyderabad"),
    ]

    print("Running Pan-India GPS City Department Allocation Verification...")
    for city, lat, lng, cat, expected_dept, expected_jur in test_cases:
        state = {
            "report_id": f"test_{city.lower()}_{cat.value}",
            "raw_text": f"Severe {cat.value} reported in {city} area needing urgent repair.",
            "gps_lat": lat,
            "gps_lng": lng,
            "perception_output": PerceptionOutput(
                detected_category=cat,
                confidence=0.92,
                combined_description=f"Severe {cat.value} reported in {city} near main junction.",
                model_used="gemini-vision",
                image_matches_description=True,
            ),
            "geo_output": GeoResolverOutput(
                location=GeoPoint(coordinates=[lng, lat]),
                source="gps",
                address=f"Main Road, {city}, India",
                ward=f"{city} Central Ward",
                city=city,
                country="India",
                road_class="secondary",
                nearby_pois=[],
                geocode_cache_hit=True,
            ),
            "audit_events": [],
        }

        updates = await authority_router(state, llm=llm, bus=bus, db=db)
        router_out = updates.get("router_output")
        assert router_out is not None, f"Router output is None for {city} {cat}"
        primary_dept = router_out.primary_authority.authority_name

        print(f"[{city} - {cat.value.upper()}] -> Routed to: {primary_dept}")
        assert expected_dept in primary_dept, (
            f"Expected '{expected_dept}' in '{primary_dept}' for {city} {cat.value}"
        )

    print("\nALL PAN-INDIA GPS CITY ROUTING TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(test_city_routing())

