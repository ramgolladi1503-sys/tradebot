from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


BUNDLE_PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_reviews" / "four_strategy_contract_bundle.json"
EXPECTED_SOURCE_HASHES = {
    "config/strategy_inventory.yml": "d14d28fea0950fe1a13eb2d975c12f9a1b0c789f21ae239fc7edea824b81c717",
    "core/movement_contract.py": "3e0025abfb1266a65617082cc09293e084392aa6c6f29d7d18c0381e9f765f95",
    "core/strategy_parameter_profiles.py": "c40787d570956da03f814dbb6a9fd6bb528c840c42c959ddb544e16e3a861407",
    "strategies/movement/opening_range_breakout.py": "06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e",
    "strategies/movement/trend_pullback.py": "36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1",
    "strategies/movement/compression_breakout.py": "c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7",
    "strategies/movement/vwap_reclaim.py": "7a30df420d2b70b4533c96e07bcccf784fbfe9e28e504cc2af7ff0aaa89566fc",
}
EXPECTED_STRATEGIES = {
    "opening_range_retest_v1": {
        "inventory_id": "OPENING_RANGE_RETEST",
        "movement_type": "OPENING_RANGE_RETEST",
        "role": "candidate_generator",
        "validation_level": "quarantined",
        "contract_version": "opening_range_retest_temporal_v1",
        "fingerprint": (
            "opening_range_retest_v1",
            "BUY_CALL",
            "RAW_CANDIDATE",
            pytest.approx(0.42150442477876104),
            "opening_range_breakout_retest_hold",
            "price_returns_inside_opening_range",
            "opening range breakout retest held",
        ),
    },
    "compression_breakout_v1": {
        "inventory_id": "COMPRESSION_BREAKOUT",
        "movement_type": "COMPRESSION_BREAKOUT",
        "role": "candidate_generator",
        "validation_level": "unverified",
        "contract_version": None,
        "fingerprint": (
            "compression_breakout_v1",
            "BUY_CALL",
            "RAW_CANDIDATE",
            pytest.approx(0.470676),
            "compression_range_breakout_release",
            "price_returns_inside_compression_range",
            "range and ATR compression released into a directional breakout",
        ),
    },
    "trend_pullback_v1": {
        "inventory_id": "TREND_PULLBACK",
        "movement_type": "TREND_PULLBACK",
        "role": "candidate_generator",
        "validation_level": "quarantined",
        "contract_version": "trend_pullback_temporal_v1",
        "fingerprint": (
            "trend_pullback_v1",
            "BUY_CALL",
            "RAW_CANDIDATE",
            pytest.approx(0.648584),
            "trend_pullback_hold_resume",
            "pullback_breaks_anchor",
            "established trend resumed after a controlled pullback",
        ),
    },
    "vwap_reclaim_rejection_v1": {
        "inventory_id": "VWAP_RECLAIM_REJECTION",
        "movement_type": "VWAP_RECLAIM_REJECTION",
        "role": "candidate_generator",
        "validation_level": "unverified",
        "contract_version": "vwap_reclaim_causal_v1",
        "fingerprint": (
            "vwap_reclaim_rejection_v1",
            "BUY_CALL",
            "RAW_CANDIDATE",
            pytest.approx(0.392377),
            "confirmed_vwap_reclaim_or_rejection",
            "price_crosses_back_through_vwap",
            "confirmed VWAP reclaim/rejection in a non-chop regime",
        ),
    },
}


def _load_bundle() -> dict[str, object]:
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundle_is_versioned_and_scoped_to_the_expected_commit() -> None:
    bundle = _load_bundle()

    assert bundle["bundle_version"] == "four_strategy_contract_bundle_v1"
    assert bundle["bundle_kind"] == "historical_validation_contract_freeze"
    assert bundle["source_commit"] == "94b48666d166c45e4b65679b4811aa1ddc237b46"
    assert bundle["branch"] == "fix/four-strategy-contract-freeze"
    assert bundle["scope"] == {
        "historical_validation_only": True,
        "live_readiness_claim": False,
        "profitability_claim": False,
        "production_code_changed": False,
    }


def test_bundle_source_hashes_match_the_current_repo_truth() -> None:
    bundle = _load_bundle()
    source_files = {item["path"]: item["sha256"] for item in bundle["source_files"]}

    assert source_files == EXPECTED_SOURCE_HASHES
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        assert _hash_file(Path(relative_path)) == expected_hash


def test_bundle_has_the_four_expected_strategy_contracts() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    assert set(strategies) == set(EXPECTED_STRATEGIES)

    for runtime_strategy_id, expected in EXPECTED_STRATEGIES.items():
        entry = strategies[runtime_strategy_id]
        assert entry["inventory_id"] == expected["inventory_id"]
        assert entry["movement_type"] == expected["movement_type"]
        assert entry["role"] == expected["role"]
        assert entry["validation_level"] == expected["validation_level"]
        assert entry["execution_eligible"] is False
        assert entry["contract_version"] == expected["contract_version"]
        assert entry["frozen_fingerprint"] == {
            "strategy_id": expected["fingerprint"][0],
            "direction": expected["fingerprint"][1],
            "status": expected["fingerprint"][2],
            "raw_score": expected["fingerprint"][3],
            "entry_trigger": expected["fingerprint"][4],
            "invalid_if": expected["fingerprint"][5],
            "rank_reason": expected["fingerprint"][6],
        }


def test_bundle_profile_resolution_matches_current_profile_truth() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    assert strategies["opening_range_retest_v1"]["profile"] == {
        "requested_profile_id": "opening_range_retest_v1",
        "resolved_profile_id": "opening_range_breakout_v1",
        "resolution_source": "COMPATIBILITY_ALIAS",
        "profile_version": "v1",
        "parameter_hash": "80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064",
    }
    assert strategies["compression_breakout_v1"]["profile"] == {
        "requested_profile_id": "compression_breakout_v1",
        "resolved_profile_id": "compression_breakout_v1",
        "resolution_source": "EXACT_PROFILE",
        "profile_version": "v1",
        "parameter_hash": "514c4d0b5c1d95b138afa051a88dbae8a6b1e1fa090e1b6f608d8d412a6d75b5",
    }
    assert strategies["trend_pullback_v1"]["profile"] == {
        "requested_profile_id": "trend_pullback_v1",
        "resolved_profile_id": "trend_pullback_v1",
        "resolution_source": "EXACT_PROFILE",
        "profile_version": "v1",
        "parameter_hash": "04513721c5b9a7e80b02c49e658f4dabfb1d9e1b379abbf42e24157c364ec2eb",
    }
    assert strategies["vwap_reclaim_rejection_v1"]["profile"] == {
        "requested_profile_id": "vwap_reclaim_rejection_v1",
        "resolved_profile_id": "vwap_reclaim_rejection_v1",
        "resolution_source": "EXACT_PROFILE",
        "profile_version": "v1",
        "parameter_hash": "ec28041cd6920b50018ef09fb4cf605aecb054b0205ec2852feebe801d98fc9b",
    }


def test_bundle_fingerprints_match_the_current_validation_proofs() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    for runtime_strategy_id, expected in EXPECTED_STRATEGIES.items():
        fingerprint = strategies[runtime_strategy_id]["frozen_fingerprint"]
        assert (
            fingerprint["strategy_id"],
            fingerprint["direction"],
            fingerprint["status"],
            fingerprint["raw_score"],
            fingerprint["entry_trigger"],
            fingerprint["invalid_if"],
            fingerprint["rank_reason"],
        ) == expected["fingerprint"]


def test_bundle_is_stable_under_canonical_json_round_trip() -> None:
    bundle = _load_bundle()
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    reparsed = json.loads(canonical)

    assert reparsed == bundle
