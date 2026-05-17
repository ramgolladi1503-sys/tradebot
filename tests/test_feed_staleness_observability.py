import json
from pathlib import Path

from core.feed_staleness_observability import build_feed_staleness_report, write_feed_staleness_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_feed_staleness_report_collects_core_runtime_fields(tmp_path):
    logs = tmp_path / "logs"
    _write_json(
        logs / "feed_runtime_latest.json",
        {
            "feed_ok": True,
            "ws_connected": True,
            "subscribed_option_tokens_count": 70,
            "option_ltp_age_sec": 1.2,
        },
    )
    _write_json(
        logs / "runtime_health_latest.json",
        {
            "feed_ok": True,
            "feed_blockers": ["ltp_stale:NIFTY age=3.1 max=2.5"],
            "sla_status": "DEGRADED",
        },
    )
    _write_json(
        logs / "engine_cycle_status.json",
        {"visible_executable_count": 0, "primary_blocker": "STALE_OPTION_LTP"},
    )
    _write_json(logs / "suggestions_status.json", {"visible_executable_count": 0})
    _append_jsonl(
        logs / "suggestions.jsonl",
        [
            {"execution_status": "QUEUE_ONLY", "primary_blocker": "STALE_OPTION_LTP", "option_ltp_age_sec": 4.2},
            {"execution_status": "ADVISORY_ONLY", "primary_blocker": "WIDE_SPREAD", "option_ltp_age_sec": 2.1},
        ],
    )

    report = build_feed_staleness_report(logs)

    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["summary"]["feed_ok"] is True
    assert report["summary"]["ws_connected"] is True
    assert report["summary"]["subscribed_option_tokens_count"] == 70
    assert report["summary"]["visible_executable_count"] == 0
    assert report["blocker_evidence"]["suggestions_tail_blocker_counts"]["STALE_OPTION_LTP"] == 1
    assert report["blocker_evidence"]["suggestions_tail_blocker_counts"]["WIDE_SPREAD"] == 1
    assert report["status_counts"]["suggestions_tail_status_counts"]["QUEUE_ONLY"] == 1
    assert report["stale_evidence"]["suggestions_tail_max_ages"]["option_ltp_age_sec"] == 4.2


def test_feed_staleness_report_degrades_when_files_missing(tmp_path):
    logs = tmp_path / "missing_logs"

    report = build_feed_staleness_report(logs)

    assert report["read_only"] is True
    assert report["summary"]["feed_ok"] is None
    assert report["summary"]["ws_connected"] is None
    assert set(report["summary"]["missing_runtime_files"]) == {
        "feed_runtime",
        "runtime_health",
        "engine_cycle",
        "suggestions_status",
    }


def test_write_feed_staleness_report_writes_json(tmp_path):
    logs = tmp_path / "logs"
    out = tmp_path / "evidence" / "feed_report.json"
    _write_json(logs / "feed_runtime_latest.json", {"feed_ok": True, "ws_connected": False})

    written = write_feed_staleness_report(logs, out)

    assert written == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["feed_ok"] is True
    assert data["summary"]["ws_connected"] is False
    assert data["read_only"] is True
    assert data["is_order_action"] is False
