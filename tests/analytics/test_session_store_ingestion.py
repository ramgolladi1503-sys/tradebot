from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.analytics.store import (
    _int_event_from_candidate_journal_row,
    discover_session_paths,
    load_session_diagnostics,
    load_session_events,
    load_trade_intent_events,
)


def _candidate_row(**overrides):
    row = {
        "candidate_id": "candidate-1",
        "journal_event": "candidate_reported",
        "symbol": "NIFTY",
        "expiry": "2026-10-08",
        "strike": 25000,
        "option_type": "CE",
        "side": "BUY",
        "permission": "BLOCK",
        "permission_reason": "FEED_STALE",
        "entry_price": 100,
        "target_price": 110,
        "stop_loss": 95,
        "timestamp_epoch": 1790841500.0,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("permission", ["EXECUTE", "ALLOW", "ACCEPT"])
def test_candidate_journal_acceptance_is_not_misclassified_as_rejected(permission):
    row = _candidate_row(permission=permission, permission_reason=None, reject_reason=None)
    event = _int_event_from_candidate_journal_row(row, source="test")
    assert event is not None
    assert event.intent == "accepted"
    assert event.reject_reason is None
    assert event.metrics_snapshot["entry"] == 100


@pytest.mark.parametrize("missing", ["expiry", "strike", "option_type", "side", "entry", "target", "stop"])
def test_candidate_journal_incomplete_candidate_fails_closed(missing):
    row = _candidate_row()
    if missing in {"expiry", "strike", "option_type"}:
        row[missing] = None
    elif missing == "side":
        row["side"] = "UNKNOWN"
    else:
        key = {"entry": "entry_price", "target": "target_price", "stop": "stop_loss"}[missing]
        row[key] = None
    assert _int_event_from_candidate_journal_row(row, source="test") is None


def test_session_observations_and_governance_snapshots_are_diagnostic_only(tmp_path: Path):
    session_dir = tmp_path / "run-001"
    session_dir.mkdir()
    (session_dir / "strategy_observations.jsonl").write_text(
        json.dumps({"symbol": "NIFTY", "reason_code": "CAS_PRIMITIVE_0915_INVALID", "timestamp_epoch": 1790841500}) + "\n",
        encoding="utf-8",
    )
    (session_dir / "trade_truth_stream.jsonl").write_text(
        json.dumps({"identity": {"underlying": "NIFTY"}, "decision": {"governance_decision": "BLOCKED"}}) + "\n",
        encoding="utf-8",
    )

    assert load_session_events([session_dir]) == []
    review_path = tmp_path / "review.json"
    review_path.write_text("[]", encoding="utf-8")
    empty_telemetry = tmp_path / "decisions.jsonl"
    empty_telemetry.write_text("", encoding="utf-8")
    assert load_trade_intent_events(
        session_paths=[session_dir], review_queue_paths=[review_path],
        decision_telemetry_paths=[empty_telemetry], db_path=tmp_path / "missing.sqlite"
    ) == []
    diagnostics = load_session_diagnostics([session_dir])
    assert diagnostics["record_count"] == 2
    assert diagnostics["malformed_record_count"] == 0
    assert diagnostics["read_only"] is True
    assert diagnostics["broker_api_called"] is False
    assert len(diagnostics["source_files"]) == 2
    assert all(len(source["sha256"]) == 64 for source in diagnostics["source_files"])


def test_session_candidate_journal_requires_complete_candidate(tmp_path: Path):
    session_dir = tmp_path / "run-002"
    session_dir.mkdir()
    rows = [_candidate_row(), _candidate_row(candidate_id="candidate-incomplete", target_price=None)]
    (session_dir / "candidate_journal.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    events = load_session_events([session_dir])
    assert len(events) == 1
    assert events[0].intent == "rejected"
    assert events[0].reject_reason == "FEED_STALE"
    assert events[0].metrics_snapshot["candidate_id"] == "candidate-1"
    assert events[0].metrics_snapshot["entry"] == 100
    assert events[0].event_id != ""


def test_explicit_session_path_is_exclusive_and_invalid_path_errors(tmp_path: Path, monkeypatch):
    explicit = tmp_path / "sessions"
    (explicit / "session_2026-10-01" / "run-good").mkdir(parents=True)
    (explicit / "session_2026-09-30" / "run-other").mkdir(parents=True)
    env = tmp_path / "other"
    (env / "session_2026-10-01").mkdir(parents=True)
    monkeypatch.setenv("TRADEBOT_SESSION_DIR", str(env))
    paths = discover_session_paths(date_key="2026-10-01", session_dir=explicit)
    assert any("run-good" in str(path) for path in paths)
    assert not any("run-other" in str(path) for path in paths)
    assert not any(env in path.parents for path in paths)
    with pytest.raises(ValueError, match="session_dir_not_a_directory"):
        discover_session_paths(date_key="2026-10-01", session_dir=tmp_path / "missing")


def test_diagnostics_count_malformed_records_and_preserve_source_hash(tmp_path: Path):
    session_dir = tmp_path / "run-003"
    session_dir.mkdir()
    source = session_dir / "strategy_observations.jsonl"
    source.write_text('{"reason_code":"OK"}\nnot-json\n', encoding="utf-8")
    result = load_session_diagnostics([session_dir])
    assert result["record_count"] == 1
    assert result["malformed_record_count"] == 1
    assert result["source_files"][0]["sha256"]
