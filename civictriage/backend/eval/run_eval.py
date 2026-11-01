"""
eval/run_eval.py
================
Comprehensive evaluation harness for CivicTriage pipeline (Task A30).

Measures:
  1. Category accuracy     — does perceived category match ground truth?
  2. Severity agreement    — does computed severity_tier match ground truth?
  3. Routing accuracy      — does primary_authority match expected authority?
  4. Legal citation rate   — are statutory citations present and non-empty?

Usage:
    cd backend/
    python eval/run_eval.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.models.schemas import IssueCategory, SeverityFeaturesFromLLM, SeverityTier
from app.agents.nodes.severity_scorer import _compute_rubric, CATEGORY_TO_HAZARD

logging.basicConfig(level=logging.WARNING)


def _load_golden_cases(golden_dir: Path) -> list[dict]:
    """Find and load all base golden input JSON files."""
    cases = []
    for f in sorted(golden_dir.glob("golden_*.json")):
        if any(f.name.endswith(suffix) for suffix in (
            "_intake.json", "_perceive.json", "_router.json", "_severity.json", "_embeddings_cache.json"
        )):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "report_id" in data:
                cases.append(data)
        except Exception as exc:
            print(f"Error loading {f.name}: {exc}")
    return cases


def _evaluate_case(case: dict, golden_dir: Path) -> dict:
    report_id = case["report_id"]
    expected = case.get("expected", {})

    # 1. Perception
    perceive_file = golden_dir / f"{report_id}_perceive.json"
    assert perceive_file.exists(), f"Missing perceive cache: {perceive_file}"
    perceive_data = json.loads(perceive_file.read_text(encoding="utf-8"))
    perceived_category = perceive_data.get("issue_type")
    cat_match = (perceived_category == expected.get("category"))

    # 2. Deterministic Severity Scoring
    hazard_indicators = perceive_data.get("hazard_indicators", [])
    damage_features = perceive_data.get("damage_features", [])

    # Map category to hazard type
    hazard_type = CATEGORY_TO_HAZARD.get(perceived_category, "default")
    has_structural = any("collapse" in h.lower() or "subsidence" in h.lower() for h in damage_features + hazard_indicators)
    has_fire = any("electric" in h.lower() or "wire" in h.lower() or "fire" in h.lower() for h in hazard_indicators)

    llm_features = SeverityFeaturesFromLLM(
        hazard_type=hazard_type,
        structural_risk=has_structural,
        fire_risk=has_fire,
        estimated_area_sqm=perceive_data.get("estimated_area_sqm"),
        hazard_indicators=hazard_indicators,
        damage_features=damage_features,
        confidence=perceive_data.get("confidence", 0.9),
    )

    # Corridors near hospital/school in Hyderabad have nearby POIs within 200m
    poi_dist = 180.0 if "Hospital" in str(damage_features) or "school" in str(hazard_indicators) else 250.0

    breakdown = _compute_rubric(
        features=llm_features,
        road_class="primary",
        nearest_poi_distance_meters=poi_dist,
        cluster_size=1,
        issue_age_hours=2.0,
    )
    computed_tier = breakdown.tier.value
    expected_tier = expected.get("severity_tier")
    sev_match = (computed_tier == expected_tier)

    # 3. Authority Routing
    router_file = golden_dir / f"{report_id}_router.json"
    assert router_file.exists(), f"Missing router cache: {router_file}"
    router_data = json.loads(router_file.read_text(encoding="utf-8"))
    primary_auth = router_data.get("primary_authority", {})
    actual_auth_name = primary_auth.get("authority_name", "")
    expected_auth_name = expected.get("authority_name", "")

    # Fuzzy match by authority prefix or key acronym
    auth_match = (
        actual_auth_name == expected_auth_name
        or actual_auth_name.split("—")[0].strip() == expected_auth_name.split("—")[0].strip()
    )

    citations = router_data.get("citation_chunk_ids", [])
    citations_valid = len(citations) > 0

    return {
        "report_id": report_id,
        "category": {
            "expected": expected.get("category"),
            "actual": perceived_category,
            "match": cat_match,
        },
        "severity": {
            "expected": expected_tier,
            "actual": computed_tier,
            "score": breakdown.total,
            "match": sev_match,
        },
        "routing": {
            "expected": expected_auth_name,
            "actual": actual_auth_name,
            "match": auth_match,
            "confidence": router_data.get("confidence", 0.0),
            "citations": citations,
            "citations_valid": citations_valid,
        },
    }


def run_eval() -> None:
    golden_dir = Path(__file__).resolve().parent / "golden_inputs"
    cases = _load_golden_cases(golden_dir)

    print("=" * 82)
    print("                 CIVICTRIAGE AGENT EVALUATION BENCHMARK (A30)")
    print("=" * 82)
    print(f"Total labeled golden test cases evaluated: {len(cases)}\n")

    results = []
    for c in cases:
        res = _evaluate_case(c, golden_dir)
        results.append(res)

    # Print Detailed Table
    print(f"{'Report ID':<12} | {'Category (Exp/Act)':<24} | {'Severity':<16} | {'Authority Routing':<16} | {'Citations':<10}")
    print("-" * 82)

    cat_correct = 0
    sev_correct = 0
    route_correct = 0
    citations_present = 0

    for r in results:
        rid = r["report_id"]
        cat_e = r["category"]["expected"]
        cat_a = r["category"]["actual"]
        cat_ok = "[OK]" if r["category"]["match"] else "[FAIL]"
        if r["category"]["match"]:
            cat_correct += 1

        sev_e = r["severity"]["expected"]
        sev_a = r["severity"]["actual"]
        sev_score = r["severity"]["score"]
        sev_ok = "[OK]" if r["severity"]["match"] else "[FAIL]"
        if r["severity"]["match"]:
            sev_correct += 1

        route_ok = "[OK]" if r["routing"]["match"] else "[FAIL]"
        if r["routing"]["match"]:
            route_correct += 1

        cit_ok = "[OK]" if r["routing"]["citations_valid"] else "[NONE]"
        if r["routing"]["citations_valid"]:
            citations_present += 1

        cat_str = f"{cat_ok} {cat_a}"
        sev_str = f"{sev_ok} {sev_a} ({sev_score:.1f})"
        route_str = f"{route_ok} {r['routing']['actual'][:14]}..."
        cit_str = f"{cit_ok} ({len(r['routing']['citations'])})"

        print(f"{rid:<12} | {cat_str:<24} | {sev_str:<16} | {route_str:<20} | {cit_str:<10}")

    total = len(results)
    cat_acc = (cat_correct / total) * 100 if total else 0
    sev_acc = (sev_correct / total) * 100 if total else 0
    route_acc = (route_correct / total) * 100 if total else 0
    cit_acc = (citations_present / total) * 100 if total else 0

    print("=" * 82)
    print("SUMMARY PERFORMANCE METRICS:")
    print(f"  * Category Classification Accuracy:   {cat_acc:5.1f}%  ({cat_correct}/{total})")
    print(f"  * Severity Tier Agreement (Hybrid):   {sev_acc:5.1f}%  ({sev_correct}/{total})")
    print(f"  * Jurisdictional Routing Accuracy:     {route_acc:5.1f}%  ({route_correct}/{total})")
    print(f"  * Legal/Charter Citation Rate:        {cit_acc:5.1f}%  ({citations_present}/{total})")
    print("=" * 82)


if __name__ == "__main__":
    run_eval()
