import sqlite3
import time

from config import config as cfg
from core.approval_store import (
    approve,
    consume_valid_approval,
    create_proposal,
)


def _db_status(db_path: str, intent_hash: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM order_approvals WHERE order_intent_hash=?",
            (intent_hash,),
        ).fetchone()
        assert row is not None
        return str(row[0])


def test_approved_then_consume_is_single_use(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    now = time.time()
    intent_hash = "hash-single-use"
    ok, reason = create_proposal(
        intent_hash=intent_hash,
        approver_id="approver-1",
        expires_at=now + 120,
        channel="cli",
        metadata={"reason": "unit-test"},
    )
    assert ok is True, reason

    approve(intent_hash, "approver-1")
    ok, reason = consume_valid_approval(intent_hash, now=now + 1)
    assert ok is True, reason
    assert _db_status(db_path, intent_hash) == "USED"

    ok, reason = consume_valid_approval(intent_hash, now=now + 2)
    assert ok is False
    assert reason == "approval_used"


def test_expired_approval_cannot_be_consumed_and_transitions_expired(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    now = time.time()
    intent_hash = "hash-expired"
    ok, reason = create_proposal(
        intent_hash=intent_hash,
        approver_id="approver-1",
        expires_at=now + 1,
        channel="telegram",
        metadata={},
    )
    assert ok is True, reason
    approve(intent_hash, "approver-1")
    ok, reason = consume_valid_approval(intent_hash, now=now + 2)
    assert ok is False
    assert reason == "approval_expired"
    assert _db_status(db_path, intent_hash) == "EXPIRED"


def test_different_intent_hash_does_not_match(monkeypatch, tmp_path):
    db_path = str(tmp_path / "trades.db")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", db_path, raising=False)
    now = time.time()
    ok, reason = create_proposal(
        intent_hash="hash-a",
        approver_id="approver-1",
        expires_at=now + 120,
        channel="cli",
        metadata={},
    )
    assert ok is True, reason
    approve("hash-a", "approver-1")
    ok, reason = consume_valid_approval("hash-b", now=now + 1)
    assert ok is False
    assert reason == "approval_missing"
