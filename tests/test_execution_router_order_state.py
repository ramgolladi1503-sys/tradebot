import time
from types import SimpleNamespace

from config import config as cfg
from core.approval_store import approve_order_intent
from core.execution_router import ExecutionRouter
from core.orders.order_intent import OrderIntent
from core.orders.state_machine import OrderState


def _snapshot():
    return {"bid": 100.0, "ask": 101.0, "ts": time.time(), "depth": {}}


def _trade(trade_id: str):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="NIFTY",
        instrument="OPT",
        instrument_id="NIFTY|2026-02-12|25200|CE",
        instrument_token=12345,
        side="BUY",
        entry_price=102.0,
        stop_loss=98.0,
        target=108.0,
        qty=10,
        confidence=0.8,
        tradable=True,
        tradable_reasons_blocking=[],
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        exchange="NFO",
        product="MIS",
        timestamp_bucket=123456,
    )


def test_router_persists_rejected_state_on_approval_block(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_PAPER", False, raising=False)

    router = ExecutionRouter()
    trade = _trade("T-STATE-REJECT")
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")
    assert report["order_state"] == OrderState.REJECTED.value
    db_state = router.engine.get_order_state(report["order_id"])
    assert db_state.state == OrderState.REJECTED


def test_router_persists_filled_state_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_PAPER", False, raising=False)

    trade = _trade("T-STATE-FILL")
    intent_hash = OrderIntent.from_trade(trade, mode="PAPER").order_intent_hash()
    ok, reason = approve_order_intent(intent_hash, approver_id="tester", ttl_sec=600)
    assert ok is True, reason

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is True
    assert price == 101.0
    assert report["order_state"] == OrderState.FILLED.value
    db_state = router.engine.get_order_state(report["order_id"])
    assert db_state.state == OrderState.FILLED
