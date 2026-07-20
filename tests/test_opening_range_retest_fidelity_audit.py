from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy_parameter_profiles import RuntimeProfileResolution
from research.opening_range_retest_fidelity_audit.artifact_audit import audit_artifacts
from research.opening_range_retest_fidelity_audit.evaluator import build_artifacts
from strategies.movement import opening_range_breakout as orb
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_AGE_5_ROWS,
    CALL_AGE_6_ROWS,
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _history_state_for_rows,
    _regime,
    _temporal_context,
)


def _candidate_for(rows: tuple[tuple[int, float, float, float, float], ...]):
    state = _history_state_for_rows(rows)
    candidates = orb.generate_opening_range_retest_candidates(_temporal_context(state), _regime())
    return candidates[0] if candidates else None


def test_profile_min_max_retest_minutes_are_required_but_inert() -> None:
    artifacts = build_artifacts()
    matrix = artifacts["parameter_wiring_results.json"]["matrix"]

    assert matrix["MIN_RETEST_MINUTES"]["runtime_role"] == "REQUIRED_BUT_INERT"
    assert matrix["MAX_RETEST_MINUTES"]["runtime_role"] == "REQUIRED_BUT_INERT"
    assert "MIN_RETEST_MINUTES" in orb.REQUIRED_PROFILE_KEYS
    assert "MAX_RETEST_MINUTES" in orb.REQUIRED_PROFILE_KEYS


def test_distance_parameters_are_score_only_not_candidate_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4]
    baseline = _candidate_for(rows)
    assert baseline is not None

    def strict_profile(strategy_id: str, required_keys: tuple[str, ...]) -> RuntimeProfileResolution:
        assert strategy_id == orb.STRATEGY_ID
        assert required_keys == orb.REQUIRED_PROFILE_KEYS
        return RuntimeProfileResolution(
            requested_profile_id=orb.STRATEGY_ID,
            resolved_profile_id="opening_range_breakout_v1",
            profile_version="v1",
            resolution_source="COMPATIBILITY_ALIAS",
            parameter_hash="strict-test-profile",
            parameters={
                "MIN_RETEST_MINUTES": 999,
                "MAX_RETEST_MINUTES": 999,
                "MAX_RETEST_DISTANCE_PCT": 0.00001,
                "MIN_BREAKOUT_DISTANCE_PCT": 0.01,
            },
        )

    monkeypatch.setattr(orb, "resolve_required_profile_parameters", strict_profile)
    strict = _candidate_for(rows)

    assert strict is not None
    assert strict.direction == baseline.direction
    assert strict.evidence["setup_identity"] == baseline.evidence["setup_identity"]
    assert strict.lineage["params_used"] != baseline.lineage["params_used"]


def test_hardcoded_breakout_to_retest_age_boundary() -> None:
    assert _candidate_for(OPENING_RANGE_ROWS + CALL_AGE_5_ROWS) is None
    assert _candidate_for(OPENING_RANGE_ROWS + CALL_AGE_6_ROWS) is not None


def test_incremental_prefix_and_whole_history_have_known_different_semantics() -> None:
    prefix_candidate = _candidate_for(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    whole_history_candidate = _candidate_for(OPENING_RANGE_ROWS + CALL_VALID_ROWS)

    assert prefix_candidate is not None
    assert whole_history_candidate is None
    artifacts = build_artifacts()
    assert artifacts["replay_equivalence_results.json"]["status"] == "REQUIRES_PREFIX_REPLAY"


def test_vwap_alignment_label_is_not_runtime_gate() -> None:
    normal = _candidate_for(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    assert normal is not None

    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    ctx = _temporal_context(state, vwap=1.0)
    no_vwap_alignment = orb.generate_opening_range_retest_candidates(ctx, _regime())
    assert no_vwap_alignment
    assert "vwap_alignment" in no_vwap_alignment[0].confluence_tags

    artifacts = build_artifacts()
    assert artifacts["label_truth_audit.json"]["status"] == "LABEL_OVERSTATED"


def test_final_fidelity_verdict_classifies_parameter_contract_broken() -> None:
    artifacts = build_artifacts()
    verdict = artifacts["final_fidelity_verdict.json"]

    assert verdict["primary_verdict"] == "PARAMETER_CONTRACT_BROKEN"
    assert verdict["edge_applicability"] == "VALID_ONLY_FOR_CURRENT_MISWIRED_VARIANT"
    assert verdict["production_changes_made"] is False
    assert verdict["optimization_performed"] is False


def test_generated_artifact_audit_is_ready() -> None:
    audit_path = Path("research/opening_range_retest_fidelity_audit/artifact_audit.json")
    if not audit_path.exists():
        pytest.skip("artifact generation has not run yet")
    result = audit_artifacts()
    assert result["status"] == "READY", json.dumps(result, sort_keys=True)
