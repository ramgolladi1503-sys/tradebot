from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.candidate_executability_evidence import (
    build_candidate_executability_evidence,
    report_to_payload,
    write_candidate_executability_evidence,
    write_candidate_executability_json_report,
    write_candidate_executability_markdown_report,
)


FIXTURE_DIR = Path("tests/fixtures/candidate_executability")
PR489_LIVE_EXCERPT = FIXTURE_DIR / "pr489_live_excerpt.log"
CLEAN_EXECUTABLE_COUNTEREXAMPLE = FIXTURE_DIR / "clean_executable_counterexample.log"


def test_parse_candidate_counts_by_symbol() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.total_symbols_seen == 3
    assert report.symbols == ("BANKNIFTY", "NIFTY", "SENSEX")
    assert report.raw_candidate_count_by_symbol["BANKNIFTY"] == 26
    assert report.post_scan_survivor_count_by_symbol["BANKNIFTY"] == 13
    assert report.real_candidate_count_by_symbol["BANKNIFTY"] == 26
    assert report.executable_candidate_count_by_symbol["BANKNIFTY"] == 2
    assert report.advisory_candidate_count_by_symbol["NIFTY"] == 9
    assert report.blocked_candidate_count_by_symbol["SENSEX"] == 2


def test_parse_top_candidate_status_and_execution_truth_blockers() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")
    row = next(candidate for candidate in report.top_candidates if candidate["symbol"] == "SENSEX")

    assert row["trade_id"] == "T-102"
    assert row["strategy_family"] == "mean_reversion"
    assert row["candidate_status"] == "blocked"
    assert row["execution_status"] == "blocked"
    assert row["execution_entry_status"] == "executable"
    assert row["permission"] == "BLOCK"
    assert row["final_action"] == "BLOCK"
    assert row["readiness"] == "BLOCKED"
    assert row["execution_allowed"] is False
    assert row["eligible_for_execution"] is False
    assert row["reportable_executable"] is False
    assert row["reason"] == "quote_truth_split_brain_reject"
    assert row["final_emit_block_reason"] == "STALE_OPTION_LTP"
    assert row["execution_truth_blockers"] == ["STALE_OPTION_LTP", "CONFIDENCE_RAW_GATE", "WS_DISCONNECTED"]


def test_parse_final_emit_abort_reasons() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.final_emit_block_reasons == ("STALE_OPTION_LTP",)
    assert any(row["final_emit_block_reason"] == "STALE_OPTION_LTP" for row in report.top_candidates)


def test_parse_phase2_hard_execution_drop_counts() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.phase2_drop_counts["HARD_EXECUTION"] == 4
    assert report.phase2_drop_counts["NO_VIABLE_CANDIDATES"] == 2


def test_parse_trade_builder_reject_counts() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.trade_builder_reject_counts["CONFIDENCE_RAW_GATE"] == 22
    assert report.trade_builder_reject_counts["NO_VIABLE_CANDIDATES"] == 7
    assert report.trade_builder_reject_counts["NO_CANDIDATES_SURVIVED"] == 5


def test_parse_latency_and_feed_blockers() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.feed_runtime_blockers["LATENCY_GUARD"] == 10
    assert report.feed_runtime_blockers["WS_DISCONNECTED"] == 4
    assert report.feed_runtime_blockers["GLOBAL_FEED_UNHEALTHY"] == 5
    assert report.feed_runtime_blockers["FEED_LTP_STALE"] == 10
    assert report.feed_runtime_blockers["FEED_DEPTH_STALE"] == 8
    assert report.feed_runtime_blockers["SLO_FAILOVER"] == 1
    assert report.feed_runtime_blockers["RISK_HALT"] == 3
    assert report.feed_runtime_blockers["LATENCY_BREACH"] == 2


def test_parse_quote_truth_split_brain_rejects() -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report.quote_truth_split_brain_count == 1
    assert report.quote_truth_split_brain_examples == (
        {
            "event": "QUOTE_TRUTH_SPLIT_BRAIN_REJECT",
            "symbol": "BANKNIFTY",
            "trade_id": "T-103",
            "current_ltp": 103.25,
            "best_bid": 103.0,
            "best_ask": 103.5,
            "reason": "quote_truth_split_brain_reject",
        },
    )


def test_dominant_blocker_is_stale_option_ltp_when_it_has_highest_count() -> None:
    report = build_candidate_executability_evidence(
        events=[
            {"event": "FINAL_EMIT_ABORT", "reason": "STALE_OPTION_LTP", "count": 3},
            {"event": "TB_REJECT_SUMMARY", "reason": "CONFIDENCE_RAW_GATE", "count": 2},
        ],
        source_name="synthetic_stale",
    )

    assert report.dominant_blocker is not None
    assert report.dominant_blocker["reason"] == "STALE_OPTION_LTP"
    assert report.top_blockers_ranked[0]["reason"] == "STALE_OPTION_LTP"
    assert report.recommended_next_pr_type == "STALE_OPTION_LTP_PROVENANCE"


def test_dominant_blocker_prefers_evidence_counts_over_hardcoded_order() -> None:
    report = build_candidate_executability_evidence(
        events=[
            {"event": "FINAL_EMIT_ABORT", "reason": "A_REASON"},
            {"event": "TB_REJECT_SUMMARY", "reason": "B_REASON", "count": 3},
        ],
        source_name="synthetic",
    )

    assert report.dominant_blocker is not None
    assert report.dominant_blocker["reason"] == "B_REASON"
    assert report.top_blockers_ranked[0]["reason"] == "B_REASON"
    assert report.top_blockers_ranked[0]["count"] == 3


def test_report_is_deterministic() -> None:
    report_one = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")
    report_two = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")

    assert report_to_payload(report_one) == report_to_payload(report_two)


def test_markdown_report_contains_no_order_actions(tmp_path: Path) -> None:
    report = build_candidate_executability_evidence(log_file=PR489_LIVE_EXCERPT, source_name="pr489_live_excerpt")
    markdown_path = write_candidate_executability_markdown_report(report, tmp_path / "candidate_executability_summary.md")

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "This report is read-only and does not authorize any order action." in markdown
    assert "read_only: True" in markdown
    assert "append: False" in markdown
    assert "is_order_action: False" in markdown
    assert "broker_api_called: False" in markdown


def test_cli_writes_json_and_markdown_to_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/write_candidate_executability_evidence.py",
            "--log-file",
            str(PR489_LIVE_EXCERPT),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    json_path = output_dir / "candidate_executability_summary.json"
    markdown_path = output_dir / "candidate_executability_summary.md"
    assert json_path.exists()
    assert markdown_path.exists()
    assert str(json_path) in proc.stdout
    assert str(markdown_path) in proc.stdout

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False
    assert payload["quote_truth_split_brain_examples"]


def test_clean_executable_counterexample_not_misclassified_as_blocked() -> None:
    report = build_candidate_executability_evidence(log_file=CLEAN_EXECUTABLE_COUNTEREXAMPLE, source_name="clean_executable_counterexample")

    assert report.raw_candidate_count_by_symbol["NIFTY"] == 8
    assert report.post_scan_survivor_count_by_symbol["NIFTY"] == 6
    assert report.executable_candidate_count_by_symbol["NIFTY"] == 2
    assert report.blocked_candidate_count_by_symbol.get("NIFTY", 0) == 0
    assert report.top_candidates[0]["candidate_status"] == "executable"
    assert report.top_candidates[0]["reportable_executable"] is True
    assert report.dominant_blocker is None
    assert report.final_emit_block_reasons == ()
    assert report.quote_truth_split_brain_count == 0


def test_write_candidate_executability_evidence_writes_both_files(tmp_path: Path) -> None:
    json_path, markdown_path, report = write_candidate_executability_evidence(
        log_file=PR489_LIVE_EXCERPT,
        output_dir=tmp_path,
        source_name="pr489_live_excerpt",
    )

    assert json_path.exists()
    assert markdown_path.exists()
    assert json_path.name == "candidate_executability_summary.json"
    assert markdown_path.name == "candidate_executability_summary.md"
    assert report.read_only is True
    assert report.append is False
    assert report.is_order_action is False
    assert report.broker_api_called is False
    assert report.live_order_allowed is False
