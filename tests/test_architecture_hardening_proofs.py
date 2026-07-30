from __future__ import annotations

import json
from pathlib import Path

from core.architecture_golden_master import compare_snapshot_files, compare_snapshots, semantic_hash
from core.execution_ranking_authority import inspect_authority
from core.execution_shadow_cycle import compare_cycle
from core.helper_parity_proof import prove_helper_parity
from core.orchestrator_stage_pipeline import OrchestratorStagePipeline
from core.trade_builder_stage_pipeline import TradeBuilderStagePipeline


def _executable_candidate() -> dict:
    return {
        "trade_id": "t1",
        "candidate_origin": "strategy",
        "candidate_status": "ranked",
        "execution_status": "EXECUTABLE",
        "execution_entry_status": "EXECUTABLE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "execution_entry": 101.5,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
    }


def test_golden_master_ignores_only_declared_volatile_fields(tmp_path: Path) -> None:
    expected = [{"trade_id": "t1", "entry": 101.5, "timestamp": "old"}]
    actual = [{"entry": 101.5, "trade_id": "t1", "timestamp": "new"}]
    assert compare_snapshots(expected, actual).matched is True
    assert semantic_hash(expected) == semantic_hash(actual)

    expected_path = tmp_path / "expected.json"
    actual_path = tmp_path / "actual.jsonl"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    actual_path.write_text(json.dumps(actual[0]) + "\n", encoding="utf-8")
    assert compare_snapshot_files(expected_path, actual_path).matched is True


def test_golden_master_detects_behavior_change() -> None:
    result = compare_snapshots([{"entry": 101.5}], [{"entry": 102.0}])
    assert result.matched is False
    assert result.expected_hash != result.actual_hash


def test_helper_parity_covers_executable_synthetic_and_blocked_rows(monkeypatch) -> None:
    monkeypatch.setattr("core.orchestrator_truth.cfg.ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", True, raising=False)
    rows = [
        _executable_candidate(),
        {"trade_id": "softrej_1", "candidate_origin": "fallback", "permission": "ADVISORY_ONLY"},
        {**_executable_candidate(), "trade_id": "t2", "hard_blockers": ["risk"]},
        {**_executable_candidate(), "trade_id": "t3", "execution_status": "", "execution_entry_status": "EXECUTABLE"},
    ]
    assert prove_helper_parity(rows) == ()


def test_shadow_cycle_reports_exact_mismatches() -> None:
    rows = [
        _executable_candidate(),
        {"trade_id": "fallback", "candidate_origin": "fallback", "permission": "ADVISORY_ONLY"},
    ]
    report = compare_cycle(rows)
    assert report["row_count"] == 2
    assert report["match_count"] + report["mismatch_count"] == 2
    assert 0.0 <= report["parity_rate"] <= 1.0
    assert len(report["rows"]) == 2


def test_authority_requires_ranked_value_to_reach_execution(tmp_path: Path) -> None:
    reporting_only = tmp_path / "reporting_only.py"
    reporting_only.write_text(
        "report = build_ranked_opportunity_report(rows)\nwrite_report(report)\n",
        encoding="utf-8",
    )
    evidence = inspect_authority(reporting_only)
    assert evidence.ranking_calls
    assert evidence.execution_calls == ()
    assert evidence.ranking_results_consumed_by_execution is False

    authoritative = tmp_path / "authoritative.py"
    authoritative.write_text(
        "ranked = build_ranked_opportunity_report(rows)\nplace_order(ranked)\n",
        encoding="utf-8",
    )
    evidence = inspect_authority(authoritative)
    assert evidence.ranking_results_consumed_by_execution is True


def test_extraction_seams_are_behavior_neutral_until_stages_are_registered() -> None:
    payload = {"candidate": "unchanged"}
    trade_result = TradeBuilderStagePipeline.passthrough().run(payload)
    orchestrator_result = OrchestratorStagePipeline.passthrough().run(payload)
    assert trade_result.value is payload
    assert trade_result.stage_names == ()
    assert orchestrator_result.context is payload
    assert orchestrator_result.completed_stages == ()


def test_extraction_seams_are_deterministic() -> None:
    pipeline = TradeBuilderStagePipeline((
        ("one", lambda value: value + [1]),
        ("two", lambda value: value + [2]),
    ))
    first = pipeline.run([])
    second = pipeline.run([])
    assert first == second
    assert first.value == [1, 2]
    assert first.stage_names == ("one", "two")
