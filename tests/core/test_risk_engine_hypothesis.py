import pytest
from hypothesis import given, strategies as st
from core.risk_engine import RiskEngine

# Strategies for generating random portfolios
portfolio_strategy = st.fixed_dictionaries({
    "capital": st.floats(min_value=1.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
    "equity_high": st.floats(min_value=1.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
    "daily_profit": st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    "daily_loss": st.floats(min_value=-100000.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    "trades_today": st.integers(min_value=0, max_value=100),
    "open_risk_pct": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "regime": st.sampled_from(["NEUTRAL", "TREND", "RANGE", "EVENT"])
})

@given(portfolio=portfolio_strategy)
def test_risk_engine_daily_loss_limit_hypothesis(portfolio):
    engine = RiskEngine()
    # Force the daily loss to exceed the limit
    # The max daily loss is typically around 0.15 * multiplier
    equity = portfolio["equity_high"]
    
    # Calculate what the max daily loss limit is
    regime = portfolio["regime"]
    daily_loss_limit = abs(engine.max_daily_loss_pct) * engine._daily_loss_mult_for_regime(regime)
    
    # Force a loss greater than the limit
    portfolio["daily_loss"] = - (daily_loss_limit + 0.01) * equity
    portfolio["daily_profit"] = 0.0 # No profit to offset
    
    # Update daily_pnl_pct
    portfolio["daily_pnl_pct"] = (portfolio["daily_profit"] + portfolio["daily_loss"]) / equity
    
    allowed, reason = engine.allow_trade(portfolio, regime=regime)
    
    # Invariant: If loss exceeds limit, trade MUST NOT be allowed
    assert not allowed
    # It might hit drawdown lock, loss limit, or other gates, but it must be False.
    assert reason in ("Daily loss limit hit", "Daily drawdown lock hit", "Daily profit lock hit") or "hit" in reason


@given(portfolio=portfolio_strategy)
def test_risk_engine_max_trades_limit_hypothesis(portfolio):
    engine = RiskEngine()
    regime = portfolio["regime"]
    max_trades_limit = max(1, int(engine.max_trades * engine._max_trades_mult_for_regime(regime)))
    
    # Force trades_today over the limit
    portfolio["trades_today"] = max_trades_limit + 1
    
    allowed, reason = engine.allow_trade(portfolio, regime=regime)
    
    # Invariant: If trade count exceeded, must block
    # Note: It might block for other reasons first (like loss limit), but it must NOT be allowed.
    assert not allowed


@given(portfolio=portfolio_strategy)
def test_risk_engine_open_risk_limit_hypothesis(portfolio):
    engine = RiskEngine()
    regime = portfolio["regime"]
    open_risk_limit = engine.max_open_risk_pct * engine._open_risk_mult_for_regime(regime)
    
    # Force open risk over limit
    portfolio["open_risk_pct"] = open_risk_limit + 0.01
    
    allowed, reason = engine.allow_trade(portfolio, regime=regime)
    
    # Invariant: Must not be allowed
    assert not allowed
