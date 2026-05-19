import json
from pathlib import Path

from scripts.validate_live_market_evidence import validate_live_evidence, write_live_validation_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_validate_live_evidence_pass_candidate_when_required_evidence_present():
    report = {
        "read_only": True,
        "is_order_action": False,
        "summary": {
            "feed_ok": True,
            "ws_connected": True,
            "subscribed_option_tokens_count": 70,
            "visible_executable_count": 0,
            "suggestions_tail_rows": 2,
            "events_tail_rows": 1,
            "missing_runtime_files": [],
            "errored_runtime_files": {},
        },
        "blocker_evidence": {"suggestions_tail_blocker_counts": {"STALE_OPTION_LTP": 1}},
        "status_counts": {"suggestions_tail_status_counts": {"QUEUE_ONLY": 1}},
    }

    validation = validate_live_evidence(report)

    assert validation["verdict"] == "PASS_CANDIDATE"
    assert validation["violations"] == []
    assert validation["warnings"] == []


def test_validate_live_evidence_fails_when_required_connection_false():
    report = {
        "read_only": True,
        "is_order_action": False,
        "summary": {
            "feed_ok": True,
            "ws_connected": False,
            "subscribed_option_tokens_count": 70,
            "visible_executable_count": 0,
            "missing_runtime_files": [],
            "errored_runtime_files": {},
        },
        "blocker_evidence": {"suggestions_tail_blocker_counts": {"FEED_STALE": 1}},
        "status_counts": {"suggestions_tail_status_counts": {"ADVISORY_ONLY": 1}},
    }

    validation = validate_live_evidence(report)

    assert validation["verdict"] == "FAIL"
    assert "websocket_not_connected" in validation["violations"]


def test_validate_live_evidence_fails_when_executable_summary_missing():
    report = {
        "read_only": True,
        "is_order_action": False,
        "summary": {
            "missing_runtime_files": ["feed_runtime"],
            "errored_runtime_files": {},
        },
        "blocker_evidence": {"suggestions_tail_blocker_counts": {}},
        "status_counts": {"suggestions_tail_status_counts": {}},
    }

    validation = validate_live_evidence(report)

    assert validation["verdict"] == "FAIL"
    assert "missing_summary_field:feed_ok" in validation["warnings"]
    assert "missing_summary_field:visible_executable_count" in validation["violations"]


def test_write_live_validation_report_writes_report(tmp_path):
    root = tmp_path / "runtime"
    out = tmp_path / "evidence" / "live_validation.json"
    _write_json(root / "feed_runtime_latest.json", {"feed_ok": True, "ws_connected": True, "subscribed_option_tokens_count": 42})
    _write_json(root / "runtime_health_latest.json", {"feed_ok": True})
    _write_json(root / "engine_cycle_status.json", {"visible_executable_count": 0})
    _write_json(root / "suggestions_status.json", {"visible_executable_count": 0})
    _write_jsonl(root / "suggestions.jsonl", [{"execution_status": "QUEUE_ONLY", "primary_blocker": "STALE_OPTION_LTP"}])

    written = write_live_validation_report(root, out)

    assert written == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["read_only"] is True
    assert data["is_order_action"] is False
    assert data["verdict"] == "PASS_CANDIDATE"
    assert data["summary"]["subscribed_option_tokens_count"] == 42
