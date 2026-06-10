"""P0 regression: allow_stale_quotes gate contract.

Gap closed: GAP-01 from qa-coverage-gaps-20260610.md

Invariant under test:
  When allow_stale_quotes=True the gate must return:
    - allowed_for_live_execution  == False
    - allowed_for_paper_execution == False
    - advisory_only               == True
    - 'ALLOW_STALE_QUOTES_ACTIVE' in blockers

  This must hold even when every other feed health field reports OK.

No production code is modified by this file.
"""
from __future__ import annotations

import pytest

from core.feed_freshness_gate import assess_feed_freshness_gate


# ---------------------------------------------------------------------------
# Shared fixture helpers – mirroring the pattern from test_feed_freshness_gate.py
# ---------------------------------------------------------------------------

def _freshness(**overrides):
    payload = {
        "ok": True,
        "state": "OK",
        "market_open": True,
        "allow_stale_quotes": False,
        "reasons": [],
        "ltp": {
            "ok": True,
            "age_sec": 0.4,
            "max_age_sec": 2.5,
            "required": True,
            "source": "feed_runtime_latest",
        },
        "depth": {
            "ok": True,
            "age_sec": 1.0,
            "max_age_sec": 6.0,
            "required": True,
            "source": "feed_runtime_latest",
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# P0 — Core gap assertion
# ---------------------------------------------------------------------------

def test_allow_stale_quotes_never_produces_live_execution_eligibility():
    """
    The baseline healthy-feed payload is known to produce FRESH +
    allowed_for_live_execution=True (verified by
    test_clean_market_open_fresh_feed_allows_execution in
    test_feed_freshness_gate.py).

    Flipping allow_stale_quotes=True while keeping every other field healthy
    must downgrade the decision to ADVISORY_ONLY and unconditionally block
    both live and paper execution.
    """
    decision = assess_feed_freshness_gate(
        _freshness(allow_stale_quotes=True, state="PLANNING")
    )

    # Execution eligibility must be blocked — both live and paper
    assert decision.allowed_for_live_execution is False, (
        "allow_stale_quotes=True must never produce allowed_for_live_execution=True"
    )
    assert decision.allowed_for_paper_execution is False, (
        "allow_stale_quotes=True must never produce allowed_for_paper_execution=True"
    )
    # The gate must be advisory, not blocked (blocked is reserved for hard failures)
    assert decision.advisory_only is True
    assert decision.gate_state == "ADVISORY_ONLY"
    # The canonical blocker reason must be present so callers can audit it
    assert "ALLOW_STALE_QUOTES_ACTIVE" in decision.blockers
    # Immutability contract
    assert decision.is_order_action is False
    assert decision.append is False


def test_allow_stale_quotes_with_explicitly_fresh_ltp_still_not_executable():
    """
    Even when ltp.ok=True and ltp.age_sec is very recent (0.1s),
    allow_stale_quotes=True must still block execution.
    The stale-quotes flag is a session-level override, not a per-tick flag.
    """
    decision = assess_feed_freshness_gate(
        _freshness(
            allow_stale_quotes=True,
            state="PLANNING",
            ltp={"ok": True, "age_sec": 0.1, "max_age_sec": 2.5, "required": True},
        )
    )

    assert decision.allowed_for_live_execution is False
    assert decision.allowed_for_paper_execution is False
    assert decision.advisory_only is True
    assert "ALLOW_STALE_QUOTES_ACTIVE" in decision.blockers


def test_allow_stale_quotes_false_does_not_suppress_clean_feed():
    """
    Baseline sanity: allow_stale_quotes=False with a clean feed must still
    allow live execution, confirming the flag comparison is correct.
    """
    decision = assess_feed_freshness_gate(_freshness(allow_stale_quotes=False))

    assert decision.allowed_for_live_execution is True
    assert decision.allowed_for_paper_execution is True
    assert decision.advisory_only is False
    assert "ALLOW_STALE_QUOTES_ACTIVE" not in decision.blockers


@pytest.mark.parametrize("state", ["PLANNING", "OFFHOURS", "DEGRADED"])
def test_allow_stale_quotes_never_executable_across_states(state):
    """
    Parametrized across state values that could co-occur with
    allow_stale_quotes=True.  Each combination must produce
    allowed_for_live_execution=False.
    """
    decision = assess_feed_freshness_gate(
        _freshness(allow_stale_quotes=True, state=state, ok=(state != "DEGRADED"))
    )

    assert decision.allowed_for_live_execution is False, (
        f"allow_stale_quotes=True in state={state!r} must block live execution"
    )
    assert decision.allowed_for_paper_execution is False, (
        f"allow_stale_quotes=True in state={state!r} must block paper execution"
    )


def test_allow_stale_quotes_decision_is_not_order_action_and_is_read_only():
    """
    Safety envelope: the decision object itself must declare it is not an
    order action and must not allow appends, regardless of stale-quote state.
    """
    for flag in (True, False):
        decision = assess_feed_freshness_gate(_freshness(allow_stale_quotes=flag))
        assert decision.is_order_action is False, "feed gate decision must never be an order action"
        assert decision.append is False, "feed gate decision must not be appendable"
