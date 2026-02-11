import sqlite3
import time
from unittest.mock import Mock

import pytest

from config import config as cfg
from core.approval_store import approve_order_intent
from core.execution.chokepoint import ApprovalMissingOrInvalid, require_approval_or_abort
from core.orders.order_intent import OrderIntent


def _intent(qty: int = 1) -> OrderIntent:
    return OrderIntent(
        symbol="NIFTY",
        instrument_type="option",
        side="BUY",
        qty=qty,
        order_type="LIMIT",
        limit_price=100.0,
        exchange="NFO",
        product="MIS",
        strategy_id="test_strategy",
        timestamp_bucket=123456,
        expiry="2026-02-12",
        strike=25200.0,
        right="CE",
        multiplier=50.0,
    )


def _run_live_pipeline(intent: OrderIntent, broker: object, now_epoch: float) -> None:
    require_approval_or_abort(intent, mode="LIVE", now=now_epoch, approver="ops_user", ttl=300)
    broker.place_order(intent_hash=intent.order_intent_hash(), symbol=intent.symbol, qty=intent.qty)


def _run_paper_pipeline(intent: OrderIntent, paper_executor: object, now_epoch: float) -> None:
    require_approval_or_abort(intent, mode="PAPER", now=now_epoch, approver="ops_user", ttl=300)
    paper_executor.record_fill(intent_hash=intent.order_intent_hash(), symbol=intent.symbol, qty=intent.qty)


def _approval_status(db_path: str, intent_hash: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM order_approvals WHERE order_intent_hash=?",
            (intent_hash,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_invariant_without_approval_blocks_every_placement_path(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    intent = _intent()
    broker = type("Broker", (), {"place_order": Mock()})()
    paper_executor = type("PaperExecutor", (), {"record_fill": Mock()})()
    now_epoch = time.time()

    with pytest.raises(ApprovalMissingOrInvalid):
        _run_live_pipeline(intent, broker, now_epoch)
    with pytest.raises(ApprovalMissingOrInvalid):
        _run_paper_pipeline(intent, paper_executor, now_epoch)

    assert broker.place_order.call_count == 0
    assert paper_executor.record_fill.call_count == 0


def test_exact_hash_approval_allows_once_and_marks_used(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    intent = _intent()
    intent_hash = intent.order_intent_hash()
    ok, reason = approve_order_intent(intent_hash, approver_id="ops_user", ttl_sec=300)
    assert ok is True, reason

    broker = type("Broker", (), {"place_order": Mock()})()
    now_epoch = time.time()
    _run_live_pipeline(intent, broker, now_epoch)
    assert broker.place_order.call_count == 1
    assert _approval_status(db_path, intent_hash) == "USED"

    with pytest.raises(ApprovalMissingOrInvalid):
        _run_live_pipeline(intent, broker, now_epoch + 1.0)
    assert broker.place_order.call_count == 1


def test_different_hash_never_matches_approval(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    approved_intent = _intent(qty=1)
    wrong_intent = _intent(qty=2)
    ok, reason = approve_order_intent(approved_intent.order_intent_hash(), approver_id="ops_user", ttl_sec=300)
    assert ok is True, reason

    broker = type("Broker", (), {"place_order": Mock()})()
    with pytest.raises(ApprovalMissingOrInvalid):
        _run_live_pipeline(wrong_intent, broker, time.time())
    assert broker.place_order.call_count == 0

