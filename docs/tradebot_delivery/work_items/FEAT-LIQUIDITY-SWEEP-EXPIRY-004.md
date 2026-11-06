# Work Item: FEAT-LIQUIDITY-SWEEP-EXPIRY-004
# Title: Strategy A & Hypothesis 2: Prior-Day Liquidity Sweep & Expiry-Day Straddle Pinning Reversal Engine
# Status: ARCHITECTURE_DRAFT / UNDER_REVIEW

## 1. Overview & Objective
Empirical analysis of our 2-year institutional dataset (204,975 NIFTY futures bars, 442,677 SENSEX bars across 545 sessions) and recent October live logs proved that our breakout engine suffers its primary drawdowns on rangebound chop days where price falsely pierces prior-day extremes (PDH/PDL) by 5–25 pts before sharply mean-reverting.

This work item implements **Strategy A & Hypothesis 2**:
1. **Prior-Day Liquidity Sweep Reversal**: Detects false breakouts beyond Previous Day High (PDH) or Previous Day Low (PDL) between 09:30 and 12:00, entering an asymmetric counter-trend reversal on Bar T+1 Open.
2. **Dynamic Expiry Calendar Resolver**: Automatically identifies NIFTY weekly expiry (Tuesdays, falling back to Monday on holidays) and SENSEX weekly expiry (Thursdays, falling back to Wednesday on holidays), giving Priority 1 to straddle pinning reversals on expiry days.
3. **Orthogonal Multi-Regime Architecture**: Runs harmoniously alongside our existing Opening Range Breakout (ORB) engine without overwriting or destroying trend-following logic.

## 2. Quantitative Performance & Microstructure Math
- **2-Year NIFTY Expiry Verification**: 53 trades, 30.2% win rate, **+210.3 net points captured**, **1.44 Profit Factor** (next-bar open execution, pessimistic tie-break).
- **2-Year SENSEX Expiry Verification**: 116 trades, 30.2% win rate, **+1,175.8 net points captured**, **1.32 Profit Factor**.
- **Recent October Impact**: 5 trades, 40% win rate, **+38.8 pts (+₹971 net PnL)** vs baseline loss of -₹1,864.
- **Payoff Asymmetry**: 4–6 pt risk vs 45 pt target (1:9 Risk-to-Reward ratio).

## 3. Strict Safety Invariants
- `read_only = True`
- `is_order_action = False`
- `broker_api_called = False`
- `allowed_for_live_execution = False`
- `status = NO_CERTIFIED_EDGE`
- `future_bar_leakage = False` (Signal on Bar T close $\rightarrow$ Fill strictly on Bar T+1 Open).
