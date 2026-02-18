import time

from config import config as cfg
from core.approval_store import (
    arm_order_intent,
    approve_and_consume_order_intent,
    approve_order_intent,
    consume_valid_approval,
    create_order_approval,
    reject_order_intent,
)
from core.execution_guard import OrderIntent


def _intent():
    return OrderIntent(
        symbol="NIFTY",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        limit_price=101.0,
        product="MIS",
        exchange="NFO",
        strategy_id="TEST_STRAT",
        timestamp_bucket=123456,
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        multiplier=1.0,
    )


def test_order_intent_hash_is_stable():
    one = _intent()
    two = _intent()
    assert one.canonical_json() == two.canonical_json()
    assert one.order_intent_hash() == two.order_intent_hash()


def test_order_intent_hash_changes_on_any_payload_field():
    base = _intent()
    qty_changed = OrderIntent(**{**base.__dict__, "qty": 11})
    price_changed = OrderIntent(**{**base.__dict__, "limit_price": 101.25})
    strike_changed = OrderIntent(**{**base.__dict__, "strike": 25300})
    expiry_changed = OrderIntent(**{**base.__dict__, "expiry": "2026-02-19"})
    assert qty_changed.order_intent_hash() != base.order_intent_hash()
    assert price_changed.order_intent_hash() != base.order_intent_hash()
    assert strike_changed.order_intent_hash() != base.order_intent_hash()
    assert expiry_changed.order_intent_hash() != base.order_intent_hash()


def test_consume_valid_approval_is_one_time(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="tester", ttl_sec=60)
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="tester")
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="tester")
    assert ok is False
    assert reason == "approval_used"


def test_consume_valid_approval_respects_expiry(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="tester", ttl_sec=0)
    assert ok is True, reason
    time.sleep(0.01)

    ok, reason = consume_valid_approval(h, approver_id="tester")
    assert ok is False
    assert reason == "approval_expired"


def test_pending_approval_cannot_be_consumed(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = create_order_approval(
        h,
        approver_id="tester",
        channel="cli",
        ttl_sec=60,
        status="PENDING",
    )
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="tester")
    assert ok is False
    assert reason == "approval_pending"


def test_rejected_approval_cannot_be_consumed(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = reject_order_intent(
        h,
        approver_id="reviewer",
        channel="telegram",
        ttl_sec=60,
        reject_reason="risk_blocked",
    )
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="tester")
    assert ok is False
    assert reason == "approval_rejected"


def test_approve_and_consume_is_atomic_and_single_use(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_and_consume_order_intent(
        h,
        approver_id="ops_user",
        channel="cli",
        ttl_sec=60,
    )
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="ops_user")
    assert ok is False
    assert reason == "approval_used"


def test_used_approval_cannot_be_reapproved(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="ops_user", ttl_sec=60)
    assert ok is True, reason
    ok, reason = consume_valid_approval(h, approver_id="ops_user")
    assert ok is True, reason

    ok, reason = approve_order_intent(h, approver_id="ops_user", ttl_sec=60)
    assert ok is False
    assert reason == "approval_already_used"


def test_used_approval_cannot_be_rearmed_with_approve_and_consume(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_and_consume_order_intent(
        h,
        approver_id="ops_user",
        channel="cli",
        ttl_sec=60,
    )
    assert ok is True, reason

    ok, reason = approve_and_consume_order_intent(
        h,
        approver_id="ops_user",
        channel="cli",
        ttl_sec=60,
    )
    assert ok is False
    assert reason == "approval_used"


def test_live_mode_requires_armed_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="ops_user", ttl_sec=60)
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="ops_user", require_armed=True)
    assert ok is False
    assert reason == "approval_not_armed"


def test_armed_approval_expiry_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="ops_user", ttl_sec=60)
    assert ok is True, reason

    ok, reason = arm_order_intent(h, approver_id="ops_user", arm_ttl_sec=0)
    assert ok is False
    assert reason == "approval_arm_ttl_invalid"

    ok, reason = arm_order_intent(h, approver_id="ops_user", arm_ttl_sec=1)
    assert ok is True, reason
    time.sleep(1.05)
    ok, reason = consume_valid_approval(h, approver_id="ops_user", require_armed=True)
    assert ok is False
    assert reason == "approval_arm_expired"


def test_armed_approval_is_single_use(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="ops_user", ttl_sec=60)
    assert ok is True, reason

    ok, reason = arm_order_intent(h, approver_id="ops_user", arm_ttl_sec=30)
    assert ok is True, reason
    ok, reason = consume_valid_approval(h, approver_id="ops_user", require_armed=True)
    assert ok is True, reason

    ok, reason = consume_valid_approval(h, approver_id="ops_user", require_armed=True)
    assert ok is False
    assert reason == "approval_used"


def test_approval_store_creates_nested_trade_db_parent_dirs(monkeypatch, tmp_path):
    nested_db = tmp_path / "missing" / "deep" / "path" / "desks" / "DEFAULT" / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(nested_db), raising=False)

    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="tester", ttl_sec=60)
    assert ok is True, reason
    assert nested_db.parent.exists()
    assert nested_db.exists()
