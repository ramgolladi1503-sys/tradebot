# Four Strategy Authoritative Math Audit

Final verdict: `FOUR_STRATEGY_MATH_AUDIT_COMPLETE_WITH_REPAIRS_AND_AMBIGUITIES`

## opening_range_retest_v1
Verdict: `ORB_OBJECTIVE_DEFECTS_REQUIRE_REPAIR`
Actual thesis: Production is a single completed-context breakout-near-boundary snapshot gated by minutes_since_open, spot, vwap, orb_high/orb_low; it does not encode prior breakout event, later retest event, hold event, or resume event as separate temporal stages.
Reachability: The current snapshot gate is theoretically reachable; true temporal retest reachability cannot be assessed because stages are not represented.
Objective defects: 1
Design ambiguities: 1

## trend_pullback_v1
Verdict: `TREND_PULLBACK_STRATEGY_INTENT_AMBIGUOUS`
Actual thesis: Production gates on TREND_UP/TREND_DOWN score and spot proximity/resume distance versus nearest support/resistance fallback to VWAP; no trend duration, impulse magnitude, pullback history, or structure-break sequence is represented in the strategy file.
Reachability: The score gates are theoretically reachable from MovementRegimeClassifier, but exact production-context historical truth remains blocked/missing from prior readiness gate.
Objective defects: 0
Design ambiguities: 1

## compression_breakout_v1
Verdict: `COMPRESSION_STRATEGY_INTENT_AMBIGUOUS`
Actual thesis: Production score averages range-width component, ATR short/long component, and regime COMPRESSION, then breaks nearest_resistance/orb_high/day_high or nearest_support/orb_low/day_low. Available proxy owner uses session-prefix range, not local contracted range; breakout fallback can trade ORB/day anchors rather than the measured compression range.
Reachability: Theoretically reachable: all three compression components can reach 1. Empirically under production-regime proxy, strategy score max was 0.4242 and pass count was zero: THEORETICALLY_REACHABLE_BUT_EMPIRICALLY_ZERO / REACHABLE_ONLY_UNDER_EXTREME_COMBINATIONS.
Objective defects: 0
Design ambiguities: 1

## vwap_reclaim_rejection_v1
Verdict: `VWAP_RECLAIM_STRATEGY_INTENT_AMBIGUOUS`
Actual thesis: Production checks current distance from ctx.vwap and confirmation metadata or immediate previous_spot_ltp crossing VWAP. It does not itself validate completed-history establishment, hold, duplicate/order/session/symbol integrity, or distinguish rejection from reclaim beyond metadata flags.
Reachability: The distance gate is theoretically reachable for FRACTION units between 0.00035 and 0.0035; edge testing readiness depends on freezing a history/VWAP owner and temporal sequence.
Objective defects: 0
Design ambiguities: 1

## Safety
No backtest, forward returns, P&L, parameter tuning, Git, or production modifications were performed.
