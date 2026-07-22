from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.structural_pattern_suite.contracts import Candidate, Side, StrategyId
from research.structural_pattern_suite.router import route_candidates
from research.structural_pattern_suite.verdict import insufficient_data_strategy_verdict, suite_verdict
from scripts.run_structural_pattern_suite import SourceError, build_reports


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


def test_runner_rejects_fake_archive_hash(tmp_path: Path) -> None:
    kite = tmp_path / "kite_candidate_replay.zip"
    kite.write_bytes(b"not-the-real-archive")
    with pytest.raises(SourceError, match="hash mismatch"):
        build_reports(tmp_path / "evidence", kite)


def test_runner_emits_v2_required_evidence_and_sidecars(tmp_path: Path) -> None:
    real_kite = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
    if not real_kite.is_file():
        pytest.skip("real Kite archive not available")
    result = build_reports(tmp_path / "evidence", real_kite)
    assert result["final_verdict"] == "CERTIFY_NONE"
    assert result["candidate_count"] > 0
    required = [
        "run-a/source/kite_source_authority.json",
        "run-a/source/accepted_file_manifest.json",
        "run-a/source/evidence_exposure_registry.json",
        "run-a/contracts/strategy_contracts.json",
        "run-a/candidates/candidate_manifest.json",
        "run-a/candidates/candidate_manifest.parquet",
        "run-a/evaluation/underlying_wfa.json",
        "run-a/evaluation/negative_controls.json",
        "run-a/audit/independent_oracle.json",
        "run-a/audit/mutation_test_results.json",
        "run-a/audit/final_verdict.json",
        "run-b/candidates/candidate_manifest.json",
        "audit/determinism.json",
    ]
    for name in required:
        assert (tmp_path / "evidence" / name).is_file()
        assert (tmp_path / "evidence" / f"{name}.sha256").is_file()
    source = json.loads((tmp_path / "evidence" / "run-a/source/kite_source_authority.json").read_text())
    assert source["hash_verified"] is True
    assert source["broker_api_called"] is False
    det = json.loads((tmp_path / "evidence" / "audit/determinism.json").read_text())
    assert det["status"] == "PASS"
