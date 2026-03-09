from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.execution_plan import ExecutionPlan
from core.orders.state_machine import OrderStateMachine


def _setup_engine(monkeypatch, tmp_path, **overrides) -> ExecutionEngine:
    db_path = tmp_path / "execution_plan_boundary.db"
    action_log = tmp_path / "execution_actions.jsonl"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "EXEC_ACTION_LOG_PATH", str(action_log), raising=False)
    monkeypatch.setattr(cfg, "ORDER_RECONCILE_ON_STARTUP", False, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)

    defaults = {
        "PRETRADE_RISK_ENABLE": True,
        "PRETRADE_MARGIN_BUFFER_PCT": 0.0,
        "PRETRADE_MAX_EXPOSURE_PER_INSTRUMENT": 1_000_000.0,
        "PRETRADE_MAX_DAILY_LOSS": 1_000_000.0,
        "PRETRADE_MAX_TRADES_PER_MINUTE": 100,
        "PRETRADE_MAX_CORRELATED_EXPOSURE": 1_000_000.0,
        "PRETRADE_DUPLICATE_WINDOW_SEC": 300.0,
        "PRETRADE_CORRELATION_THRESHOLD": 0.75,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    return ExecutionEngine(order_state_machine=OrderStateMachine(db_path=str(db_path)))


def _build_plan(*, mode: str = "PAPER") -> ExecutionPlan:
    return ExecutionPlan(
        symbol="NIFTY",
        token=123456,
        side="BUY",
        qty=10,
        entry_type="LIMIT",
        stop_loss=98.0,
        take_profit=112.0,
        snapshot_id="snap-test-001",
        decision_id="decision-test-001",
        mode=mode,
        signal_id="signal-test-001",
        timestamp_epoch=1_700_000_100.0,
    )


def test_execution_plan_rejects_when_risk_limit_exceeded(monkeypatch, tmp_path):
    engine = _setup_engine(monkeypatch, tmp_path)
    submit_calls = {"count": 0}

    def _submit(**_kwargs):
        submit_calls["count"] += 1
        return {"order_id": "BRK-PLAN-1", "status": "OPEN"}

    out = engine.place_order_from_plan(
        _build_plan(),
        submit_order_fn=_submit,
        submit_kwargs={"quantity": 10, "price": 100.0},
        risk_context={"margin_required": 1_000.0, "margin_available": 100.0},
    )
    assert out["placed"] is False
    assert out["risk_rejected"] is True
    assert out["snapshot_id"] == "snap-test-001"
    assert out["decision_id"] == "decision-test-001"
    assert submit_calls["count"] == 0


def test_execution_plan_logs_snapshot_and_decision_ids(monkeypatch, tmp_path):
    engine = _setup_engine(monkeypatch, tmp_path)
    action_log = Path(str(getattr(cfg, "EXEC_ACTION_LOG_PATH")))

    def _submit(**_kwargs):
        return {"order_id": "BRK-PLAN-2", "status": "OPEN"}

    out = engine.place_order_from_plan(
        _build_plan(),
        submit_order_fn=_submit,
        submit_kwargs={"quantity": 1, "price": 100.0},
        risk_context={"margin_available": 1_000_000.0},
    )
    assert out["placed"] is True
    assert action_log.exists()
    rows = [
        json.loads(line)
        for line in action_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert any(row.get("phase") == "received" for row in rows)
    assert any(row.get("phase") == "completed" for row in rows)
    for row in rows:
        assert row.get("snapshot_id") == "snap-test-001"
        assert row.get("decision_id") == "decision-test-001"
