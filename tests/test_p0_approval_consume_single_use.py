"""P0 regression: consume_valid_approval is single-use and cannot be
double-consumed or re-approved after USED state.

Gap closed: GAP-04 and GAP-05 from qa-coverage-gaps-20260610.md

Invariant under test:
  1. Once consumed, every subsequent call to consume_valid_approval returns
     (False, "approval_used").
  2. A record whose expires_at_epoch is in the past but whose status is still
     APPROVED (TOCTOU window simulation) must be rejected with
     "approval_expired", not consumed.
  3. A USED record cannot be re-approved via approve_order_intent.
  4. N rapid sequential consume calls after a single approve produce exactly
     1 success and N-1 "approval_used" rejections.

These tests do NOT place, modify or cancel any order.
No production code is modified by this file.
"""
from __future__ import annotations

import time

import pytest

from config import config as cfg
from core.approval_store import (
    approve_order_intent,
    consume_valid_approval,
    create_order_approval,
)
from core.execution_guard import OrderIntent


# ---------------------------------------------------------------------------
# Shared intent factory — mirrors test_order_approval_store.py pattern
# ---------------------------------------------------------------------------

def _intent(suffix="P0"):
    return OrderIntent(
        symbol="NIFTY",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        limit_price=101.0,
        product="MIS",
        exchange="NFO",
        strategy_id=f"TEST_{suffix}",
        timestamp_bucket=777000 + hash(suffix) % 1000,
        expiry="2026-06-26",
        strike=25000,
        right="CE",
        multiplier=1.0,
    )


# ---------------------------------------------------------------------------
# P0 — Double-consume must produce exactly one success then "approval_used"
# ---------------------------------------------------------------------------

def test_consume_valid_approval_is_single_use_first_call_succeeds(
    monkeypatch, tmp_path
):
    """
    Standard single-use contract: after one successful consume the record
    is USED and a second identical call must return approval_used.

    This is the core idempotency/single-use regression test.
    The existing test_consume_valid_approval_is_one_time in
    test_order_approval_store.py covers the same logic; this variant
    adds explicit assertions on the reason code for both calls to make
    the pass/fail surface unambiguous.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t1.db"), raising=False)
    h = _intent("SINGLE").order_intent_hash()

    ok, _ = approve_order_intent(h, approver_id="tester", ttl_sec=60)
    assert ok is True

    # First consume — must succeed
    ok1, reason1 = consume_valid_approval(h, approver_id="tester")
    assert ok1 is True, f"First consume must succeed; got reason={reason1!r}"

    # Second consume of the same hash — must be rejected
    ok2, reason2 = consume_valid_approval(h, approver_id="tester")
    assert ok2 is False, "Second consume must be rejected"
    assert reason2 == "approval_used", (
        f"Expected 'approval_used' on second consume, got {reason2!r}"
    )


def test_consume_valid_approval_n_rapid_calls_produce_exactly_one_success(
    monkeypatch, tmp_path
):
    """
    Sequential rapid calls: approve once, consume 5 times.
    Exactly one must succeed; the remaining 4 must return 'approval_used'.

    This is a sequential (not concurrent) proof of the single-use invariant.
    It is stronger than a two-call test because it confirms the USED state
    persists across 4 more retries.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t2.db"), raising=False)
    h = _intent("RAPID").order_intent_hash()

    ok, _ = approve_order_intent(h, approver_id="tester", ttl_sec=60)
    assert ok is True

    results = [consume_valid_approval(h, approver_id="tester") for _ in range(5)]

    successes = [(ok, r) for ok, r in results if ok is True]
    failures = [(ok, r) for ok, r in results if ok is False]

    assert len(successes) == 1, (
        f"Exactly 1 consume must succeed across 5 calls; got {len(successes)} successes"
    )
    assert all(r == "approval_used" for _, r in failures), (
        f"All failed calls must return 'approval_used'; got: {[r for _, r in failures]}"
    )


# ---------------------------------------------------------------------------
# P0 — TOCTOU window: past-expiry APPROVED row must be rejected
# ---------------------------------------------------------------------------

def test_expired_wall_clock_row_still_approved_in_db_is_rejected(
    monkeypatch, tmp_path
):
    """
    Simulates the TOCTOU window: a row is inserted with status=APPROVED but
    expires_at_epoch set to the past (now - 1 second).

    consume_valid_approval must detect the wall-clock expiry and return
    (False, "approval_expired"), not consume the record.

    This tests the check at line ~745 in approval_store.py:
        if now_epoch > expires: ... return False, "approval_expired"
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t3.db"), raising=False)
    h = _intent("TOCTOU").order_intent_hash()

    # Insert an APPROVED record that expired 1 second in the past
    expired_at = time.time() - 1.0
    ok, reason = create_order_approval(
        h,
        approver_id="tester",
        channel="cli",
        ttl_sec=60,  # TTL is irrelevant — we override expires_at_epoch directly
        status="APPROVED",
        expires_at_epoch=expired_at,
    )
    assert ok is True, f"Test setup: create_order_approval failed: {reason}"

    # Now try to consume — must be rejected due to wall-clock expiry
    ok, reason = consume_valid_approval(h, approver_id="tester")

    assert ok is False, (
        "consume_valid_approval must reject a record whose expires_at_epoch is in the past, "
        "even if the row status is APPROVED in the DB"
    )
    assert reason == "approval_expired", (
        f"Expected 'approval_expired' for past-expiry APPROVED row, got {reason!r}"
    )


def test_future_expiry_approved_row_is_consumable(monkeypatch, tmp_path):
    """
    Positive control: a record with expires_at_epoch in the future must be
    consumable. Ensures the expiry check in the test above is not a
    false positive.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t4.db"), raising=False)
    h = _intent("FUTURE").order_intent_hash()

    future_at = time.time() + 600.0
    ok, reason = create_order_approval(
        h,
        approver_id="tester",
        channel="cli",
        status="APPROVED",
        expires_at_epoch=future_at,
    )
    assert ok is True, f"Test setup failed: {reason}"

    ok, reason = consume_valid_approval(h, approver_id="tester")

    assert ok is True, (
        f"A future-expiry APPROVED record must be consumable; got reason={reason!r}"
    )


# ---------------------------------------------------------------------------
# P0 — USED record cannot be re-approved (no replay attack)
# ---------------------------------------------------------------------------

def test_used_approval_cannot_be_reapproved_after_consume(monkeypatch, tmp_path):
    """
    After a successful consume, calling approve_order_intent again for the
    same hash must return (False, "approval_already_used").

    This blocks a replay attack where an attacker re-approves a USED record
    to create a second consumable approval from the same hash.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t5.db"), raising=False)
    h = _intent("REPLAY").order_intent_hash()

    ok, _ = approve_order_intent(h, approver_id="tester", ttl_sec=60)
    assert ok is True

    ok, _ = consume_valid_approval(h, approver_id="tester")
    assert ok is True

    # Attempt to re-approve the now-USED record
    ok, reason = approve_order_intent(h, approver_id="attacker", ttl_sec=60)
    assert ok is False, "approve_order_intent must reject a USED record"
    assert reason == "approval_already_used", (
        f"Expected 'approval_already_used', got {reason!r}"
    )


# ---------------------------------------------------------------------------
# P0 — Missing hash is always rejected (no approval_hash_missing bypass)
# ---------------------------------------------------------------------------

def test_consume_with_empty_hash_is_rejected(monkeypatch, tmp_path):
    """
    Calling consume_valid_approval with an empty string hash must return
    (False, "approval_hash_missing") without touching the DB.
    Confirms the guard clause at the top of consume_valid_approval.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "t6.db"), raising=False)

    ok, reason = consume_valid_approval("", approver_id="tester")

    assert ok is False
    assert reason == "approval_hash_missing"
