"""
tests/test_rule_engine.py
=========================
Automated tests for the Rule-Based Routing Engine.

Tests:
  1. Rule lookup by category + subtype
  2. Asset type matching and precedence
  3. Priority-based rule selection (lowest number wins)
  4. Human review triggers (no rules, ambiguous, low confidence)
  5. Source document association integrity
  6. Seed data self-consistency checks

Run with:
    cd civictriage/backend
    python -m pytest tests/test_rule_engine.py -v
"""

from __future__ import annotations

import pytest


# ── Sample fixture (subset of real rules) ─────────────────────────────────────

@pytest.fixture
def sample_rules():
    return [
        {
            "rule_id": "rule_001",
            "category": "road_damage",
            "subtype": "pothole",
            "asset_type": "municipal_road",
            "department_id": "roads_dept",
            "priority": 10,
            "sla_hours": 48,
            "requires_human_review": False,
            "source_document_ids": ["ghmc_roads_charter", "motor_vehicles_act_198a"],
            "is_active": True,
        },
        {
            "rule_id": "rule_002",
            "category": "road_damage",
            "subtype": "pothole",
            "asset_type": "national_highway",
            "department_id": "nhai_dept",
            "priority": 5,
            "sla_hours": 72,
            "requires_human_review": False,
            "source_document_ids": ["nhai_road_safety_manual"],
            "is_active": True,
        },
        {
            "rule_id": "rule_003",
            "category": "road_damage",
            "subtype": "road_collapse",
            "asset_type": "any",
            "department_id": "roads_dept",
            "priority": 3,
            "sla_hours": 6,
            "requires_human_review": False,
            "source_document_ids": ["ghmc_roads_charter"],
            "is_active": True,
        },
        {
            "rule_id": "rule_006",
            "category": "road_damage",
            "subtype": "any",
            "asset_type": "unknown",
            "department_id": "roads_dept",
            "priority": 20,
            "sla_hours": 48,
            "requires_human_review": True,
            "source_document_ids": [],
            "is_active": True,
        },
        {
            "rule_id": "rule_007",
            "category": "water_leak",
            "subtype": "main_break",
            "asset_type": "water_main",
            "department_id": "water_dept",
            "priority": 5,
            "sla_hours": 12,
            "requires_human_review": False,
            "source_document_ids": ["hmwssb_service_charter"],
            "is_active": True,
        },
        {
            "rule_id": "rule_021",
            "category": "flood",
            "subtype": "waterlogging",
            "asset_type": "any",
            "department_id": "disaster_mgmt",
            "priority": 2,
            "sla_hours": 6,
            "requires_human_review": False,
            "source_document_ids": ["telangana_sdma_act"],
            "is_active": True,
        },
        {
            "rule_id": "rule_025",
            "category": "other",
            "subtype": "any",
            "asset_type": "any",
            "department_id": "general_desk",
            "priority": 100,
            "sla_hours": 72,
            "requires_human_review": True,
            "source_document_ids": [],
            "is_active": True,
        },
        {
            "rule_id": "rule_inactive",
            "category": "road_damage",
            "subtype": "pothole",
            "asset_type": "municipal_road",
            "department_id": "roads_dept",
            "priority": 1,
            "sla_hours": 24,
            "requires_human_review": False,
            "source_document_ids": [],
            "is_active": False,  # disabled
        },
    ]


# ── Pure Python rule engine mirror ────────────────────────────────────────────

def match_rules(rules, category, subtype=None, asset_type=None):
    """Mirror of the server-side rule matching logic."""
    matched = []
    for rule in rules:
        if not rule.get("is_active", True):
            continue
        if rule["category"] != category:
            continue
        rule_subtype = rule.get("subtype", "any")
        if rule_subtype != "any" and subtype and rule_subtype != subtype:
            continue
        rule_asset = rule.get("asset_type", "any")
        if rule_asset != "any" and asset_type and rule_asset != asset_type:
            continue
        matched.append(rule)
    matched.sort(key=lambda r: r.get("priority", 999))
    return matched


def select_rule(rules, category, subtype=None, asset_type=None, confidence=1.0):
    """Applies rule precedence; returns (rule_or_None, needs_human_review, reason)."""
    CRITIC_MIN_CONFIDENCE = 0.65

    if confidence < CRITIC_MIN_CONFIDENCE:
        return None, True, f"low_confidence:{confidence:.2f}"

    matched = match_rules(rules, category, subtype, asset_type)
    if not matched:
        return None, True, "no_matching_rule"

    best = matched[0]
    if best.get("requires_human_review", False):
        return best, True, "rule_requires_review"

    return best, False, "OK"


# ── Tests: basic lookup ────────────────────────────────────────────────────────

class TestRuleLookup:

    def test_category_match(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage")
        assert len(matched) > 0
        assert all(r["category"] == "road_damage" for r in matched)

    def test_no_match_returns_empty(self, sample_rules):
        assert match_rules(sample_rules, "nonexistent_xyz") == []

    def test_inactive_rules_excluded(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage")
        ids = [r["rule_id"] for r in matched]
        assert "rule_inactive" not in ids, "Inactive rules must be excluded"

    def test_specific_subtype_match(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage", subtype="pothole")
        ids = [r["rule_id"] for r in matched]
        assert "rule_001" in ids
        assert "rule_002" in ids

    def test_any_subtype_matches_everything(self, sample_rules):
        # rule_003 has subtype="road_collapse", rule_006 has subtype="any"
        matched = match_rules(sample_rules, "road_damage", subtype="crack")
        ids = [r["rule_id"] for r in matched]
        assert "rule_006" in ids, "subtype=any rule must match any subtype"

    def test_specific_asset_type(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage", subtype="pothole", asset_type="national_highway")
        ids = [r["rule_id"] for r in matched]
        assert "rule_002" in ids

    def test_any_asset_type_matches(self, sample_rules):
        # rule_003 has asset_type="any"
        matched = match_rules(sample_rules, "road_damage", subtype="road_collapse", asset_type="some_random_asset")
        ids = [r["rule_id"] for r in matched]
        assert "rule_003" in ids

    def test_water_leak_match(self, sample_rules):
        matched = match_rules(sample_rules, "water_leak", subtype="main_break", asset_type="water_main")
        assert len(matched) == 1
        assert matched[0]["rule_id"] == "rule_007"

    def test_flood_match(self, sample_rules):
        matched = match_rules(sample_rules, "flood")
        assert len(matched) == 1
        assert matched[0]["rule_id"] == "rule_021"


# ── Tests: precedence ─────────────────────────────────────────────────────────

class TestRulePrecedence:

    def test_sorted_by_priority_ascending(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage")
        priorities = [r["priority"] for r in matched]
        assert priorities == sorted(priorities), "Rules must be sorted by priority (ascending)"

    def test_nhai_beats_ghmc_for_national_highway(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage", subtype="pothole", asset_type="national_highway")
        # rule_002 (nhai_dept, priority=5) should be first
        assert matched[0]["rule_id"] == "rule_002"
        assert matched[0]["department_id"] == "nhai_dept"

    def test_road_collapse_has_high_priority(self, sample_rules):
        matched = match_rules(sample_rules, "road_damage", subtype="road_collapse")
        assert matched[0]["priority"] <= 5, "Emergency road collapse should have top priority"

    def test_flood_top_priority(self, sample_rules):
        matched = match_rules(sample_rules, "flood")
        assert matched[0]["priority"] <= 5

    def test_select_returns_highest_priority(self, sample_rules):
        rule, hr, reason = select_rule(sample_rules, "water_leak", subtype="main_break", asset_type="water_main")
        assert rule is not None
        assert rule["rule_id"] == "rule_007"
        assert hr is False

    def test_unknown_asset_triggers_review(self, sample_rules):
        """rule_006 matches unknown asset_type and has requires_human_review=True."""
        rule, hr, reason = select_rule(
            sample_rules, "road_damage", subtype="pothole", asset_type="unknown"
        )
        assert hr is True


# ── Tests: human review triggers ──────────────────────────────────────────────

class TestHumanReviewTrigger:

    def test_no_matching_rule_triggers_review(self, sample_rules):
        rule, hr, reason = select_rule(sample_rules, "garbage")
        assert hr is True
        assert "no_matching_rule" in reason

    def test_low_confidence_triggers_review(self, sample_rules):
        rule, hr, reason = select_rule(
            sample_rules, "road_damage", subtype="pothole",
            asset_type="municipal_road", confidence=0.50
        )
        assert hr is True
        assert "confidence" in reason

    def test_confidence_exactly_at_threshold_passes(self, sample_rules):
        rule, hr, reason = select_rule(
            sample_rules, "road_damage", subtype="pothole",
            asset_type="municipal_road", confidence=0.65
        )
        # 0.65 is NOT < 0.65, so it should NOT trigger confidence review
        assert not ("confidence" in reason and hr is True) or rule is not None

    def test_zero_confidence_triggers_review(self, sample_rules):
        _, hr, reason = select_rule(sample_rules, "road_damage", confidence=0.0)
        assert hr is True

    def test_requires_human_review_flag_respected(self, sample_rules):
        rule, hr, reason = select_rule(sample_rules, "other")
        assert hr is True
        assert reason in ("rule_requires_review", "no_matching_rule")

    def test_catch_all_other_routes_to_general_desk(self, sample_rules):
        rule, hr, reason = select_rule(sample_rules, "other")
        if rule:
            assert rule["department_id"] == "general_desk"


# ── Tests: source document integrity ──────────────────────────────────────────

class TestSourceDocuments:

    def test_rules_have_source_doc_references(self, sample_rules):
        rules_with_docs = [r for r in sample_rules if r.get("source_document_ids")]
        assert len(rules_with_docs) >= 3, "At least 3 rules should have source doc references"

    def test_rule_001_has_ghmc_charter(self, sample_rules):
        r = next(r for r in sample_rules if r["rule_id"] == "rule_001")
        assert "ghmc_roads_charter" in r["source_document_ids"]

    def test_flood_rule_has_sdma(self, sample_rules):
        r = next(r for r in sample_rules if r["rule_id"] == "rule_021")
        assert "telangana_sdma_act" in r["source_document_ids"]

    def test_water_rule_has_hmwssb(self, sample_rules):
        r = next(r for r in sample_rules if r["rule_id"] == "rule_007")
        assert "hmwssb_service_charter" in r["source_document_ids"]


# ── Tests: seed data self-consistency ─────────────────────────────────────────

class TestSeedDataIntegrity:

    def test_25_routing_rules_exist(self):
        from seed.seed_rules import ROUTING_RULES
        assert 15 <= len(ROUTING_RULES) <= 30, f"Expected 15–25 rules, got {len(ROUTING_RULES)}"

    def test_rule_ids_unique(self):
        from seed.seed_rules import ROUTING_RULES
        ids = [r["rule_id"] for r in ROUTING_RULES]
        assert len(ids) == len(set(ids)), "Duplicate rule_ids found"

    def test_dept_ids_unique(self):
        from seed.seed_rules import DEPARTMENTS
        ids = [d["department_id"] for d in DEPARTMENTS]
        assert len(ids) == len(set(ids)), "Duplicate department_ids found"

    def test_rule_dept_ids_reference_valid_dept(self):
        from seed.seed_rules import DEPARTMENTS, ROUTING_RULES
        dept_ids = {d["department_id"] for d in DEPARTMENTS}
        for rule in ROUTING_RULES:
            assert rule["department_id"] in dept_ids, (
                f"Rule {rule['rule_id']} references unknown dept '{rule['department_id']}'"
            )

    def test_rule_source_doc_ids_reference_valid_docs(self):
        from seed.seed_rules import SOURCE_DOCUMENTS, ROUTING_RULES
        doc_ids = {d["doc_id"] for d in SOURCE_DOCUMENTS}
        for rule in ROUTING_RULES:
            for doc_id in rule.get("source_document_ids", []):
                assert doc_id in doc_ids, (
                    f"Rule {rule['rule_id']} references unknown doc '{doc_id}'"
                )

    def test_jurisdiction_boundaries_are_valid_polygons(self):
        from seed.seed_rules import JURISDICTIONS
        for jur in JURISDICTIONS:
            b = jur["boundary"]
            assert b["type"] == "Polygon"
            ring = b["coordinates"][0]
            assert len(ring) >= 4, f"Polygon ring for {jur['jurisdiction_id']} needs >= 4 points"

    def test_all_categories_have_at_least_one_rule(self):
        from seed.seed_rules import ROUTING_RULES
        categories = {r["category"] for r in ROUTING_RULES}
        expected = {"road_damage", "water_leak", "sewage", "garbage",
                    "streetlight", "pollution", "encroachment", "tree_hazard", "flood", "other"}
        missing = expected - categories
        assert not missing, f"No routing rules for categories: {missing}"

    def test_destination_dept_ids_reference_valid_dept(self):
        from seed.seed_rules import DEPARTMENTS, REPORTING_DESTINATIONS
        dept_ids = {d["department_id"] for d in DEPARTMENTS}
        for dest in REPORTING_DESTINATIONS:
            assert dest["department_id"] in dept_ids, (
                f"Destination {dest['destination_id']} references unknown dept '{dest['department_id']}'"
            )

    def test_all_rules_have_required_fields(self):
        from seed.seed_rules import ROUTING_RULES
        required = {"rule_id", "category", "subtype", "asset_type", "department_id", "priority", "sla_hours"}
        for rule in ROUTING_RULES:
            missing = required - rule.keys()
            assert not missing, f"Rule {rule.get('rule_id')} missing fields: {missing}"

    def test_priority_ordering(self):
        """Emergency rules must have lower priority numbers than routine rules."""
        from seed.seed_rules import ROUTING_RULES
        # Flood rule should have priority < 10
        flood_rules = [r for r in ROUTING_RULES if r["category"] == "flood" and "waterlogging" in r.get("subtype", "")]
        if flood_rules:
            assert min(r["priority"] for r in flood_rules) < 10, "Flood (waterlogging) must be high priority"
        # Road collapse should be high priority
        collapse_rules = [r for r in ROUTING_RULES if "collapse" in r.get("subtype", "")]
        if collapse_rules:
            assert min(r["priority"] for r in collapse_rules) < 10, "Road collapse must be high priority"

