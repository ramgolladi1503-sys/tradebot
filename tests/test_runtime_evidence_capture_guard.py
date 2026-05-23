from __future__ import annotations

import json
import tarfile
from datetime import date
from pathlib import Path

from core.runtime_evidence_capture_guard import (
    REQUIRED_CAPTURE_SECTIONS,
    RuntimeEvidenceCaptureOptions,
    generate_runtime_evidence_capture_guard_report,
    runtime_evidence_capture_guard_to_markdown,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _build_capture_snapshot(root: Path) -> Path:
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
            }
        },
    )
    _write_json(latest / "runtime_health_latest.json", {"status": "WARN", "ts_epoch": observation_ts_epoch})
    _write_json(
        latest / "top_opportunities_latest.json",
        {
            "top_executable_count": 0,
            "top_advisory_count": 1,
            "source_candidate_count": 4,
            "phase2_ranked_count": 0,
            "phase2_reason": "no_rankable_candidates",
            "selector_outcome": "NO_EXECUTABLE_OPPORTUNITY",
            "selected_count": 0,
            "ranked_candidates": [],
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
            {
                "symbol": "BANKNIFTY",
                "fresh": False,
                "reason": "quote_exceeds_threshold",
                "quote_age_sec": 602128.0,
                "ts_epoch": observation_ts_epoch,
            }
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
                "confidence_raw": 0.600494,
                "confidence": 0.18,
                "opportunity_score_raw": 0.41932,
                "opportunity_score": 0.32,
                "score_flattening_reason": "fallback_penalty_and_no_signal_penalty",
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
                "reason_code": "price_mismatch",
                "ts_epoch": observation_ts_epoch,
            }
        ],
    )
    _write_jsonl(
        logs / "trade_lifecycle_tail.jsonl",
        [
            {
                "trade_id": "t2",
                "stage": "review",
                "status": "blocked",
                "reason": "no_executable_opportunity",
                "ts_epoch": observation_ts_epoch,
            }
        ],
    )
    return snapshot


def _sections_by_name(report):
    return {section.name: section for section in report.sections}


def test_capture_guard_reports_all_required_sections(tmp_path):
    _build_capture_snapshot(tmp_path)

    report = generate_runtime_evidence_capture_guard_report(
        tmp_path,
        options=RuntimeEvidenceCaptureOptions(today=date(2026, 5, 22)),
    )

    assert report.verdict == "CAPTURE_GUARD_OK"
    assert tuple(REQUIRED_CAPTURE_SECTIONS) == report.required_sections
    sections = _sections_by_name(report)
    assert set(sections) == set(REQUIRED_CAPTURE_SECTIONS)
    assert all(section.status == "covered" for section in sections.values())
    assert sections["feed"].details["feed_not_ok_snapshots"] == 1
    assert sections["freshness"].details["stale_symbols"] == ["BANKNIFTY"]
    assert sections["fallback"].details["fallback_rows_in_capture_scan"] >= 1
    assert sections["candidate_funnel"].details["rows_seen"] >= 2
    assert sections["score_flattening"].details["score_flattening_count"] >= 2
    assert "no_executable_opportunity" in sections["final_no_trade_reasons"].details["reason_counts"]


def test_capture_guard_serializes_safety_metadata(tmp_path):
    _build_capture_snapshot(tmp_path)

    payload = generate_runtime_evidence_capture_guard_report(
        tmp_path,
        options=RuntimeEvidenceCaptureOptions(today=date(2026, 5, 22)),
    ).to_dict()

    assert payload["mode"] == "EVIDENCE_REPLAY"
    assert payload["candidate_id"] == "EDGE-38-RUNTIME-EVIDENCE-CAPTURE-GUARD"
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["decision"] == "CAPTURE_GUARD_OK"


def test_capture_guard_supports_tar_gz_pack(tmp_path):
    source_root = tmp_path / "source"
    _build_capture_snapshot(source_root)
    bundle = tmp_path / "live_diag_20260522_evidence.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        archive.add(source_root / "runtime", arcname="runtime")

    report = generate_runtime_evidence_capture_guard_report(
        bundle,
        options=RuntimeEvidenceCaptureOptions(today=date(2026, 5, 22)),
    )

    assert report.verdict == "CAPTURE_GUARD_OK"
    assert report.source.endswith("live_diag_20260522_evidence.tar.gz")
    assert report.diagnosis_totals["fallback_row_count"] >= 1


def test_capture_guard_fails_closed_when_snapshot_missing_required_sections(tmp_path):
    snapshot = tmp_path / "runtime" / "evidence" / "live_diag_manual_20260522_143341"
    (snapshot / "runtime_latest").mkdir(parents=True)
    (snapshot / "runtime_logs").mkdir(parents=True)
    _write_json(snapshot / "runtime_latest" / "top_opportunities_latest.json", {"top_executable_count": 0})

    report = generate_runtime_evidence_capture_guard_report(
        tmp_path,
        options=RuntimeEvidenceCaptureOptions(today=date(2026, 5, 22)),
    )

    assert report.verdict == "CAPTURE_GUARD_INCOMPLETE"
    sections = _sections_by_name(report)
    assert sections["feed"].status == "missing"
    assert sections["freshness"].status == "missing"
    assert sections["final_no_trade_reasons"].status == "missing"


def test_capture_guard_markdown_contains_required_sections(tmp_path):
    _build_capture_snapshot(tmp_path)
    report = generate_runtime_evidence_capture_guard_report(
        tmp_path,
        options=RuntimeEvidenceCaptureOptions(today=date(2026, 5, 22)),
    )

    markdown = runtime_evidence_capture_guard_to_markdown(report)

    assert "EDGE-38 Runtime Evidence Capture Guard Report" in markdown
    assert "CAPTURE_GUARD_OK" in markdown
    for section in REQUIRED_CAPTURE_SECTIONS:
        assert section in markdown
