from __future__ import annotations

import json
import tarfile
from datetime import date
from pathlib import Path

from core.evidence_replay_report import (
    EvidenceReplayOptions,
    generate_evidence_replay_report,
    report_to_markdown,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _build_snapshot(root: Path) -> Path:
    snapshot = root / "runtime" / "evidence" / "live_diag_manual_20260522_143341"
    latest = snapshot / "runtime_latest"
    logs = snapshot / "runtime_logs"
    observation_ts_epoch = 1779441061.0

    _write_json(
        latest / "feed_runtime_latest.json",
        {
            "feed_ok": False,
            "effective_ws_connected": False,
            "last_error": "1006 websocket closed uncleanly",
            "last_tick_age_sec": 0.2,
            "option_last_tick_age_by_symbol": {"NIFTY": 0.2, "BANKNIFTY": 602128.0},
            "option_feed_block_reason_by_symbol": {"NIFTY": "OK", "BANKNIFTY": "quote_exceeds_threshold"},
            "ts_epoch": observation_ts_epoch,
        },
    )
    _write_json(
        latest / "freshness_latest.json",
        {
            "BANKNIFTY": {
                "symbol": "BANKNIFTY",
                "fresh": False,
                "freshness_reason": "quote_exceeds_threshold",
                "quote_age_sec": 602128.0,
                "freshness_threshold_sec": 900.0,
                "ts_epoch": observation_ts_epoch,
            },
            "NIFTY": {
                "symbol": "NIFTY",
                "fresh": True,
                "freshness_reason": "quote_within_threshold",
                "quote_age_sec": 1.0,
                "freshness_threshold_sec": 900.0,
                "ts_epoch": observation_ts_epoch,
            },
        },
    )
    _write_json(latest / "runtime_health_latest.json", {"status": "WARN", "ts_epoch": observation_ts_epoch})
    _write_json(
        latest / "top_opportunities_latest.json",
        {
            "top_executable_count": 0,
            "top_advisory_count": 0,
            "source_candidate_count": 0,
            "phase2_reason": "no_rankable_candidates",
            "selector_outcome": "NO_EXECUTABLE_OPPORTUNITY",
            "ts_epoch": observation_ts_epoch,
        },
    )
    _write_json(
        latest / "option_chain_latest.json",
        {
            "NIFTY": [
                {
                    "symbol": "NIFTY",
                    "tradingsymbol": "NIFTY26MAY26000CE",
                    "expiry": "2026-05-19",
                    "instrument_token": 123,
                    "quote_source": "live",
                    "quote_age_sec": 1.0,
                    "ts_epoch": observation_ts_epoch,
                }
            ]
        },
    )
    _write_json(
        latest / "token_resolution_latest.json",
        {
            "symbol": "NIFTY",
            "resolved_expiry": "2026-05-19",
            "instrument_token": 123,
            "resolution_path": "exact_contract_match",
            "ts_epoch": observation_ts_epoch,
        },
    )

    _write_jsonl(
        logs / "freshness_decisions_tail.jsonl",
        [
            {"symbol": "BANKNIFTY", "fresh": False, "reason": "quote_exceeds_threshold", "quote_age_sec": 602128.0, "ts_epoch": observation_ts_epoch},
            {"symbol": "NIFTY", "fresh": True, "reason": "quote_within_threshold", "quote_age_sec": 1.0, "ts_epoch": observation_ts_epoch},
        ],
    )
    _write_jsonl(
        logs / "rejected_candidates_tail.jsonl",
        [
            {
                "trade_id": "t1",
                "symbol": "BANKNIFTY",
                "candidate_status": "advisory_only",
                "execution_status": "advisory_only",
                "reject_reason": "no_signal",
                "quote_source": "rest_fallback",
                "execution_allowed": False,
                "ts_epoch": observation_ts_epoch,
            }
        ],
    )
    old_ts = 1778838935.651782
    _write_jsonl(
        logs / "execution_entry_trace_tail.jsonl",
        [
            {
                "trade_id": "t2",
                "symbol": "BANKNIFTY",
                "candidate_status": "queue_only",
                "execution_status": "non_executable",
                "quote_ts_epoch": old_ts,
                "quote_age_sec": 1.0,
                "quote_validation_status": "PRICE_MISMATCH",
                "quote_consistency_score": 0.0,
                "current_ltp": 731.75,
                "best_bid": 386.4,
                "best_ask": 387.45,
                "ts_epoch": observation_ts_epoch,
            }
        ],
    )
    _write_jsonl(logs / "trade_lifecycle_tail.jsonl", [{"trade_id": "t2", "stage": "review", "status": "blocked", "ts_epoch": observation_ts_epoch}])
    return snapshot


def test_generate_evidence_replay_report_detects_live_diag_failures(tmp_path):
    _build_snapshot(tmp_path)

    report = generate_evidence_replay_report(
        tmp_path,
        options=EvidenceReplayOptions(today=date(2026, 5, 22)),
    )

    assert report.snapshot_count == 1
    assert report.verdict == "NOT_READY_EXECUTION_TRUTH_FAILED"
    assert report.totals["feed_not_ok_snapshots"] == 1
    assert report.totals["zero_executable_snapshots"] == 1
    assert report.totals["expired_contract_count"] >= 1
    assert report.totals["quote_age_mismatch_count"] == 1
    assert report.totals["fallback_row_count"] == 1
    assert report.totals["price_mismatch_row_count"] == 1
    assert report.evidence_map["expired_contracts"] == "evidence_present"
    assert report.evidence_map["quote_age_mismatch"] == "evidence_present"
    assert "BANKNIFTY" in report.totals["symbols_with_stale_freshness"]


def test_generate_evidence_replay_report_supports_tar_gz(tmp_path):
    source_root = tmp_path / "source"
    _build_snapshot(source_root)
    bundle = tmp_path / "live_diag_20260522_evidence.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        archive.add(source_root / "runtime", arcname="runtime")

    report = generate_evidence_replay_report(
        bundle,
        options=EvidenceReplayOptions(today=date(2026, 5, 22)),
    )

    assert report.snapshot_count == 1
    assert report.totals["expired_contract_count"] >= 1
    assert report.source.endswith("live_diag_20260522_evidence.tar.gz")


def test_report_to_markdown_contains_verdict_and_evidence_map(tmp_path):
    _build_snapshot(tmp_path)
    report = generate_evidence_replay_report(
        tmp_path,
        options=EvidenceReplayOptions(today=date(2026, 5, 22)),
    )

    markdown = report_to_markdown(report)

    assert "EDGE-37 Evidence Replay Quality Report" in markdown
    assert "NOT_READY_EXECUTION_TRUTH_FAILED" in markdown
    assert "expired_contracts" in markdown
    assert "quote_age_mismatch" in markdown


def test_missing_files_are_reported_without_crashing(tmp_path):
    snapshot = tmp_path / "runtime" / "evidence" / "live_diag_manual_20260522_143341"
    (snapshot / "runtime_latest").mkdir(parents=True)
    (snapshot / "runtime_logs").mkdir(parents=True)
    _write_json(snapshot / "runtime_latest" / "top_opportunities_latest.json", {"top_executable_count": 0})

    report = generate_evidence_replay_report(
        tmp_path,
        options=EvidenceReplayOptions(today=date(2026, 5, 22)),
    )

    assert report.snapshot_count == 1
    snap = report.snapshots[0]
    assert "feed_runtime_latest.json" in snap.missing_latest_files
    assert "freshness_decisions_tail.jsonl" in snap.missing_log_tails
    assert report.totals["zero_executable_snapshots"] == 1
