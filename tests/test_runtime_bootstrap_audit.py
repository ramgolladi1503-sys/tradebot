from __future__ import annotations

import json

from core import audit_log
from core import runtime_bootstrap


def test_missing_audit_log_bootstraps_and_verifies(monkeypatch, tmp_path):
    path = tmp_path / "desks" / "DEFAULT" / "audit_log.jsonl"
    monkeypatch.setattr(audit_log, "AUDIT_LOG", path)
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)

    result = runtime_bootstrap.initialize_audit_chain(run_id="fresh-run", boot_epoch=123.0)
    assert result["ok"] is True, repr(result)
    assert result["created"] is True
    assert result["count"] == 1
    ok, status, count = audit_log.verify_chain(path, expected_run_id="fresh-run")
    assert (ok, count) == (True, 1)
    assert status != "missing_log"
    event = json.loads(path.read_text().splitlines()[0])
    assert event["run_id"] == "fresh-run"
    assert event["prev_hash"] == "GENESIS"


def test_prior_run_log_is_rejected_for_current_run(monkeypatch, tmp_path):
    path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(audit_log, "AUDIT_LOG", path)
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)
    first = runtime_bootstrap.initialize_audit_chain(run_id="run-a")
    assert first["ok"] is True, first

    result = runtime_bootstrap.initialize_audit_chain(run_id="run-b")

    assert result["ok"] is False
    assert result["status"] == "run_id_mismatch"


def test_empty_audit_log_is_rejected(monkeypatch, tmp_path):
    path = tmp_path / "audit_log.jsonl"
    path.touch()
    monkeypatch.setattr(audit_log, "AUDIT_LOG", path)
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)

    result = runtime_bootstrap.initialize_audit_chain(run_id="run-a")

    assert result["ok"] is False
    assert result["status"] == "empty_log"


def test_zero_event_log_with_non_bootstrap_record_is_rejected(monkeypatch, tmp_path):
    path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(audit_log, "AUDIT_LOG", path)
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)
    audit_log.append_event({"event": "UNRELATED_EVENT", "run_id": "run-a"})

    result = runtime_bootstrap.initialize_audit_chain(run_id="run-a")

    assert result["ok"] is False
    assert result["status"] == "missing_bootstrap"


def test_missing_run_id_fails_closed(monkeypatch, tmp_path):
    path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)
    monkeypatch.delenv("TRADEBOT_RUN_ID", raising=False)

    result = runtime_bootstrap.initialize_audit_chain()

    assert result["ok"] is False
    assert result["status"] == "missing_run_id"
    assert not path.exists()


def test_existing_tampered_log_is_not_replaced(monkeypatch, tmp_path):
    path = tmp_path / "audit_log.jsonl"
    path.write_text('{"prev_hash":"GENESIS","event_hash":"tampered"}\n')
    monkeypatch.setattr(runtime_bootstrap, "AUDIT_LOG", path)

    result = runtime_bootstrap.initialize_audit_chain(run_id="fresh-run")

    assert result["ok"] is False
    assert result["created"] is False
    assert "event_hash_mismatch" == result["status"]
    assert path.read_text() == '{"prev_hash":"GENESIS","event_hash":"tampered"}\n'
