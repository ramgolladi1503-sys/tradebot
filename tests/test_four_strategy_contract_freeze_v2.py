from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


BUNDLE_PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v2.json"
SIDECAR_PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v2.json.sha256"

EXPECTED_SOURCE_HASHES = {
    "config/strategy_inventory.yml": "d14d28fea0950fe1a13eb2d975c12f9a1b0c789f21ae239fc7edea824b81c717",
    "core/movement_contract.py": "3e0025abfb1266a65617082cc09293e084392aa6c6f29d7d18c0381e9f765f95",
    "core/strategy_parameter_profiles.py": "c40787d570956da03f814dbb6a9fd6bb528c840c42c959ddb544e16e3a861407",
    "strategies/movement/opening_range_breakout.py": "4f7dad9c0ba5749129b8645b9c76ba4543cc39087f18ebfbfb5063c09adfda0e",
    "strategies/movement/trend_pullback.py": "36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1",
    "strategies/movement/compression_breakout.py": "c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7",
    "strategies/movement/vwap_reclaim.py": "ba71230688fd0728efc62fecb9a934a32dd99819e39173f05e7ab8668e06b259",
}


def _load_bundle() -> dict[str, object]:
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(bundle: dict[str, object]) -> bytes:
    return (json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def test_v2_bundle_is_canonical_and_supersedes_v1_without_overwriting_it() -> None:
    bundle = _load_bundle()
    raw = BUNDLE_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    assert bundle["bundle_version"] == 2
    assert bundle["bundle_id"] == "four_strategy_contract_bundle_v2"
    assert bundle["supersedes"] == "four_strategy_contract_bundle_v1"
    assert bundle["bundle_sha256_sidecar"] == "docs/agent_reviews/four_strategy_contract_bundle_v2.json.sha256"
    assert raw == _canonical_bytes(bundle)
    assert SIDECAR_PATH.read_text(encoding="utf-8").strip() == f"{digest}  {BUNDLE_PATH.name}"
    assert _hash_file(Path("docs/agent_reviews/four_strategy_contract_bundle_v1.json")) == (
        "8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2"
    )


def test_v2_bundle_source_hashes_match_current_repaired_repo_truth() -> None:
    bundle = _load_bundle()
    source_files = {item["path"]: item["sha256"] for item in bundle["source_files"]}

    assert source_files == EXPECTED_SOURCE_HASHES
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        assert _hash_file(Path(relative_path)) == expected_hash


def test_v2_bundle_records_only_approved_orb_and_vwap_fingerprint_changes() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    opening = strategies["opening_range_retest_v1"]
    assert opening["frozen_output_vector"] == {
        "strategy_id": "opening_range_retest_v1",
        "direction": "BUY_CALL",
        "status": "RAW_CANDIDATE",
        "raw_score": pytest.approx(0.54),
        "entry_trigger": "opening_range_breakout_retest_hold",
        "invalid_if": "price_returns_inside_opening_range",
        "rank_reason": "opening range breakout retest held",
    }
    assert opening["approved_repair_metadata"] == {
        "repair_id": "orb_retest_distance_source_v3",
        "retest_distance_pct_source": "retest_bar.close",
        "breakout_distance_pct_source": "breakout_bar.close",
        "temporal_candidate_presence_changed": False,
        "thresholds_changed": False,
    }

    vwap = strategies["vwap_reclaim_rejection_v1"]
    assert vwap["frozen_output_vector"] == {
        "strategy_id": "vwap_reclaim_rejection_v1",
        "direction": "BUY_CALL",
        "status": "RAW_CANDIDATE",
        "raw_score": pytest.approx(0.392377),
        "entry_trigger": "confirmed_vwap_reclaim_hold",
        "invalid_if": "price_crosses_back_through_vwap",
        "rank_reason": "confirmed VWAP reclaim and hold in a non-chop regime",
    }
    assert vwap["approved_repair_metadata"] == {
        "repair_id": "vwap_reclaim_hold_identity_v3",
        "compatibility_strategy_id": "vwap_reclaim_rejection_v1",
        "implemented_pattern": "VWAP_RECLAIM_HOLD",
        "rejection_predicate_added": False,
        "predicate_changed": False,
        "score_changed": False,
        "thresholds_changed": False,
    }

    assert strategies["trend_pullback_v1"]["frozen_output_vector"]["raw_score"] == pytest.approx(0.648584)
    assert strategies["compression_breakout_v1"]["frozen_output_vector"]["raw_score"] == pytest.approx(0.470676)
