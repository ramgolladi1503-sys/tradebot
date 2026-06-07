from __future__ import annotations

import json
from pathlib import Path

from core.expectancy.top_opportunity_selector import (
    TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION,
    select_top_opportunities,
    write_top_opportunities_report,
)


def _row(**overrides):
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "strategy_family": "breakout",
        "setup_id": "breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE",
        "regime": "LIVE",
        "direction": "BUY",
        "edge_rank_score": 0.81,
        "rank_score": 0.69,
        "confidence_final": 0.72,
        "expectancy_status": "KEEP",
        "expectancy_sample_count": 52,
        "expectancy_avg_cost_adjusted_r": 0.20,
        "execution_truth_state": "EXEMPLAR",
        "reportable_executable": True,
        "execution_allowed": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "fallback_used": False,
        "why_ranked": "",
        "why_not_ranked": "",
        "blockers": [],
    }
    row.update(overrides)
    return row


def test_top_executable_contains_only_keep_executable_candidates():
    rows = [
        _row(candidate_id="cand-exec", trade_id="trade-exec", edge_rank_score=0.92),
        _row(
            candidate_id="cand-watch",
            trade_id="trade-watch",
            expectancy_status="WATCH",
            permission="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            execution_allowed=False,
            reportable_executable=False,
            edge_rank_score=0.70,
        ),
        _row(
            candidate_id="cand-kill",
            trade_id="trade-kill",
            expectancy_status="KILL",
            permission="BLOCK",
            final_action="BLOCK",
            execution_allowed=False,
            reportable_executable=False,
            edge_rank_score=0.0,
        ),
    ]

    report = select_top_opportunities(rows)

    assert report.schema_version == TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION
    assert report.executable_count == 1
    assert [row.candidate_id for row in report.executable_opportunities] == ["cand-exec"]
    assert report.executable_opportunities[0].expectancy_status == "KEEP"
    assert report.executable_opportunities[0].permission == "EXECUTE"
    assert report.executable_opportunities[0].final_action == "EXECUTE"


def test_watch_appears_in_advisory_not_executable():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-watch", trade_id="trade-watch", expectancy_status="WATCH", permission="QUEUE_ONLY", final_action="QUEUE_ONLY", execution_allowed=False, reportable_executable=False, edge_rank_score=0.61),
        ]
    )

    assert report.advisory_count == 1
    assert [row.candidate_id for row in report.advisory_opportunities] == ["cand-watch"]
    assert report.executable_count == 0


def test_kill_excluded_from_executable_and_shown_in_rejected_summary():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-kill", trade_id="trade-kill", expectancy_status="KILL", permission="BLOCK", final_action="BLOCK", execution_allowed=False, reportable_executable=False, edge_rank_score=0.0),
        ]
    )

    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert "expectancy_kill" in report.rejected_opportunities[0].why_not_ranked


def test_fallback_excluded_from_executable():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-fallback", trade_id="softrej_trade-1", fallback_used=True, expectancy_status="KEEP", edge_rank_score=0.91),
        ]
    )

    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert "fallback_not_rankable" in report.rejected_opportunities[0].why_not_ranked


def test_blocked_and_stale_excluded_from_executable():
    report = select_top_opportunities(
        [
            _row(
                candidate_id="cand-blocked",
                trade_id="trade-blocked",
                expectancy_status="KEEP",
                execution_truth_state="RECOVERY_BLOCKED",
                permission="BLOCK",
                final_action="BLOCK",
                execution_allowed=False,
                reportable_executable=False,
                blockers=["STALE_OPTION_LTP"],
                edge_rank_score=0.0,
            ),
        ]
    )

    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert "blockers=" in report.rejected_opportunities[0].why_not_ranked


def test_ranking_is_sorted_by_edge_rank_score_desc():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-low", trade_id="trade-low", edge_rank_score=0.45),
            _row(candidate_id="cand-high", trade_id="trade-high", edge_rank_score=0.91),
            _row(candidate_id="cand-mid", trade_id="trade-mid", edge_rank_score=0.72),
        ]
    )

    assert [row.candidate_id for row in report.executable_opportunities] == ["cand-high", "cand-mid", "cand-low"]
    assert [row.rank for row in report.executable_opportunities] == [1, 2, 3]


def test_ties_are_resolved_deterministically_by_symbol_and_trade_id():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-b", trade_id="trade-b", symbol="BANKNIFTY", edge_rank_score=0.77, rank_score=0.66, confidence_final=0.64),
            _row(candidate_id="cand-a", trade_id="trade-a", symbol="NIFTY", edge_rank_score=0.77, rank_score=0.66, confidence_final=0.64),
            _row(candidate_id="cand-c", trade_id="trade-c", symbol="NIFTY", edge_rank_score=0.77, rank_score=0.66, confidence_final=0.64),
        ]
    )

    assert [row.trade_id for row in report.executable_opportunities] == ["trade-b", "trade-a", "trade-c"]


def test_duplicate_candidates_do_not_dominate_when_diverse_alternatives_exist():
    report = select_top_opportunities(
        [
            _row(candidate_id="cand-dup-1", trade_id="trade-dup-1", symbol="NIFTY", strategy_family="breakout", edge_rank_score=0.84, rank_score=0.71, confidence_final=0.73),
            _row(candidate_id="cand-dup-2", trade_id="trade-dup-2", symbol="NIFTY", strategy_family="breakout", edge_rank_score=0.83, rank_score=0.70, confidence_final=0.72),
            _row(candidate_id="cand-bear", trade_id="trade-bear", symbol="BANKNIFTY", strategy_family="mean_reversion", direction="SELL", edge_rank_score=0.82, rank_score=0.74, confidence_final=0.75),
            _row(candidate_id="cand-range", trade_id="trade-range", symbol="FINNIFTY", strategy_family="range", direction="BUY", edge_rank_score=0.81, rank_score=0.73, confidence_final=0.74),
        ]
    )

    executable_ids = [row.candidate_id for row in report.executable_opportunities]
    assert executable_ids[0] == "cand-bear"
    assert "cand-range" in executable_ids[:3]
    assert report.executable_opportunities[0].why_ranked.startswith("expectancy=keep")
    assert report.executable_opportunities[0].why_ranked


def test_why_ranked_includes_expectancy_and_execution_quality():
    report = select_top_opportunities([_row(candidate_id="cand-exec", trade_id="trade-exec")])

    why_ranked = report.executable_opportunities[0].why_ranked
    assert "expectancy=keep" in why_ranked
    assert "edge_rank_score=" in why_ranked
    assert "rank_score=" in why_ranked
    assert "confidence_final=" in why_ranked
    assert "execution_eligible" in why_ranked


def test_why_not_ranked_includes_blocker_reason():
    report = select_top_opportunities(
        [
            _row(
                candidate_id="cand-watch",
                trade_id="trade-watch",
                expectancy_status="WATCH",
                permission="QUEUE_ONLY",
                final_action="QUEUE_ONLY",
                execution_allowed=False,
                reportable_executable=False,
                blockers=["STALE_OPTION_LTP"],
                edge_rank_score=0.70,
            )
        ]
    )

    why_not_ranked = report.advisory_opportunities[0].why_not_ranked
    assert "expectancy_watch" in why_not_ranked
    assert "blockers=STALE_OPTION_LTP" in why_not_ranked


def test_markdown_json_reports_generated(tmp_path: Path):
    report = select_top_opportunities([_row(candidate_id="cand-exec", trade_id="trade-exec")])
    json_path, md_path, emitted = write_top_opportunities_report([_row(candidate_id="cand-exec", trade_id="trade-exec")], output_dir=tmp_path)

    assert emitted.schema_version == TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["schema_version"] == TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION
    assert payload["executable_count"] == 1
    assert payload["executable_opportunities"][0]["candidate_id"] == "cand-exec"
    markdown = md_path.read_text()
    assert "Top Opportunity Selector Report" in markdown
    assert "## Executable Opportunities" in markdown
    assert "This report is read-only and does not change execution behavior." in markdown
    assert report.executable_count == 1
