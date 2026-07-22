from __future__ import annotations

import json
from pathlib import Path

from research.structural_pattern_suite.contracts import Candidate, Side, StrategyId
from research.structural_pattern_suite.router import route_candidates
from research.structural_pattern_suite.verdict import insufficient_data_strategy_verdict, suite_verdict
from scripts.run_structural_pattern_suite import build_reports


def candidate(strategy_id: StrategyId, side: Side = Side.LONG, ts: str = "2026-07-20T09:45:00+05:30") -> Candidate:
    return Candidate(
        strategy_id=strategy_id,
        strategy_version="v1",
        symbol="NIFTY",
        side=side,
        session="2026-07-20",
        decision_timestamp=ts,
        entry_timestamp="2026-07-20T09:50:00+05:30",
        source_manifest_hash="s" * 64,
        feature_contract_hash="f" * 64,
        candidate_bundle_hash="c" * 64,
    )


def test_router_keeps_gap_go_over_prior_range_same_symbol_side_boundary() -> None:
    accepted, rejected = route_candidates([
        candidate(StrategyId.PRIOR_RANGE_LEADER),
        candidate(StrategyId.GAP_GO_LEADER),
    ])
    assert [item.strategy_id for item in accepted] == [StrategyId.GAP_GO_LEADER]
    assert rejected["lower_priority_same_side"] == 1


def test_router_rejects_contradictory_sides_at_same_boundary() -> None:
    accepted, rejected = route_candidates([
        candidate(StrategyId.GAP_GO_LEADER, Side.LONG),
        candidate(StrategyId.PRIOR_RANGE_LEADER, Side.SHORT),
    ])
    assert accepted == []
    assert rejected["contradictory_side"] == 2


def test_fail_closed_suite_verdict_does_not_certify_missing_data() -> None:
    verdicts = [insufficient_data_strategy_verdict(strategy_id) for strategy_id in StrategyId]
    assert suite_verdict(verdicts) == "CERTIFY_NONE"
    assert verdicts[0]["30_MINUTE_COMPATIBILITY"] == "FAIL_PRODUCTION_COMPATIBILITY"


def test_runner_emits_required_evidence_and_sidecars(tmp_path: Path) -> None:
    kite = tmp_path / "kite_candidate_replay.zip"
    kite.write_bytes(b"not-the-real-archive")
    result = build_reports(tmp_path / "evidence", kite)
    assert result["final_verdict"] == "CERTIFY_NONE"
    required = [
        "source_authority.json",
        "strategy_contracts.json",
        "threshold_freeze.json",
        "candidate_bundle_hash.json",
        "chronological_folds.json",
        "underlying_wfa.json",
        "horizon_comparison.json",
        "matched_controls.json",
        "negative_controls.json",
        "parameter_neighbourhood.json",
        "delay_sensitivity.json",
        "concentration.json",
        "option_replay.json",
        "production_compatibility.json",
        "router_comparison.json",
        "independent_oracle.json",
        "determinism.json",
        "final_verdict.json",
        "FINAL_REPORT.md",
    ]
    for name in required:
        assert (tmp_path / "evidence" / name).is_file()
        assert (tmp_path / "evidence" / f"{name}.sha256").is_file()
    source = json.loads((tmp_path / "evidence" / "source_authority.json").read_text())
    assert source["kite_hash_verified"] is False
    assert source["broker_api_called"] is False

