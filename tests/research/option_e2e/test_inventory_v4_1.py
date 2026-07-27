from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.option_e2e_recertification_v4.inventory_v4_1 import build_inventory_v4_1


REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPO_ROOT / "research" / "option_e2e_recertification_v4" / "inventory_v4_1" / "historical_strategy_inventory_v4_1.json"
MANIFEST_PATH = REPO_ROOT / "research" / "option_e2e_recertification_v4" / "inventory_v4_1" / "manifest_v4_1.json"
REPORT_PATH = REPO_ROOT / "docs" / "agent_reviews" / "option_e2e_historical_inventory_v4_1.md"


def _load_inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def test_inventory_separates_non_strategy_entities() -> None:
    inventory = _load_inventory()
    entities = {entry["id"]: entry for entry in inventory["entities"]}

    for strategy_id in ["POSITION_SIZER", "RISK_MANAGER", "TRADE_BUILDER", "TEST_STRAT"]:
        assert entities[strategy_id]["entity_type"] == "non_strategy_support"
        assert entities[strategy_id]["counted_as_strategy"] is False

    assert entities["COMPRESSION_BREAKOUT"]["counted_as_strategy"] is True
    assert entities["VWAP_RECLAIM"]["counted_as_strategy"] is True
    assert entities["ZERO_HERO"]["counted_as_strategy"] is True


def test_required_prompt_families_have_explicit_inventory_slots() -> None:
    inventory = _load_inventory()
    expected = set(build_inventory_v4_1.FAMILY_PATTERNS)

    assert set(inventory["family_evidence"]) == expected
    assert inventory["family_evidence"]["ORB_RETEST_DRIVE"]
    assert inventory["family_evidence"]["VWAP_VARIANTS"]
    assert inventory["family_evidence"]["MRE"]
    assert inventory["family_evidence"]["CANDIDATE_INTENT"]


def test_inventory_is_fail_closed_offline_metadata_only() -> None:
    inventory = _load_inventory()

    assert inventory["mode"] == "OFFLINE_INVENTORY_NO_ECONOMIC_REPLAY"
    assert inventory["read_only"] is True
    assert inventory["is_order_action"] is False
    assert inventory["broker_api_called"] is False
    assert inventory["allowed_for_live_execution"] is False
    assert inventory["append"] is False


def test_manifest_hashes_match_generated_artifacts() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    inventory_hash = hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest()
    report_hash = hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest()

    assert manifest["artifacts"]["historical_strategy_inventory_v4_1.json"] == inventory_hash
    assert manifest["artifacts"]["docs/agent_reviews/option_e2e_historical_inventory_v4_1.md"] == report_hash

