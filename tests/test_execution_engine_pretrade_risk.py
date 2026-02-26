from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.state_machine import OrderStateMachine


def _setup_engine(monkeypatch, tmp_path, **overrides):
    db_path = tmp_path / "execution_pretrade.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "ORDER_RECONCILE_ON_STARTUP", False, raising=False)
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
    state_machine = OrderStateMachine(db_path=str(db_path))
    engine = ExecutionEngine(order_state_machine=state_machine)
    return engine


def test_place_order_pretrade_rejects_before_submit(monkeypatch, tmp_path):
    engine = _setup_engine(monkeypatch, tmp_path)
    calls = {"submit": 0}

    def _submit(**_kwargs):
        calls["submit"] += 1
        return {"order_id": "BRK-1", "status": "OPEN"}

    out = engine.place_order(
        signal_id="SIG-RISK-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1700001000,
        submit_order_fn=_submit,
        submit_kwargs={"quantity": 10},
        risk_context={"margin_required": 1000.0, "margin_available": 100.0},
    )
    assert out["placed"] is False
    assert out["risk_rejected"] is True
    assert out["risk_decision"]["reason_code"] == "INSUFFICIENT_MARGIN"
    assert calls["submit"] == 0
    assert out["order"].state.name == "REJECTED"


def test_place_order_blocks_duplicate_signal_after_first_accept(monkeypatch, tmp_path):
    engine = _setup_engine(monkeypatch, tmp_path)

    def _submit(**_kwargs):
        return {"order_id": "BRK-2", "status": "OPEN"}

    first = engine.place_order(
        signal_id="SIG-DUP-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1700002000,
        submit_order_fn=_submit,
        submit_kwargs={"quantity": 1, "price": 100.0},
        risk_context={"margin_available": 1_000_000.0},
    )
    assert first["placed"] is True

    second = engine.place_order(
        signal_id="SIG-DUP-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1700002001,
        submit_order_fn=_submit,
        submit_kwargs={"quantity": 1, "price": 100.0},
        risk_context={"margin_available": 1_000_000.0},
    )
    assert second["placed"] is False
    assert second["risk_rejected"] is True
    assert second["risk_decision"]["reason_code"] == "DUPLICATE_SIGNAL"

