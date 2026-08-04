from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core.cas_close_structure import normal_strategy_entry_allowed
from core.decision_dag import _node_final_decision
from core.market_context import (
    SESSION_CAS_MATCHING,
    SESSION_CAS_ORDER_DISCOVERY,
    SESSION_CAS_RANDOM_CLOSE_WINDOW,
    SESSION_CAS_REFERENCE_TRANSITION,
    SESSION_DERIVATIVE_CONVERGENCE,
    SESSION_NORMAL_OPEN,
    SESSION_POST_CLOSE,
    derive_session_state_ist,
)
from core.session_calendar import is_open, minutes_to_close

IST = ZoneInfo("Asia/Kolkata")


def dt(year, month, day, hour, minute, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=IST)


def test_market_context_uses_new_cas_states_after_effective_date():
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 14, 59), segment="NSE_FNO") == SESSION_NORMAL_OPEN
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 15), segment="NSE_FNO") == SESSION_CAS_REFERENCE_TRANSITION
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 20), segment="NSE_FNO") == SESSION_CAS_ORDER_DISCOVERY
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 25), segment="NSE_FNO") == SESSION_CAS_RANDOM_CLOSE_WINDOW
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 30), segment="NSE_FNO") == SESSION_CAS_MATCHING
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 35), segment="NSE_FNO") == SESSION_DERIVATIVE_CONVERGENCE
    assert derive_session_state_ist(dt(2026, 8, 4, 15, 40), segment="NSE_FNO") == SESSION_POST_CLOSE


def test_session_calendar_distinguishes_cash_and_derivative_close():
    assert is_open(dt(2026, 8, 4, 15, 34), segment="NSE_EQ")
    assert not is_open(dt(2026, 8, 4, 15, 36), segment="NSE_EQ")
    assert is_open(dt(2026, 8, 4, 15, 38), segment="NSE_FNO")
    assert not is_open(dt(2026, 8, 4, 15, 41), segment="NSE_FNO")
    assert minutes_to_close(dt(2026, 8, 4, 15, 35), segment="NSE_FNO") == 5


def test_historical_sessions_before_rule_keep_1530_close():
    friday = dt(2026, 7, 31, 15, 29)
    assert is_open(friday, segment="NSE_FNO")
    assert not is_open(dt(2026, 7, 31, 15, 31), segment="NSE_FNO")
    assert derive_session_state_ist(friday, segment="NSE_FNO") == SESSION_NORMAL_OPEN
    assert derive_session_state_ist(dt(2026, 7, 31, 15, 31), segment="NSE_FNO") == SESSION_POST_CLOSE


@pytest.mark.parametrize(
    "state",
    [
        SESSION_CAS_REFERENCE_TRANSITION,
        SESSION_CAS_ORDER_DISCOVERY,
        SESSION_CAS_RANDOM_CLOSE_WINDOW,
        SESSION_CAS_MATCHING,
        SESSION_DERIVATIVE_CONVERGENCE,
    ],
)
def test_existing_decision_firewall_blocks_every_cas_state(state):
    class Payload:
        session_state = state
        execution_feed_ready = True
        is_order_action = False
        broker_api_called = False
        symbol = "NIFTY"
        ts_epoch = 1_785_837_500.0

    decision = _node_final_decision(Payload(), {}, {})
    assert not decision.ok
    assert "SESSION_NOT_NORMAL_OPEN" in decision.reasons


def test_old_late_day_entries_stop_before_cas():
    assert normal_strategy_entry_allowed(dt(2026, 8, 4, 15, 5), segment="NSE_FNO")
    assert not normal_strategy_entry_allowed(dt(2026, 8, 4, 15, 5, 1), segment="NSE_FNO")
    assert not normal_strategy_entry_allowed(dt(2026, 8, 4, 15, 15), segment="NSE_FNO")
