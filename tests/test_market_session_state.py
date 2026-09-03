from datetime import datetime

from core.market_session_state import MARKET_CLOSED, MARKET_OPEN, PREMARKET, derive_market_session_policy
from core.time_utils import IST_TZ


def test_nse_fno_premarket_is_observation_only():
    for hour, minute, second in ((9, 0, 0), (9, 14, 59)):
        policy = derive_market_session_policy(
            now=datetime(2026, 9, 3, hour, minute, second, tzinfo=IST_TZ),
            segment="NSE_FNO",
        )
        assert policy.market_state == PREMARKET
        assert policy.fresh_ticks_required is False
        assert policy.persistence_advancement_required is False
        assert policy.strategies_active is False
        assert policy.cas_active is False


def test_nse_fno_open_boundary_starts_live_evidence_at_0915():
    policy = derive_market_session_policy(
        now=datetime(2026, 9, 3, 9, 15, 0, tzinfo=IST_TZ),
        segment="NSE_FNO",
    )
    assert policy.market_state == MARKET_OPEN
    assert policy.fresh_ticks_required is True
    assert policy.persistence_advancement_required is True
    assert policy.cas_active is True


def test_before_premarket_remains_closed():
    policy = derive_market_session_policy(
        now=datetime(2026, 9, 3, 8, 59, 59, tzinfo=IST_TZ),
        segment="NSE_FNO",
    )
    assert policy.market_state == MARKET_CLOSED
