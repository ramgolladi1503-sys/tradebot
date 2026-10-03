from __future__ import annotations

import hashlib
import json
from pathlib import Path

from config import config as cfg
from core.analytics.daily_report import build_daily_intelligence_report
from core.runtime_snapshot_producer import (
    _build_advisory_latest_payload,
    canonical_suggestions_log_path,
)


def test_observer_decision_rows_match_advisory_and_eod_diagnostic_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session-2026-10-01"
    session_dir.mkdir()
    decision_path = session_dir / "candidate_decisions.jsonl"
    rows = [
        {
            "candidate_id": "PARITY-1",
            "ts_epoch": 1790821800.0,
            "ts_ist": "2026-10-01T10:00:00+05:30",
            "symbol": "NIFTY",
            "entry": 123.45,
            "stop_loss": 120.0,
            "target": 130.0,
            "execution_allowed": False,
            "permission": "ADVISORY_ONLY",
            "final_action": "QUEUE_ONLY",
        },
        {
            "candidate_id": "PARITY-2",
            "ts_epoch": 1790821860.0,
            "ts_ist": "2026-10-01T10:01:00+05:30",
            "symbol": "NIFTY",
            "entry": 124.45,
            "stop_loss": 121.0,
            "target": 131.0,
            "execution_allowed": False,
            "permission": "ADVISORY_ONLY",
            "final_action": "QUEUE_ONLY",
        },
    ]
    raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    decision_path.write_bytes(raw)

    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(
        "core.runtime_snapshot_producer.logs_dir",
        lambda: logs_dir,
    )
    monkeypatch.setattr(
        "core.runtime_snapshot_producer.canonical_suggestions_log_path",
        lambda: logs_dir / "suggestions.jsonl",
    )
    monkeypatch.setattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)
    monkeypatch.setattr(
        cfg,
        "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE",
        True,
        raising=False,
    )
    monkeypatch.setattr(cfg, "DAILY_REPORT_INCLUDE_EXECUTABLE_SHADOW", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTABLE_SHADOW_PORTFOLIO_ENABLE", False, raising=False)

    advisory = _build_advisory_latest_payload(candidate_decisions_path=decision_path)
    report = build_daily_intelligence_report(
        "2026-10-01",
        events=[],
        attempt_outcome_replay=False,
        output_dir=tmp_path / "report",
        session_dir=session_dir,
    )

    expected_ids = [row["candidate_id"] for row in rows]
    assert [row["trade_id"] for row in advisory["rows"]] == expected_ids
    assert advisory["row_count"] == len(rows)
    assert Path(advisory["source_path"]).resolve() == decision_path.resolve()

    telemetry = report["sections"]["session_telemetry"]
    source = next(
        item
        for item in telemetry["source_files"]
        if item["kind"] == "candidate_decisions"
    )
    assert Path(source["path"]).resolve() == decision_path.resolve()
    assert source["sha256"] == hashlib.sha256(raw).hexdigest()
    assert source["records"] == len(rows)
    assert source["malformed_records"] == 0

    # Decision telemetry is not a candidate journal or trade-intent source.
    assert report["header"]["counts"]["events"] == 0
