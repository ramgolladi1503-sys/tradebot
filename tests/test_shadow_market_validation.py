from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.expectancy.top_opportunity_selector import write_top_opportunities_report
from core.candidate_outcome_tracker import write_candidate_outcome_records
from core.expectancy.strategy_regime_expectancy import write_strategy_regime_expectancy_report
from scripts.run_shadow_market_validation import main as run_shadow_market_validation_main


def _journal_row(**overrides: object) -> dict[str, object]:
    row = {
        "candidate_id": "cand-exec-1",
        "trade_id": "trade-exec-1",
        "strategy_family": "breakout",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "regime": "LIVE",
        "expiry_type": "WEEKLY",
        "direction": "BUY",
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "signal_epoch": 100.0,
        "reportable_executable": True,
        "execution_allowed": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "candidate_status": "executable",
        "readiness": "READY",
        "execution_entry_status": "executable",
        "fallback_used": False,
    }
    row.update(overrides)
    return row


def _candidate_outcome_row(candidate_id: str, trade_id: str, window_sec: int, **overrides: object) -> dict[str, object]:
    row = {
        "candidate_id": candidate_id,
        "trade_id": trade_id,
        "strategy_family": "breakout",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "regime": "LIVE",
        "expiry_type": "WEEKLY",
        "direction": "BUY",
        "window_sec": window_sec,
        "outcome_status": "TARGET_HIT",
        "outcome_reason": "target_hit",
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "max_favorable_price": 110.0,
        "max_adverse_price": 97.0,
        "mfe_abs": 10.0,
        "mae_abs": 3.0,
        "mfe_r": 2.0,
        "mae_r": 0.6,
        "gross_r": 2.0,
        "estimated_cost_r": 0.25,
        "cost_adjusted_r": 1.75,
        "target_hit": True,
        "stop_hit": False,
        "timeout_hit": False,
        "first_hit_epoch": 140.0,
        "observation_count": 2,
        "blockers": [],
        "fallback_used": False,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }
    row.update(overrides)
    return row


def _top_row(candidate_id: str, trade_id: str, *, edge_rank_score: float, rank_score: float, expectancy_status: str = "KEEP", fallback_used: bool = False, execution_truth_state: str = "EXEMPLAR", reportable_executable: bool = True, execution_allowed: bool = True, permission: str = "EXECUTE", final_action: str = "EXECUTE", blockers: list[str] | None = None) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "trade_id": trade_id,
        "symbol": "NIFTY",
        "index": "NIFTY",
        "strategy_family": "breakout",
        "setup_id": f"setup-{candidate_id}",
        "regime": "LIVE",
        "direction": "BUY",
        "edge_rank_score": edge_rank_score,
        "rank_score": rank_score,
        "confidence_final": 0.9,
        "expectancy_status": expectancy_status,
        "expectancy_sample_count": 50,
        "expectancy_avg_cost_adjusted_r": 0.2,
        "execution_truth_state": execution_truth_state,
        "reportable_executable": reportable_executable,
        "execution_allowed": execution_allowed,
        "permission": permission,
        "final_action": final_action,
        "fallback_used": fallback_used,
        "why_ranked": "expectancy=keep|edge_rank_score=0.9|execution_eligible",
        "why_not_ranked": "" if expectancy_status == "KEEP" else "expectancy_watch",
        "blockers": blockers or [],
    }


def test_shadow_runner_writes_session_evidence_from_deterministic_fixture(tmp_path: Path) -> None:
    journal_path = tmp_path / "candidate_journal.jsonl"
    with journal_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_journal_row(candidate_id="cand-exec-1", trade_id="trade-exec-1")) + "\n")
        handle.write(json.dumps(_journal_row(candidate_id="cand-fallback-1", trade_id="softrej_trade-fallback", fallback_used=True, candidate_status="advisory_only", execution_status="advisory_only", permission="QUEUE_ONLY", final_action="QUEUE_ONLY", execution_allowed=False, reportable_executable=False)) + "\n")

    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records(
        [
            _candidate_outcome_row("cand-exec-1", "trade-exec-1", 300),
            _candidate_outcome_row("cand-fallback-1", "softrej_trade-fallback", 300, fallback_used=True, outcome_status="NOT_EXECUTABLE", outcome_reason="fallback_not_executable", cost_adjusted_r=-1.0, gross_r=-1.0, target_hit=False, stop_hit=False, timeout_hit=False, blockers=["fallback_not_executable"]),
        ],
        path=outcomes_path,
    )

    top_dir = tmp_path / "top"
    write_top_opportunities_report(
        [
            _top_row("cand-exec-1", "trade-exec-1", edge_rank_score=0.95, rank_score=0.85),
            _top_row("cand-fallback-1", "softrej_trade-fallback", edge_rank_score=0.20, rank_score=0.10, fallback_used=True, expectancy_status="KEEP", permission="BLOCK", final_action="BLOCK", execution_allowed=False, reportable_executable=False, execution_truth_state="BLOCKED", blockers=["fallback_not_executable"]),
        ],
        output_dir=top_dir,
    )
    top_path = top_dir / "top_opportunities_latest.json"

    from core.expectancy.shadow_validation import build_shadow_market_validation_report, write_shadow_market_validation_report

    report = build_shadow_market_validation_report(
        candidate_journal=journal_path,
        candidate_outcomes=outcomes_path,
        top_opportunities=top_path,
        output_dir=tmp_path / "shadow",
        session_date="20260607",
    )

    assert report.candidate_count == 2
    assert report.executable_count == 1
    assert report.advisory_count == 0
    assert report.blocked_count == 0
    assert report.fallback_count == 1
    assert round(report.avg_cost_adjusted_r, 2) == 1.75
    assert report.top_1_result["candidate_id"] == "cand-exec-1"
    assert report.top_1_result["outcome_status"] == "TARGET_HIT"
    assert [item["candidate_id"] for item in report.top_3_result["candidates"]] == ["cand-exec-1"]
    assert report.top_3_result["aggregate_cost_adjusted_r"] == pytest.approx(1.75)
    assert report.fallback_exclusion_summary["excluded_from_executable_count"] == 1
    assert report.feed_block_summary["blocked_count"] == 0

    json_path = tmp_path / "shadow" / "shadow_validation_latest.json"
    md_path = tmp_path / "shadow" / "shadow_validation_latest.md"
    session_path = tmp_path / "shadow" / "session_20260607.jsonl"
    assert json_path.exists()
    assert md_path.exists()
    assert session_path.exists()
    assert session_path.read_text(encoding="utf-8").strip()


def test_shadow_runner_top_1_and_top_3_results_are_edge_rank_ordered(tmp_path: Path) -> None:
    journal_path = tmp_path / "candidate_journal.jsonl"
    with journal_path.open("w", encoding="utf-8") as handle:
        for idx in range(1, 4):
            handle.write(json.dumps(_journal_row(candidate_id=f"cand-{idx}", trade_id=f"trade-{idx}")) + "\n")

    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records(
        [_candidate_outcome_row(f"cand-{idx}", f"trade-{idx}", 300, cost_adjusted_r=2.0 - idx * 0.25) for idx in range(1, 4)],
        path=outcomes_path,
    )

    top_dir = tmp_path / "top"
    write_top_opportunities_report(
        [
            _top_row("cand-3", "trade-3", edge_rank_score=0.99, rank_score=0.91),
            _top_row("cand-1", "trade-1", edge_rank_score=0.88, rank_score=0.81),
            _top_row("cand-2", "trade-2", edge_rank_score=0.77, rank_score=0.71),
        ],
        output_dir=top_dir,
    )

    from core.expectancy.shadow_validation import build_shadow_market_validation_report

    report = build_shadow_market_validation_report(
        candidate_journal=journal_path,
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=tmp_path / "shadow",
        session_date="20260607",
    )

    assert report.top_1_result["candidate_id"] == "cand-3"
    assert [item["candidate_id"] for item in report.top_3_result["candidates"]] == ["cand-3", "cand-1", "cand-2"]
    assert report.top_3_result["aggregate_cost_adjusted_r"] == pytest.approx((1.75 + 1.5 + 1.25) / 3)


def test_shadow_runner_handles_fallback_and_blocked_candidates_separately(tmp_path: Path) -> None:
    journal_path = tmp_path / "candidate_journal.jsonl"
    with journal_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_journal_row(candidate_id="cand-exec", trade_id="trade-exec")) + "\n")
        handle.write(json.dumps(_journal_row(candidate_id="cand-fallback", trade_id="softrej_trade-fallback", fallback_used=True, candidate_status="advisory_only", execution_status="advisory_only", permission="QUEUE_ONLY", final_action="QUEUE_ONLY", execution_allowed=False, reportable_executable=False)) + "\n")
        handle.write(json.dumps(_journal_row(candidate_id="cand-blocked", trade_id="trade-blocked", execution_status="blocked", candidate_status="advisory_only", permission="BLOCK", final_action="BLOCK", execution_allowed=False, reportable_executable=False, execution_truth_state="RECOVERY_BLOCKED", blockers=["STALE_OPTION_LTP"])) + "\n")

    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records(
        [
            _candidate_outcome_row("cand-exec", "trade-exec", 300),
            _candidate_outcome_row("cand-fallback", "softrej_trade-fallback", 300, fallback_used=True, outcome_status="NOT_EXECUTABLE", outcome_reason="fallback_not_executable", cost_adjusted_r=-1.0, gross_r=-1.0, target_hit=False, stop_hit=False, timeout_hit=False, blockers=["fallback_not_executable"]),
            _candidate_outcome_row("cand-blocked", "trade-blocked", 300, outcome_status="NOT_EXECUTABLE", outcome_reason="blocked", cost_adjusted_r=-2.0, gross_r=-2.0, target_hit=False, stop_hit=False, timeout_hit=False, blockers=["STALE_OPTION_LTP"]),
        ],
        path=outcomes_path,
    )

    top_dir = tmp_path / "top"
    write_top_opportunities_report(
        [
            _top_row("cand-exec", "trade-exec", edge_rank_score=0.95, rank_score=0.85),
            _top_row("cand-fallback", "softrej_trade-fallback", edge_rank_score=0.20, rank_score=0.10, fallback_used=True, expectancy_status="KEEP", permission="BLOCK", final_action="BLOCK", execution_allowed=False, reportable_executable=False, execution_truth_state="BLOCKED", blockers=["fallback_not_executable"]),
            _top_row("cand-blocked", "trade-blocked", edge_rank_score=0.10, rank_score=0.05, expectancy_status="KEEP", permission="BLOCK", final_action="BLOCK", execution_allowed=False, reportable_executable=False, execution_truth_state="RECOVERY_BLOCKED", blockers=["STALE_OPTION_LTP"]),
        ],
        output_dir=top_dir,
    )

    from core.expectancy.shadow_validation import build_shadow_market_validation_report

    report = build_shadow_market_validation_report(
        candidate_journal=journal_path,
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=tmp_path / "shadow",
        session_date="20260607",
    )

    assert report.fallback_count == 1
    assert report.blocked_count == 1
    assert report.executable_count == 1
    assert report.fallback_exclusion_summary["excluded_from_executable_count"] == 1
    assert report.feed_block_summary["blocked_count"] == 1


def test_shadow_runner_missing_files_fail_gracefully_with_diagnostic_report(tmp_path: Path) -> None:
    from core.expectancy.shadow_validation import build_shadow_market_validation_report

    report = build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=tmp_path / "missing-outcomes.jsonl",
        top_opportunities=tmp_path / "missing-top.json",
        output_dir=tmp_path / "shadow",
        session_date="20260607",
    )

    assert report.candidate_count == 0
    assert report.executable_count == 0
    assert report.recommendation in {"NO_TRADE", "PAPER_ONLY"}
    assert report.diagnostics["missing_inputs"]
    assert report.diagnostics["missing_inputs"] == [
        "candidate_journal",
        "candidate_outcomes",
        "top_opportunities",
    ]


def test_shadow_runner_cli_exits_zero_for_valid_fixture(tmp_path: Path) -> None:
    journal_path = tmp_path / "candidate_journal.jsonl"
    with journal_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_journal_row(candidate_id="cand-exec-1", trade_id="trade-exec-1")) + "\n")

    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records([_candidate_outcome_row("cand-exec-1", "trade-exec-1", 300)], path=outcomes_path)

    top_dir = tmp_path / "top"
    write_top_opportunities_report([_top_row("cand-exec-1", "trade-exec-1", edge_rank_score=0.95, rank_score=0.85)], output_dir=top_dir)

    out_dir = tmp_path / "shadow"
    exit_code = run_shadow_market_validation_main(
        [
            "--candidate-journal",
            str(journal_path),
            "--candidate-outcomes",
            str(outcomes_path),
            "--top-opportunities",
            str(top_dir / "top_opportunities_latest.json"),
            "--out-dir",
            str(out_dir),
            "--session-date",
            "20260607",
        ]
    )

    assert exit_code == 0
    assert (out_dir / "shadow_validation_latest.json").exists()
    assert (out_dir / "shadow_validation_latest.md").exists()


def test_shadow_runner_has_no_broker_or_order_imports() -> None:
    source = Path("core/expectancy/shadow_validation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    rendered = "\n".join(
        ",".join(alias.name for alias in node.names)
        for node in imports
    )
    assert "broker" not in rendered.lower()
    assert "order" not in rendered.lower()
