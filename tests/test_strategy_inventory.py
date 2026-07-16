import json
from pathlib import Path


INVENTORY_PATH = Path(__file__).parents[1] / "config" / "strategy_inventory.yml"
ALLOWED_STATUSES = {
    "UNVERIFIED",
    "PARTIAL_DETECTOR",
    "CONFORMANCE_PASSED",
    "RESEARCH_REJECTED",
    "RESEARCH_SURVIVOR",
    "OPTION_VALIDATED",
    "SHADOW_VALIDATED",
    "PROMOTED",
}
REQUIRED_ITEM_FIELDS = {
    "id",
    "role",
    "status",
    "implementation_claim",
    "validation_level",
    "execution_eligible",
    "reason",
}


def _load_inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def test_inventory_is_read_only_and_globally_ineligible_for_live_execution():
    inventory = _load_inventory()

    assert inventory["schema_version"] == 1
    assert inventory["read_only"] is True
    assert inventory["is_order_action"] is False
    assert inventory["broker_api_called"] is False
    assert inventory["allowed_for_live_execution"] is False
    assert inventory["append"] is False


def test_inventory_has_unique_ids_and_explicit_aliases():
    strategies = _load_inventory()["strategies"]
    ids = [item["id"] for item in strategies]
    aliases = [alias for item in strategies for alias in item.get("aliases", [])]

    assert len(ids) == len(set(ids))
    assert len(aliases) == len(set(aliases))
    assert set(ids).isdisjoint(aliases)


def test_inventory_classifies_ten_generators_one_confirmation_and_one_safety_layer():
    strategies = _load_inventory()["strategies"]
    roles = [item["role"] for item in strategies]

    assert roles.count("candidate_generator") == 10
    assert roles.count("option_confirmation") == 1
    assert roles.count("safety_suppression") == 1
    assert len(strategies) == 12


def test_every_item_is_complete_unpromoted_and_execution_ineligible():
    for item in _load_inventory()["strategies"]:
        assert REQUIRED_ITEM_FIELDS <= item.keys()
        assert item["status"] in ALLOWED_STATUSES
        assert item["status"] not in {
            "CONFORMANCE_PASSED",
            "RESEARCH_SURVIVOR",
            "OPTION_VALIDATED",
            "SHADOW_VALIDATED",
            "PROMOTED",
        }
        assert item["execution_eligible"] is False
        assert item["reason"].strip()


def test_required_generators_are_quarantined_fail_closed():
    by_id = {item["id"]: item for item in _load_inventory()["strategies"]}

    assert {
        "TREND_PULLBACK",
        "OPENING_RANGE_RETEST",
        "EXHAUSTION_REVERSAL",
    } == {
        strategy_id
        for strategy_id, item in by_id.items()
        if item["validation_level"] == "quarantined"
    }


def test_truthful_names_do_not_claim_unproven_event_or_option_flow_evidence():
    by_id = {item["id"]: item for item in _load_inventory()["strategies"]}

    volatility = by_id["DIRECTIONAL_VOLATILITY_EXPANSION"]
    assert volatility["aliases"] == ["EVENT_VOLATILITY_EXPANSION"]
    assert "event" not in volatility["implementation_claim"]

    option_confirmation = by_id["OPTION_QUOTE_CONFIRMATION"]
    assert option_confirmation["aliases"] == ["OPTION_PRESSURE"]
    assert option_confirmation["role"] == "option_confirmation"


def test_exhaustion_claim_is_risk_not_confirmed_reversal():
    by_id = {item["id"]: item for item in _load_inventory()["strategies"]}

    assert by_id["EXHAUSTION_REVERSAL"]["implementation_claim"] == "exhaustion_risk"
