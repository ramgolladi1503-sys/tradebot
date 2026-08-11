from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


BUNDLE_PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json"
SIDECAR_PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json.sha256"

EXPECTED_SOURCE_HASHES = {
    "config/strategy_inventory.yml": "d14d28fea0950fe1a13eb2d975c12f9a1b0c789f21ae239fc7edea824b81c717",
    "core/movement_contract.py": "3e0025abfb1266a65617082cc09293e084392aa6c6f29d7d18c0381e9f765f95",
    "core/strategy_parameter_profiles.py": "c40787d570956da03f814dbb6a9fd6bb528c840c42c959ddb544e16e3a861407",
    "strategies/movement/opening_range_breakout.py": "06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e",
    "strategies/movement/trend_pullback.py": "36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1",
    "strategies/movement/compression_breakout.py": "c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7",
    "strategies/movement/vwap_reclaim.py": "7a30df420d2b70b4533c96e07bcccf784fbfe9e28e504cc2af7ff0aaa89566fc",
}

EXPECTED_OWNER_HASHES = {
    "core/opening_range_retest_publication.py": "7c8183b4f5c7a46c6165d6cc06a33c42cb8e3c89b7679b2f810374fb7779658a",
    "core/opening_range_retest_emission_store.py": "24702110e6e4789f510bfc291bf7a86d21056a8cd85f122e47c7ce5a104c43d0",
    "core/candidate_pool.py": "0dff0a9405340f9deda8a875af0322883b7614df369d6dc0e54d6f14c7792bfa",
    "core/strategy_parameter_profiles.py": "c40787d570956da03f814dbb6a9fd6bb528c840c42c959ddb544e16e3a861407",
    "strategies/movement/opening_range_breakout.py": "06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e",
    "strategies/movement/compression_breakout.py": "c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7",
    "strategies/movement/trend_pullback.py": "36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1",
    "strategies/movement/vwap_reclaim.py": "7a30df420d2b70b4533c96e07bcccf784fbfe9e28e504cc2af7ff0aaa89566fc",
}

EXPECTED_STRATEGIES = {
    "opening_range_retest_v1": {
        "canonical_strategy_id": "OPENING_RANGE_RETEST",
        "runtime_strategy_id": "opening_range_retest_v1",
        "movement_type": "OPENING_RANGE_RETEST",
        "role": "candidate_generator",
        "validation_level": "quarantined",
        "contract_version": "opening_range_retest_temporal_v1",
        "profile": {
            "requested_profile_id": "opening_range_retest_v1",
            "resolved_profile_id": "opening_range_breakout_v1",
            "resolution_source": "COMPATIBILITY_ALIAS",
            "profile_version": "v1",
            "parameter_hash": "80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064",
            "compatibility_alias": "opening_range_retest_v1->opening_range_breakout_v1",
        },
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
        "canonical_strategy_id": "COMPRESSION_BREAKOUT",
        "runtime_strategy_id": "compression_breakout_v1",
        "movement_type": "COMPRESSION_BREAKOUT",
        "role": "candidate_generator",
        "validation_level": "unverified",
        "contract_version": None,
        "profile": {
            "requested_profile_id": "compression_breakout_v1",
            "resolved_profile_id": "compression_breakout_v1",
            "resolution_source": "EXACT_PROFILE",
            "profile_version": "v1",
            "parameter_hash": "514c4d0b5c1d95b138afa051a88dbae8a6b1e1fa090e1b6f608d8d412a6d75b5",
        },
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
        "canonical_strategy_id": "TREND_PULLBACK",
        "runtime_strategy_id": "trend_pullback_v1",
        "movement_type": "TREND_PULLBACK",
        "role": "candidate_generator",
        "validation_level": "quarantined",
        "contract_version": "trend_pullback_temporal_v1",
        "profile": {
            "requested_profile_id": "trend_pullback_v1",
            "resolved_profile_id": "trend_pullback_v1",
            "resolution_source": "EXACT_PROFILE",
            "profile_version": "v1",
            "parameter_hash": "04513721c5b9a7e80b02c49e658f4dabfb1d9e1b379abbf42e24157c364ec2eb",
        },
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
        "canonical_strategy_id": "VWAP_RECLAIM_REJECTION",
        "runtime_strategy_id": "vwap_reclaim_rejection_v1",
        "movement_type": "VWAP_RECLAIM_REJECTION",
        "role": "candidate_generator",
        "validation_level": "unverified",
        "contract_version": "vwap_reclaim_causal_v1",
        "profile": {
            "requested_profile_id": "vwap_reclaim_rejection_v1",
            "resolved_profile_id": "vwap_reclaim_rejection_v1",
            "resolution_source": "EXACT_PROFILE",
            "profile_version": "v1",
            "parameter_hash": "ec28041cd6920b50018ef09fb4cf605aecb054b0205ec2852feebe801d98fc9b",
        },
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

EXPECTED_FUTURE_PHASE_EXCLUSIONS = [
    "historical dataset selection",
    "dataset file paths",
    "dataset hashes",
    "data vendor",
    "instrument universe",
    "underlying universe",
    "option-contract resolution policy",
    "cost model",
    "brokerage",
    "taxes and statutory charges",
    "slippage model",
    "fill model",
    "bid/ask execution model",
    "liquidity simulation",
    "capital allocation",
    "position sizing",
    "portfolio constraints",
    "risk budget",
    "WFA windows",
    "training windows",
    "validation windows",
    "holdout windows",
    "purge",
    "embargo",
    "parameter-search space",
    "profitability thresholds",
    "certification thresholds",
    "paper-trading gates",
    "live-readiness gates",
]


def _load_bundle() -> dict[str, object]:
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_file_at_commit(commit: str, relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    raw = subprocess.check_output(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
    )
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(bundle: dict[str, object]) -> bytes:
    return (json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def test_bundle_is_versioned_and_scoped_to_the_expected_commit() -> None:
    bundle = _load_bundle()

    assert bundle["schema_version"] == 1
    assert bundle["bundle_name"] == "four_strategy_contract_bundle"
    assert bundle["bundle_version"] == 1
    assert bundle["bundle_id"] == "four_strategy_contract_bundle_v1"
    assert bundle["bundle_kind"] == "historical_validation_contract_freeze"
    assert bundle["source_commit"] == "94b48666d166c45e4b65679b4811aa1ddc237b46"
    assert bundle["architecture_decision"] == "KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE"
    assert bundle["bundle_sha256_sidecar"] == "docs/agent_reviews/four_strategy_contract_bundle_v1.json.sha256"
    assert bundle["scope"] == {
        "historical_validation_only": True,
        "live_readiness_claim": False,
        "profitability_claim": False,
        "production_code_changed": False,
    }
    assert bundle["included_strategies"] == [
        "opening_range_retest_v1",
        "compression_breakout_v1",
        "trend_pullback_v1",
        "vwap_reclaim_rejection_v1",
    ]
    assert bundle["future_phase_boundaries"]["do_not_claim"] == [
        "profitability",
        "live readiness",
        "production certification",
        "execution authority",
        "Phase 2 authority",
    ]


def test_bundle_bytes_are_canonical_and_sidecar_matches() -> None:
    bundle = _load_bundle()
    canonical = _canonical_bytes(bundle)
    raw = BUNDLE_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = SIDECAR_PATH.read_text(encoding="utf-8").strip()

    assert raw == canonical
    assert raw.endswith(b"\n")
    assert canonical == _canonical_bytes(json.loads(raw.decode("utf-8")))
    assert sidecar == f"{digest}  {BUNDLE_PATH.name}"
    assert sidecar.split()[1] == BUNDLE_PATH.name
    assert digest == _hash_file(BUNDLE_PATH)


def test_bundle_source_hashes_match_frozen_source_commit() -> None:
    bundle = _load_bundle()
    source_files = {item["path"]: item["sha256"] for item in bundle["source_files"]}
    source_commit = bundle["source_commit"]

    assert source_files == EXPECTED_SOURCE_HASHES
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        assert _hash_file_at_commit(source_commit, relative_path) == expected_hash


def test_bundle_owner_files_match_current_repo_truth() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    for runtime_strategy_id, expected in EXPECTED_STRATEGIES.items():
        owner_paths = {
            item["path"]: item["sha256"]
            for item in strategies[runtime_strategy_id]["production_owner_files"]
        }
        for owner_path, expected_hash in EXPECTED_OWNER_HASHES.items():
            if runtime_strategy_id == "opening_range_retest_v1" and owner_path not in {
                "core/opening_range_retest_publication.py",
                "core/opening_range_retest_emission_store.py",
                "core/strategy_parameter_profiles.py",
                "strategies/movement/opening_range_breakout.py",
            }:
                continue
            if runtime_strategy_id == "compression_breakout_v1" and owner_path not in {
                "core/candidate_pool.py",
                "core/strategy_parameter_profiles.py",
                "strategies/movement/compression_breakout.py",
            }:
                continue
            if runtime_strategy_id == "trend_pullback_v1" and owner_path not in {
                "core/candidate_pool.py",
                "core/strategy_parameter_profiles.py",
                "strategies/movement/trend_pullback.py",
            }:
                continue
            if runtime_strategy_id == "vwap_reclaim_rejection_v1" and owner_path not in {
                "core/candidate_pool.py",
                "core/strategy_parameter_profiles.py",
                "strategies/movement/vwap_reclaim.py",
            }:
                continue
            assert owner_paths[owner_path] == expected_hash

        assert strategies[runtime_strategy_id]["profile"] == expected["profile"]


def test_bundle_has_the_four_expected_strategy_contracts() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    assert set(strategies) == set(EXPECTED_STRATEGIES)

    for runtime_strategy_id, expected in EXPECTED_STRATEGIES.items():
        entry = strategies[runtime_strategy_id]
        assert entry["canonical_strategy_id"] == expected["canonical_strategy_id"]
        assert entry["movement_type"] == expected["movement_type"]
        assert entry["role"] == expected["role"]
        assert entry["validation_level"] == expected["validation_level"]
        assert entry["contract_version"] == expected["contract_version"]
        assert entry["profile"] == expected["profile"]
        assert entry["frozen_output_vector"] == {
            "strategy_id": expected["fingerprint"][0],
            "direction": expected["fingerprint"][1],
            "status": expected["fingerprint"][2],
            "raw_score": expected["fingerprint"][3],
            "entry_trigger": expected["fingerprint"][4],
            "invalid_if": expected["fingerprint"][5],
            "rank_reason": expected["fingerprint"][6],
        }
        assert entry["fingerprint_classification"]["output_classification"] == "FIXED_OUTPUT_FINGERPRINT"


def test_bundle_records_identity_and_lifecycle_contracts_honestly() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    opening = strategies["opening_range_retest_v1"]
    assert opening["fingerprint_classification"]["candidate_identity_fingerprint"] == {
        "status": "CANDIDATE_IDENTITY_FINGERPRINT",
        "fields": [
            "strategy_id",
            "symbol",
            "session_date",
            "direction",
            "boundary_type",
            "normalized_boundary_value",
            "breakout_timestamp",
            "setup_id",
            "history_hash",
        ],
        "field_order": [
            "strategy_id",
            "symbol",
            "session_date",
            "direction",
            "boundary_type",
            "normalized_boundary_value",
            "breakout_timestamp",
            "setup_id",
            "history_hash",
        ],
        "normalization_rules": [
            "canonical_json_serialization",
            "sha256_setup_id",
            "history_hash_from_completed_causal_prefix",
        ],
        "deduplication_relationship": "durable_owner_setup_id",
        "owner_file": "core/opening_range_retest_publication.py",
        "owner_symbol": "build_opening_range_retest_proposal",
        "timestamp_contribution": "breakout_timestamp",
    }
    assert opening["lifecycle_contract"]["duplicate_suppression_owner"] == "OpeningRangeRetestEmissionStore"
    assert opening["lifecycle_contract"]["restart_behavior"].startswith("ALREADY_EMITTED")
    assert opening["lifecycle_contract"]["missing_data_behavior"]["missing_history"] == "FAIL_CLOSED"
    assert opening["authority_boundary"] == {
        "raw_strategy_score_owner": "strategy",
        "phase2_score_owner": "phase2",
        "rank_score_owner": "ranking",
        "execution_eligibility_owner": "live_phase2",
        "claimed_by_generator": {
            "phase2_score": False,
            "liquidity_score": False,
            "freshness_score": False,
            "execution_eligible": False,
        },
    }

    for runtime_strategy_id in ("compression_breakout_v1", "trend_pullback_v1", "vwap_reclaim_rejection_v1"):
        entry = strategies[runtime_strategy_id]
        assert entry["fingerprint_classification"]["candidate_identity_fingerprint"]["status"] == "UNRESOLVED"
        assert entry["lifecycle_contract"]["duplicate_suppression_owner"] == "core.candidate_pool.candidate_pool_dedupe_key"
        assert entry["authority_boundary"]["claimed_by_generator"] == {
            "phase2_score": False,
            "liquidity_score": False,
            "freshness_score": False,
            "execution_eligible": False,
        }


def test_bundle_gap_classification_block_is_explicit_and_machine_checkable() -> None:
    bundle = _load_bundle()
    gap = bundle["evidence_gap_classification"]

    identity = gap["candidate_identity_contracts"]
    assert identity["opening_range_retest_v1"]["status"] == "PROVEN"
    assert identity["opening_range_retest_v1"]["classification"] == "CANDIDATE_IDENTITY_PROVEN"
    assert identity["trend_pullback_v1"]["status"] == "UNRESOLVED_WITH_EXACT_REASON"
    assert identity["trend_pullback_v1"]["classification"] == "POOL_DEDUPLICATION_ONLY"
    assert identity["compression_breakout_v1"]["status"] == "UNRESOLVED_WITH_EXACT_REASON"
    assert identity["compression_breakout_v1"]["classification"] == "POOL_DEDUPLICATION_ONLY"
    assert identity["vwap_reclaim_rejection_v1"]["status"] == "UNRESOLVED_WITH_EXACT_REASON"
    assert identity["vwap_reclaim_rejection_v1"]["classification"] == "POOL_DEDUPLICATION_ONLY"

    version_gap = gap["compression_breakout_contract_version_ownership"]
    assert version_gap["status"] == "UNRESOLVED_WITH_EXACT_REASON"
    assert version_gap["classification"] == "UNVERSIONED_RUNTIME_CONTRACT"
    assert version_gap["contract_version"] is None

    thresholds = gap["active_runtime_thresholds_vs_dormant_defaults"]
    assert thresholds["status"] == "PROVEN"
    assert thresholds["embedded_non_enforced_defaults"] == {
        "opening_range_retest_v1": ["MIN_RETEST_MINUTES", "MAX_RETEST_MINUTES"],
    }
    assert thresholds["historical_replay_treatment"]["MIN_RETEST_MINUTES"] == "DO_NOT_ENFORCE"
    assert thresholds["historical_replay_treatment"]["MAX_RETEST_MINUTES"] == "DO_NOT_ENFORCE"
    assert thresholds["historical_replay_treatment"]["MIN_BREAKOUT_DISTANCE_PCT"] == "ENFORCE_AS_RUNTIME_CONTRACT"
    assert thresholds["historical_replay_treatment"]["MAX_CHOP_SCORE"] == "ENFORCE_AS_RUNTIME_CONTRACT"

    exclusions = gap["explicit_future_phase_exclusions"]
    assert exclusions["status"] == "PROVEN"
    assert exclusions["classification"] == "FUTURE_PHASE_NOT_FROZEN"
    assert exclusions["items"] == EXPECTED_FUTURE_PHASE_EXCLUSIONS

    baseline = gap["baseline_auth_failure_evidence_metadata"]
    assert baseline == {
        "status": "PROVEN",
        "exact_command": "python -m pytest -q tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports",
        "exit_code": 1,
        "failure_type": "RuntimeError",
        "failure_message": "[AUTH] missing_kite_access_token",
        "failure_scope": "pre-existing unrelated baseline failure",
    }

    cleanup = gap["test_residue_cleanup_evidence"]
    assert cleanup["status"] == "PROVEN"
    assert cleanup["pre_test_hash"] == "97ef1fc8c0eaa4c39c8580c01236256531bcc1c11f35bcb91aefa471fa9d8f31"
    assert cleanup["tracked_residue_restore"] == (
        "git show HEAD:runtime/strategy_validation/regime_timeline.jsonl > "
        "runtime/strategy_validation/regime_timeline.jsonl"
    )
    assert cleanup["generated_file_cleanup"].startswith("remove only explicit MagicMock-named files")
    assert cleanup["final_git_status"] == "clean after cleanup proof"

    subagents = gap["subagent_deployment_or_skip_reason"]
    assert subagents["status"] == "NOT_APPLICABLE"
    assert subagents["exact_reason"] == (
        "primary agent executed the required read-only audit lanes in-thread; "
        "no external subagents were required or deployed"
    )


def test_bundle_parameter_input_temporal_and_profile_matrices_are_complete() -> None:
    bundle = _load_bundle()
    strategies = {item["runtime_strategy_id"]: item for item in bundle["strategies"]}

    for runtime_strategy_id, entry in strategies.items():
        assert entry["parameters"]
        for parameter in entry["parameters"]:
            assert {"name", "value", "type", "unit", "owner_file", "owner_symbol", "semantic_meaning", "comparison_semantics"} <= set(parameter)
            assert parameter["comparison_semantics"] in {
                "less_than_or_equal",
                "greater_than_or_equal",
                "less_than",
                "embedded_default_only",
            }

        assert entry["required_inputs"]
        for required_input in entry["required_inputs"]:
            assert {"field", "data_type", "unit", "source_owner", "required", "missing_data_behavior", "provenance_requirement", "freshness_requirement"} <= set(required_input)

        temporal = entry["temporal_contract"]
        assert {"bar_interval", "timezone", "market_session_interpretation", "completed_history_requirement", "warmup_requirement", "current_bar_inclusion_policy", "signal_timestamp_semantics", "feature_cutoff_semantics", "future_bar_exclusion", "future_mutation_expectation", "expiry_session_restrictions"} <= set(temporal)

        profile = entry["historical_validation_profile"]
        assert {"required_ohlcv_fields", "required_derived_fields", "allowed_provenance", "bar_and_session_rules", "minimum_completed_history", "warmup", "signal_evaluation_timing", "causal_cutoff", "candidate_output_fields", "determinism_requirements", "required_negative_controls", "contract_justified_perturbation_dimensions"} <= set(profile)

    assert strategies["opening_range_retest_v1"]["temporal_contract"]["completed_history_requirement"] == 15
    assert strategies["trend_pullback_v1"]["temporal_contract"]["completed_history_requirement"] == 4
    assert strategies["vwap_reclaim_rejection_v1"]["temporal_contract"]["completed_history_requirement"] == 3
    assert strategies["compression_breakout_v1"]["temporal_contract"]["bar_interval"] == "snapshot_only"


def test_bundle_is_stable_under_canonical_json_round_trip() -> None:
    bundle = _load_bundle()
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    reparsed = json.loads(canonical)

    assert reparsed == bundle
