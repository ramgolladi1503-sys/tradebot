import json

import pytest

from config import config as cfg
from core.execution_engine import ExecutionEngine, FailureType


def _build_engine(monkeypatch, tmp_path, **overrides):
    defaults = {
        "EXEC_FAILURE_LOG_PATH": str(tmp_path / "execution_failures.jsonl"),
        "EXEC_BROKER_REJECT_KILL_THRESHOLD": 2,
        "EXEC_NETWORK_KILL_THRESHOLD": 2,
        "EXEC_NETWORK_FAILURE_WINDOW_SEC": 60.0,
        "EXEC_NETWORK_RETRY_MAX_ATTEMPTS": 3,
        "EXEC_NETWORK_RETRY_BASE_SEC": 0.1,
        "EXEC_NETWORK_RETRY_MAX_SEC": 0.5,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    return ExecutionEngine()


def _read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_register_failure_tracks_per_type_counters(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path)
    engine.register_failure(FailureType.UNKNOWN, reason="test_unknown")
    engine.register_failure(FailureType.SPREAD_TOO_WIDE, reason="spread_too_wide")
    snap = engine.get_failure_snapshot(now_epoch=10.0)
    assert snap["counters"]["UNKNOWN"] == 1
    assert snap["counters"]["SPREAD_TOO_WIDE"] == 1
    assert snap["kill_switch_triggered"] is False


def test_kill_switch_triggers_only_when_broker_reject_exceeds_threshold(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path, EXEC_BROKER_REJECT_KILL_THRESHOLD=1)
    engine.register_failure(FailureType.BROKER_REJECT, reason="first_reject")
    assert engine.get_failure_snapshot()["kill_switch_triggered"] is False
    with pytest.raises(RuntimeError, match="EXECUTION KILL SWITCH TRIGGERED"):
        engine.register_failure(FailureType.BROKER_REJECT, reason="second_reject")


def test_kill_switch_triggers_for_network_rolling_window(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path, EXEC_NETWORK_KILL_THRESHOLD=2, EXEC_NETWORK_FAILURE_WINDOW_SEC=60.0)
    engine.register_failure(FailureType.NETWORK, reason="net_1", now_epoch=0.0)
    engine.register_failure(FailureType.NETWORK, reason="net_2", now_epoch=1.0)
    with pytest.raises(RuntimeError, match="EXECUTION KILL SWITCH TRIGGERED"):
        engine.register_failure(FailureType.NETWORK, reason="net_3", now_epoch=2.0)


def test_network_window_pruning_prevents_false_kill(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path, EXEC_NETWORK_KILL_THRESHOLD=2, EXEC_NETWORK_FAILURE_WINDOW_SEC=60.0)
    engine.register_failure(FailureType.NETWORK, reason="net_old_1", now_epoch=0.0)
    engine.register_failure(FailureType.NETWORK, reason="net_old_2", now_epoch=1.0)
    engine.register_failure(FailureType.NETWORK, reason="net_new_1", now_epoch=70.0)
    snap = engine.get_failure_snapshot(now_epoch=70.0)
    assert snap["network_failures_rolling_60s"] == 1
    assert snap["kill_switch_triggered"] is False


def test_execute_with_network_retry_uses_exponential_backoff(monkeypatch, tmp_path):
    engine = _build_engine(
        monkeypatch,
        tmp_path,
        EXEC_NETWORK_RETRY_MAX_ATTEMPTS=4,
        EXEC_NETWORK_RETRY_BASE_SEC=0.2,
        EXEC_NETWORK_RETRY_MAX_SEC=1.0,
        EXEC_NETWORK_KILL_THRESHOLD=99,
    )
    sleeps = []
    monkeypatch.setattr("core.execution_engine.time.sleep", lambda d: sleeps.append(float(d)))
    calls = {"n": 0}

    def _op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary_network_issue")
        return {"ok": True}

    out = engine.execute_with_network_retry(_op, operation_name="broker_submit")
    assert out == {"ok": True}
    assert calls["n"] == 3
    assert sleeps == [0.2, 0.4]
    snap = engine.get_failure_snapshot()
    assert snap["counters"]["NETWORK"] == 2


def test_structured_failure_logging_written(monkeypatch, tmp_path):
    log_path = tmp_path / "failure_log.jsonl"
    engine = _build_engine(monkeypatch, tmp_path, EXEC_FAILURE_LOG_PATH=str(log_path))
    engine.register_failure(
        FailureType.RISK_LIMIT,
        reason="risk_cap_reached",
        context={"symbol": "NIFTY", "risk": "MAX_DAILY_LOSS"},
    )
    rows = _read_jsonl(log_path)
    assert rows
    row = rows[-1]
    assert row["event"] == "execution_failure"
    assert row["failure_type"] == FailureType.RISK_LIMIT.value
    assert row["reason"] == "risk_cap_reached"
    assert row["context"]["symbol"] == "NIFTY"

