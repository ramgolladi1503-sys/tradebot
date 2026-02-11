import time
from types import SimpleNamespace
import pytest

from config import config as cfg
import core.execution_guard as execution_guard
from core.execution_router import ExecutionRouter
from tools.flatten_positions import _flatten


@pytest.fixture(autouse=True)
def _disable_exec_readiness_guard(monkeypatch):
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_PAPER", False, raising=False)


def _trade(trade_id: str = "T-SAMPLE-RUN"):
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
        time_to_expiry_hrs=4.0,
        tradable=True,
        tradable_reasons_blocking=[],
        entry_type="LIMIT",
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        entry_condition="BUY_ABOVE",
        entry_ref_price=101.5,
        exchange="NFO",
        product="MIS",
    )


def _snapshot():
    return {"bid": 100.0, "ask": 101.0, "ts": time.time(), "depth": {}}


def test_sample_run_no_approval_never_places_broker(monkeypatch, tmp_path):
    class _FakeKite:
        VARIETY_REGULAR = "regular"
        ORDER_TYPE_MARKET = "market"
        PRODUCT_MIS = "mis"
        VALIDITY_DAY = "day"

        def __init__(self):
            self.calls = 0

        def place_order(self, **kwargs):
            self.calls += 1
            return "OID"

    def _deny_approval(*args, **kwargs):
        return False, "approval_missing"

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(execution_guard, "consume_valid_approval", _deny_approval)

    fake_kite = _FakeKite()
    monkeypatch.setattr("tools.flatten_positions.kite_client", SimpleNamespace(kite=fake_kite))
    monkeypatch.setattr("tools.flatten_positions.send_telegram_message", lambda *_a, **_k: True)

    router = ExecutionRouter()
    filled, price, report = router.execute(
        _trade(),
        bid=100.0,
        ask=101.0,
        volume=1000,
        snapshot_fn=_snapshot,
    )
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")

    _flatten(
        [{"tradingsymbol": "NIFTY26FEBFUT", "exchange": "NFO", "quantity": 10}],
        dry_run=False,
    )
    assert fake_kite.calls == 0
