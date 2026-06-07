from __future__ import annotations

import json
from pathlib import Path

from core.expectancy.topn_replay_quality import (
    TOPN_VERDICT_INSUFFICIENT_SAMPLE,
    TOPN_VERDICT_MATCHES,
    TOPN_VERDICT_OUTPERFORMS,
    TOPN_VERDICT_UNDERPERFORMS,
    build_topn_replay_quality_report,
    write_topn_replay_quality_report,
)
from core.expectancy.top_opportunity_selector import write_top_opportunities_report
from core.candidate_outcome_tracker import write_candidate_outcome_records
from scripts.run_topn_replay_quality import main as run_topn_replay_quality_main


def _top_row(
    candidate_id: str,
    trade_id: str,
    *,
    edge_rank_score: float,
    rank_score: float,
    regime: str | None = "LIVE",
    expectancy_status: str = "KEEP",
    fallback_used: bool = False,
    execution_truth_state: str = "EXEMPLAR",
    reportable_executable: bool = True,
    execution_allowed: bool = True,
    permission: str = "EXECUTE",
    final_action: str = "EXECUTE",
    blockers: list[str] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "candidate_id": candidate_id,
        "trade_id": trade_id,
        "symbol": "NIFTY",
        "index": "NIFTY",
        "strategy_family": "breakout",
        "setup_id": f"setup-{candidate_id}",
        "direction": "BUY",
        "edge_rank_score": edge_rank_score,
        "rank_score": rank_score,
        "confidence_final": 0.9,
        "expectancy_status": expectancy_status,
        "expectancy_sample_count": 50,
        "expectancy_avg_cost_adjusted_r": 0.25,
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
    if regime is not None:
        row["regime"] = regime
    return row


def _outcome_row(candidate_id: str, trade_id: str, *, cost_adjusted_r: float, gross_r: float | None = None) -> dict[str, object]:
    gross = gross_r if gross_r is not None else cost_adjusted_r + 0.20
    return {
        "candidate_id": candidate_id,
        "trade_id": trade_id,
        "strategy_family": "breakout",
        "regime": "LIVE",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "window_sec": 300,
        "outcome_status": "TARGET_HIT" if cost_adjusted_r >= 0 else "STOP_HIT",
        "outcome_reason": "fixture",
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "gross_r": gross,
        "estimated_cost_r": gross - cost_adjusted_r,
        "cost_adjusted_r": cost_adjusted_r,
        "target_hit": cost_adjusted_r >= 0,
        "stop_hit": cost_adjusted_r < 0,
        "timeout_hit": False,
        "first_hit_epoch": 120.0,
        "observation_count": 3,
        "fallback_used": False,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _write_bundle(
    tmp_path: Path,
    *,
    values: list[float],
    regimes: list[str | None] | None = None,
    fallback_rows: int = 0,
    blocked_rows: int = 0,
    missing_outcome_indices: set[int] | None = None,
) -> tuple[Path, Path]:
    top_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    missing_outcome_indices = missing_outcome_indices or set()
    for idx, value in enumerate(values, start=1):
        regime = regimes[idx - 1] if regimes is not None and idx - 1 < len(regimes) else "LIVE"
        top_rows.append(
            _top_row(
                f"cand-{idx}",
                f"trade-{idx}",
                edge_rank_score=1.0 - idx * 0.01,
                rank_score=0.9 - idx * 0.01,
                regime=regime,
            )
        )
        if idx not in missing_outcome_indices:
            outcome_rows.append(_outcome_row(f"cand-{idx}", f"trade-{idx}", cost_adjusted_r=value, gross_r=value + 0.20))
    next_idx = len(values)
    for extra in range(1, fallback_rows + 1):
        next_idx += 1
        top_rows.append(
            _top_row(
                f"cand-fallback-{extra}",
                f"softrej_trade-{extra}",
                edge_rank_score=0.01,
                rank_score=0.01,
                fallback_used=True,
                execution_truth_state="BLOCKED",
                reportable_executable=False,
                execution_allowed=False,
                permission="BLOCK",
                final_action="BLOCK",
                blockers=["fallback_not_executable"],
            )
        )
        outcome_rows.append(_outcome_row(f"cand-fallback-{extra}", f"softrej_trade-{extra}", cost_adjusted_r=0.30, gross_r=0.50))
    for extra in range(1, blocked_rows + 1):
        next_idx += 1
        top_rows.append(
            _top_row(
                f"cand-blocked-{extra}",
                f"blocked_trade-{extra}",
                edge_rank_score=0.005,
                rank_score=0.005,
                fallback_used=False,
                execution_truth_state="BLOCKED",
                reportable_executable=False,
                execution_allowed=False,
                permission="BLOCK",
                final_action="BLOCK",
                blockers=["ws1006_process_restart_required"],
            )
        )
        outcome_rows.append(_outcome_row(f"cand-blocked-{extra}", f"blocked_trade-{extra}", cost_adjusted_r=0.05, gross_r=0.25))
    top_dir = tmp_path / "top"
    top_path, _, _ = write_top_opportunities_report(top_rows, output_dir=top_dir)
    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records(outcome_rows, path=outcomes_path)
    return top_path, outcomes_path


def test_top1_outperforms_lower_ranks_and_baseline_returns_outperforms(tmp_path: Path) -> None:
    values = [0.62, 0.55, 0.52, 0.18, 0.17, 0.12, 0.11, 0.10, 0.09, 0.08] + [0.05] * 20
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_OUTPERFORMS
    assert report.sample_count == 30
    assert report.top_1_after_cost_expectancy > report.top_5_after_cost_expectancy
    assert report.top_3_after_cost_expectancy > report.top_10_after_cost_expectancy
    assert report.average_return_after_cost > 0
    assert report.top_1_vs_top_5_delta > 0
    assert report.top_3_vs_top_10_delta > 0


def test_top3_outperforms_naive_baseline_when_other_conditions_are_equal(tmp_path: Path) -> None:
    values = [0.30, 0.28, 0.27] + [0.12] * 27
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_OUTPERFORMS
    assert report.top_3_vs_baseline_delta > 0
    assert report.top_3_after_cost_expectancy > report.naive_baseline_after_cost_expectancy


def test_topn_underperforming_after_cost_returns_underperforms(tmp_path: Path) -> None:
    values = [-0.08, -0.07, -0.06, -0.04, -0.03, -0.02, -0.01, -0.01, -0.01, -0.01] + [-0.02] * 20
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_UNDERPERFORMS
    assert report.average_return_after_cost <= 0
    assert report.top_1_vs_top_5_delta <= 0


def test_matches_when_signal_gaps_are_small(tmp_path: Path) -> None:
    values = [0.12, 0.121, 0.119, 0.123, 0.118, 0.122, 0.12, 0.119, 0.121, 0.12] + [0.12] * 20
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_MATCHES
    assert abs(report.top_1_vs_top_5_delta) <= 0.03
    assert abs(report.top_3_vs_top_10_delta) <= 0.03


def test_insufficient_sample_returns_insufficient_sample(tmp_path: Path) -> None:
    values = [0.22] * 12
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_INSUFFICIENT_SAMPLE
    assert report.sample_count == 12


def test_regime_specific_samples_are_handled_separately_and_missing_regime_falls_back_conservatively(tmp_path: Path) -> None:
    values = [0.30, 0.28, 0.27, 0.24, 0.22, 0.20, 0.18, 0.17, 0.16, 0.15] + [0.10] * 20 + [0.14, 0.13, 0.12, 0.11, 0.10]
    regimes = ["LIVE"] * 30 + [None] * 5
    top_path, outcomes_path = _write_bundle(tmp_path, values=values, regimes=regimes)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert "LIVE" in report.regime_breakdown
    assert "UNKNOWN" in report.regime_breakdown
    assert report.regime_breakdown["LIVE"]["sample_count"] >= 30
    assert report.regime_breakdown["UNKNOWN"]["verdict"] == TOPN_VERDICT_INSUFFICIENT_SAMPLE


def test_fallback_and_blocked_candidates_are_excluded_from_executable_summary(tmp_path: Path) -> None:
    values = [0.40, 0.36, 0.34, 0.20, 0.18, 0.16, 0.14, 0.12, 0.11, 0.10] + [0.06] * 20
    top_path, outcomes_path = _write_bundle(tmp_path, values=values, fallback_rows=1, blocked_rows=1)

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_OUTPERFORMS
    assert report.fallback_count == 1
    assert report.blocked_count == 1
    assert report.eligible_count == 30
    assert report.sample_count == 30


def test_gross_positive_but_after_cost_negative_does_not_pass(tmp_path: Path) -> None:
    values = [-0.05] * 30
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)
    payload = json.loads(outcomes_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["gross_r"] > 0
    assert payload["cost_adjusted_r"] < 0

    report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)

    assert report.verdict == TOPN_VERDICT_UNDERPERFORMS
    assert report.average_return_after_cost < 0


def test_missing_files_fail_gracefully_with_diagnostic_report(tmp_path: Path) -> None:
    report = build_topn_replay_quality_report(
        candidate_outcomes=tmp_path / "missing-outcomes.jsonl",
        top_opportunities=tmp_path / "missing-top.json",
    )

    assert report.verdict == TOPN_VERDICT_INSUFFICIENT_SAMPLE
    assert "candidate_outcomes" in report.missing_inputs
    assert "top_opportunities" in report.missing_inputs


def test_output_is_deterministic_and_cli_exits_zero_for_valid_fixture(tmp_path: Path) -> None:
    values = [0.45, 0.40, 0.35, 0.24, 0.22, 0.18, 0.16, 0.14, 0.12, 0.10] + [0.08] * 20
    top_path, outcomes_path = _write_bundle(tmp_path, values=values)
    out_dir = tmp_path / "report"

    json_path, md_path, report = write_topn_replay_quality_report(
        candidate_outcomes=outcomes_path,
        top_opportunities=top_path,
        output_dir=out_dir,
        mirror_runtime=True,
    )
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload == report.to_payload()
    second_report = build_topn_replay_quality_report(candidate_outcomes=outcomes_path, top_opportunities=top_path)
    assert second_report.to_payload() == report.to_payload()
    exit_code = run_topn_replay_quality_main(
        [
            "--candidate-outcomes",
            str(outcomes_path),
            "--top-opportunities",
            str(top_path),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0


def test_no_broker_order_imports() -> None:
    source = Path("core/expectancy/topn_replay_quality.py").read_text(encoding="utf-8")
    forbidden_markers = (
        "place" + "_" + "order",
        "modify" + "_" + "order",
        "cancel" + "_" + "order",
        "exit" + "_" + "order",
        "kite." + "place" + "_" + "order",
        "broker." + "place" + "_" + "order",
    )
    assert all(marker not in source for marker in forbidden_markers)
