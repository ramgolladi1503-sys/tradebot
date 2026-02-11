import time
from types import SimpleNamespace
import pytest

from config import config as cfg
from core.execution_router import ExecutionRouter
from core.execution_guard import OrderIntent
from core.approval_store import approve_order_intent, arm_order_intent
import core.review_queue as review_queue
from tools.flatten_positions import _flatten


@pytest.fixture(autouse=True)
def _disable_exec_readiness_guard(monkeypatch):
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_PAPER", False, raising=False)


def _trade(trade_id: str = "T-APPROVAL-1"):
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


def test_no_approval_blocks_order(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_STRICT_PAYLOAD_HASH", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(review_queue, "APPROVED_PATH", tmp_path / "approved_trades.json", raising=False)

    router = ExecutionRouter()
    trade = _trade("T-NO-APPROVAL")
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:approval_missing")


def test_approval_payload_mismatch_blocks_order(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_STRICT_PAYLOAD_HASH", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(review_queue, "APPROVED_PATH", tmp_path / "approved_trades.json", raising=False)

    trade = _trade("T-MISMATCH")
    approve_order_intent("deadbeef", approver_id="tester", ttl_sec=600)

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")


def test_expired_approval_blocks_order(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_STRICT_PAYLOAD_HASH", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(review_queue, "APPROVED_PATH", tmp_path / "approved_trades.json", raising=False)

    trade = _trade("T-EXPIRED")
    payload_hash = OrderIntent.from_trade(trade, mode="PAPER").order_intent_hash()
    approve_order_intent(payload_hash, approver_id="tester", ttl_sec=0)
    time.sleep(0.02)

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:approval_expired")


def test_matching_approval_allows_order(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_STRICT_PAYLOAD_HASH", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(review_queue, "APPROVED_PATH", tmp_path / "approved_trades.json", raising=False)

    trade = _trade("T-OK")
    payload_hash = OrderIntent.from_trade(trade, mode="PAPER").order_intent_hash()
    approve_order_intent(payload_hash, approver_id="tester", ttl_sec=600)

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is True
    assert price == 101.0
    assert report.get("reason_if_aborted") is None


def test_sim_path_without_approval_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    router = ExecutionRouter()
    trade = _trade("T-SIM-NO-APPROVAL")
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")


def test_live_path_without_approval_blocks_before_live_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    router = ExecutionRouter()
    trade = _trade("T-LIVE-NO-APPROVAL")
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")


def test_live_approval_not_armed_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", True, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    trade = _trade("T-LIVE-APPROVED-NOT-ARMED")
    payload_hash = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    ok, reason = approve_order_intent(payload_hash, approver_id="tester", ttl_sec=600)
    assert ok is True, reason

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].endswith("approval_not_armed")


def test_live_armed_within_window_passes_once(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", True, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    trade = _trade("T-LIVE-ARMED-ONCE")
    payload_hash = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    ok, reason = approve_order_intent(payload_hash, approver_id="tester", ttl_sec=600)
    assert ok is True, reason
    ok, reason = arm_order_intent(payload_hash, approver_id="tester", arm_ttl_sec=30)
    assert ok is True, reason

    router = ExecutionRouter()
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"] == "live_not_implemented"

    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].endswith("approval_used")


def test_flatten_positions_path_without_approval_never_calls_broker(monkeypatch, tmp_path):
    class _FakeKite:
        VARIETY_REGULAR = "regular"
        ORDER_TYPE_MARKET = "market"
        PRODUCT_MIS = "mis"
        VALIDITY_DAY = "day"
        calls = 0

        def place_order(self, **kwargs):
            self.calls += 1
            return "OID"

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    fake = _FakeKite()
    monkeypatch.setattr("tools.flatten_positions.kite_client", SimpleNamespace(kite=fake))
    net = [{"tradingsymbol": "NIFTY26FEBFUT", "exchange": "NFO", "quantity": 10}]
    _flatten(net, dry_run=False)
    assert fake.calls == 0


def test_paper_path_without_approval_never_calls_fill_simulator(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "SIM,PAPER,LIVE", raising=False)

    router = ExecutionRouter()
    called = {"count": 0}

    def _simulate(*args, **kwargs):
        called["count"] += 1
        return True, 101.0, {"fill_status": "FILLED", "fill_qty": 1, "requested_qty": 1}

    monkeypatch.setattr(router.paper_sim, "simulate", _simulate)

    trade = _trade("T-PAPER-NO-APPROVAL-SIMCALL")
    filled, price, report = router.execute(trade, bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")
    assert called["count"] == 0
