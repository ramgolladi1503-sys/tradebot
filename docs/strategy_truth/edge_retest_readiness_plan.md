# Edge Retest Readiness Plan

## 1. Ready for Edge Retesting (Implementation Verified)
These strategies have hard test assertions proving fail-closed mapping and pipeline safety.
- `PRO_TREND_CONTINUATION`
- `PRO_MEAN_REVERSION`
- `PRO_MOMENTUM_BREAKOUT`
- `PRO_VOLATILITY_EXPANSION`
- `PRO_RANGE_FADE`
- `MEAN_REVERSION`
- `ORB_BREAKOUT`
- `VWAP_ORB`
- `VOLATILITY_SCALED_TREND`
- `INTRADAY_DIRECTIONAL`

## 2. Blocked: HTF Legacy Strategies
These strategies are blocked due to `IMPLEMENTATION_BUG_FOUND` and `PIPELINE_MUTATION_FOUND`.
- `HTF_OPENING_DRIVE_CONT`
- `HTF_15M_TREND_CONT`
- `HTF_15M_VWAP_PULLBACK`
- `HTF_FAILED_BREAKOUT_REVERSAL`
- `HTF_PDH_PDL_HOLD`

**Blocker Details:**
HTF strategies bypass Phase-2 and `TradeBuilder` ranking safety entirely, wiring into an offline script instead.

**Remediation Plan for HTF:**
Before retesting HTF edge, we must decide whether to:
1. Deprecate HTF offline paths entirely.
2. Port HTF logic into `TradeBuilder` and re-evaluate via standard execution gates.
