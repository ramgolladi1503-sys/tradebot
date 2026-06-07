from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.expectancy.shadow_validation import build_shadow_market_validation_report
from core.expectancy.strategy_regime_expectancy import write_strategy_regime_expectancy_report
from core.expectancy.top_opportunity_selector import write_top_opportunities_report
from core.candidate_outcome_tracker import write_candidate_outcome_records
from scripts.write_edge_readiness_report import main as write_edge_readiness_report_main


def _outcome_row(candidate_id: str, trade_id: str, *, window_sec: int = 300, status: str = "TARGET_HIT", cost_adjusted_r: float = 1.5, fallback_used: bool = False) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "trade_id": trade_id,
        "strategy_family": "breakout",
        "regime": "LIVE",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "window_sec": window_sec,
        "outcome_status": status,
        "outcome_reason": status.lower(),
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "gross_r": cost_adjusted_r + 0.25,
        "estimated_cost_r": 0.25,
        "cost_adjusted_r": cost_adjusted_r,
        "target_hit": status == "TARGET_HIT",
        "stop_hit": status == "STOP_HIT",
        "timeout_hit": status == "TIMEOUT",
        "first_hit_epoch": 120.0,
        "observation_count": 2,
        "fallback_used": fallback_used,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


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


def _expectancy_row(strategy_family: str, regime: str, index: str, expiry_type: str, option_type: str, direction: str, sample_count: int, avg_cost_adjusted_r: float, status: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "group_key": f"{strategy_family}|{regime}|{index}|{expiry_type}|{option_type}|{direction}",
        "strategy_family": strategy_family,
        "regime": regime,
        "index": index,
        "expiry_type": expiry_type,
        "option_type": option_type,
        "direction": direction,
        "sample_count": sample_count,
        "executable_count": sample_count,
        "not_executable_count": 0,
        "win_count": sample_count,
        "loss_count": 0,
        "timeout_count": 0,
        "target_hit_count": sample_count,
        "stop_hit_count": 0,
        "win_rate": 1.0,
        "avg_gross_r": avg_cost_adjusted_r + 0.25,
        "avg_cost_adjusted_r": avg_cost_adjusted_r,
        "median_cost_adjusted_r": avg_cost_adjusted_r,
        "total_cost_adjusted_r": avg_cost_adjusted_r * sample_count,
        "target_hit_rate": 1.0,
        "stop_hit_rate": 0.0,
        "timeout_rate": 0.0,
        "max_drawdown_r": 0.0,
        "fallback_excluded_count": 0,
        "blocked_excluded_count": 0,
        "keep_watch_kill_status": status,
        "status_reason": "sample_count_below_threshold" if status == "INSUFFICIENT_DATA" else "positive_expectancy" if status == "KEEP" else "negative_expectancy",
        "read_only": True,
        "append": False,
    }


def _write_positive_fixture_bundle(tmp_path: Path, *, include_fallback: bool = False) -> tuple[Path, Path, Path]:
    expectancy_path = tmp_path / "strategy_regime_expectancy_latest.json"
    expectancy_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_by": "strategy_regime_expectancy_aggregator",
        "source": "fixture",
        "candidate_outcome_count": 50,
        "group_count": 1,
        "groups": [_expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "CE", "BUY", 50, 0.25, "KEEP")],
        "read_only": True,
        "append": False,
    }, indent=2), encoding="utf-8")

    top_rows: list[dict[str, object]] = [
        _top_row(
            f"cand-{idx}",
            f"trade-{idx}",
            edge_rank_score=0.95 - idx * 0.01,
            rank_score=0.8 - idx * 0.01,
            execution_truth_state="EXEMPLAR",
            reportable_executable=True,
            execution_allowed=True,
            permission="EXECUTE",
            final_action="EXECUTE",
        )
        for idx in range(1, 51)
    ]
    if include_fallback:
        top_rows.append(
            _top_row(
                "cand-fallback",
                "softrej_trade-1",
                edge_rank_score=0.01,
                rank_score=0.01,
                expectancy_status="KEEP",
                fallback_used=True,
                permission="BLOCK",
                final_action="BLOCK",
                execution_allowed=False,
                reportable_executable=False,
                execution_truth_state="BLOCKED",
                blockers=["fallback_not_executable"],
            )
        )

    top_dir = tmp_path / "top"
    write_top_opportunities_report(top_rows, output_dir=top_dir)

    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    outcome_rows = [
        _outcome_row(f"cand-{idx}", f"trade-{idx}", cost_adjusted_r=0.25)
        for idx in range(1, 51)
    ]
    if include_fallback:
        outcome_rows.append(_outcome_row("cand-fallback", "softrej_trade-1", cost_adjusted_r=0.35, fallback_used=True))
    write_candidate_outcome_records(outcome_rows, path=outcomes_path)

    shadow_dir = tmp_path / "shadow"
    build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=shadow_dir,
        session_date="20260607",
    )
    return expectancy_path, top_dir / "top_opportunities_latest.json", shadow_dir / "shadow_validation_latest.json"


def test_negative_expectancy_returns_no_trade(tmp_path: Path) -> None:
    expectancy_path = tmp_path / "strategy_regime_expectancy_latest.json"
    expectancy_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_by": "strategy_regime_expectancy_aggregator",
        "source": "fixture",
        "candidate_outcome_count": 1,
        "group_count": 1,
        "groups": [_expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "CE", "BUY", 50, -0.25, "KILL")],
        "read_only": True,
        "append": False,
    }, indent=2), encoding="utf-8")
    top_dir = tmp_path / "top"
    write_top_opportunities_report([_top_row("cand-1", "trade-1", edge_rank_score=0.9, rank_score=0.8)], output_dir=top_dir)
    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records([_outcome_row("cand-1", "trade-1", cost_adjusted_r=-0.25)], path=outcomes_path)
    shadow_dir = tmp_path / "shadow"
    build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=shadow_dir,
        session_date="20260607",
    )

    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_dir / "top_opportunities_latest.json",
        shadow_validation_path=shadow_dir / "shadow_validation_latest.json",
    )

    assert report.recommendation == "NO_TRADE"
    assert "negative" in report.recommendation_reason.lower()


def test_insufficient_samples_returns_paper_only(tmp_path: Path) -> None:
    expectancy_path = tmp_path / "strategy_regime_expectancy_latest.json"
    expectancy_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_by": "strategy_regime_expectancy_aggregator",
        "source": "fixture",
        "candidate_outcome_count": 1,
        "group_count": 1,
        "groups": [_expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "CE", "BUY", 12, 0.15, "INSUFFICIENT_DATA")],
        "read_only": True,
        "append": False,
    }, indent=2), encoding="utf-8")
    top_dir = tmp_path / "top"
    write_top_opportunities_report([_top_row("cand-1", "trade-1", edge_rank_score=0.9, rank_score=0.8)], output_dir=top_dir)
    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records([_outcome_row("cand-1", "trade-1", cost_adjusted_r=0.15)], path=outcomes_path)
    shadow_dir = tmp_path / "shadow"
    build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=shadow_dir,
        session_date="20260607",
    )

    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_dir / "top_opportunities_latest.json",
        shadow_validation_path=shadow_dir / "shadow_validation_latest.json",
    )

    assert report.recommendation == "PAPER_ONLY"
    assert "insufficient" in report.recommendation_reason.lower()


def test_mature_positive_expectancy_returns_ready_for_manual_pilot(tmp_path: Path) -> None:
    expectancy_path, top_path, shadow_path = _write_positive_fixture_bundle(tmp_path)

    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_path,
        shadow_validation_path=shadow_path,
    )

    assert report.recommendation == "READY_FOR_MANUAL_PILOT"
    assert report.expectancy_summary["keep_count"] == 1
    assert report.shadow_validation_summary["positive"] is True


def test_fallback_inflated_result_never_returns_ready(tmp_path: Path) -> None:
    expectancy_path, top_path, shadow_path = _write_positive_fixture_bundle(tmp_path, include_fallback=True)

    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_path,
        shadow_validation_path=shadow_path,
    )

    assert report.recommendation != "READY_FOR_MANUAL_PILOT"
    assert "fallback" in report.recommendation_reason.lower()


def test_all_mature_baseline_weak_returns_paper_only(tmp_path: Path) -> None:
    expectancy_path = tmp_path / "strategy_regime_expectancy_latest.json"
    expectancy_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_by": "strategy_regime_expectancy_aggregator",
        "source": "fixture",
        "candidate_outcome_count": 80,
        "group_count": 2,
        "groups": [
            _expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "CE", "BUY", 50, 0.26, "KEEP"),
            _expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "PE", "BUY", 50, 0.24, "KEEP"),
        ],
        "baseline_comparison_summary": {
            "comparison_count": 2,
            "outperform_count": 0,
            "match_count": 0,
            "underperform_count": 2,
            "insufficient_sample_count": 0,
            "mature_group_count": 2,
            "mature_outperform_count": 0,
            "mature_match_count": 0,
            "mature_underperform_count": 2,
            "mature_insufficient_sample_count": 0,
            "all_mature_groups_below_baseline_or_insufficient": True,
        },
        "baseline_comparisons": [
            {
                "baseline_verdict": "UNDERPERFORMS",
                "sample_count": 50,
            },
            {
                "baseline_verdict": "UNDERPERFORMS",
                "sample_count": 50,
            },
        ],
        "read_only": True,
        "append": False,
    }, indent=2), encoding="utf-8")
    top_dir = tmp_path / "top"
    write_top_opportunities_report([_top_row("cand-1", "trade-1", edge_rank_score=0.95, rank_score=0.8)], output_dir=top_dir)
    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records([_outcome_row("cand-1", "trade-1", cost_adjusted_r=0.26)], path=outcomes_path)
    shadow_dir = tmp_path / "shadow"
    build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=shadow_dir,
        session_date="20260607",
    )

    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_dir / "top_opportunities_latest.json",
        shadow_validation_path=shadow_dir / "shadow_validation_latest.json",
    )

    assert report.recommendation == "PAPER_ONLY"
    assert any(token in report.recommendation_reason.lower() for token in {"below-baseline", "insufficient"})


def test_missing_input_files_fail_closed_to_no_trade_or_paper_only_with_explicit_reason(tmp_path: Path) -> None:
    from core.expectancy.edge_readiness_report import build_edge_readiness_report

    report = build_edge_readiness_report(
        expectancy_path=tmp_path / "missing-expectancy.json",
        top_opportunities_path=tmp_path / "missing-top.json",
        shadow_validation_path=tmp_path / "missing-shadow.json",
    )

    assert report.recommendation in {"NO_TRADE", "PAPER_ONLY"}
    assert report.missing_inputs == ["expectancy", "top_opportunities", "shadow_validation"]
    assert report.recommendation_reason


def test_markdown_and_json_reports_generated(tmp_path: Path) -> None:
    expectancy_path = tmp_path / "strategy_regime_expectancy_latest.json"
    expectancy_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_by": "strategy_regime_expectancy_aggregator",
        "source": "fixture",
        "candidate_outcome_count": 1,
        "group_count": 1,
        "groups": [_expectancy_row("breakout", "LIVE", "NIFTY", "WEEKLY", "CE", "BUY", 50, 0.25, "KEEP")],
        "read_only": True,
        "append": False,
    }, indent=2), encoding="utf-8")
    top_dir = tmp_path / "top"
    write_top_opportunities_report([_top_row("cand-1", "trade-1", edge_rank_score=0.95, rank_score=0.8)], output_dir=top_dir)
    outcomes_path = tmp_path / "candidate_outcomes.jsonl"
    write_candidate_outcome_records([_outcome_row("cand-1", "trade-1", cost_adjusted_r=0.25)], path=outcomes_path)
    shadow_dir = tmp_path / "shadow"
    build_shadow_market_validation_report(
        candidate_journal=tmp_path / "missing-journal.jsonl",
        candidate_outcomes=outcomes_path,
        top_opportunities=top_dir / "top_opportunities_latest.json",
        output_dir=shadow_dir,
        session_date="20260607",
    )

    from core.expectancy.edge_readiness_report import write_edge_readiness_report

    json_path, md_path, report = write_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_dir / "top_opportunities_latest.json",
        shadow_validation_path=shadow_dir / "shadow_validation_latest.json",
        output_dir=tmp_path / "reports",
        mirror_runtime=True,
    )

    assert json_path.exists()
    assert md_path.exists()
    assert report.recommendation in {"READY_FOR_MANUAL_PILOT", "PAPER_ONLY", "NO_TRADE"}
    assert "Executive verdict" in md_path.read_text(encoding="utf-8")
    assert "Recommendation" in md_path.read_text(encoding="utf-8")


def test_no_broker_order_imports() -> None:
    source = Path("core/expectancy/edge_readiness_report.py").read_text(encoding="utf-8")
    assert "broker" not in source.lower()
    forbidden_markers = (
        "place" + "_" + "order",
        "modify" + "_" + "order",
        "cancel" + "_" + "order",
        "exit" + "_" + "order",
        "kite." + "place" + "_" + "order",
        "broker." + "place" + "_" + "order",
    )
    assert all(marker not in source for marker in forbidden_markers)
