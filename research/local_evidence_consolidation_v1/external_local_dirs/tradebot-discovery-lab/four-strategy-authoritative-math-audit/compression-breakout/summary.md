# compression_breakout_v1

Verdict: `COMPRESSION_STRATEGY_INTENT_AMBIGUOUS`

Actual thesis: Production score averages range-width component, ATR short/long component, and regime COMPRESSION, then breaks nearest_resistance/orb_high/day_high or nearest_support/orb_low/day_low. Available proxy owner uses session-prefix range, not local contracted range; breakout fallback can trade ORB/day anchors rather than the measured compression range.

Reachability: Theoretically reachable: all three compression components can reach 1. Empirically under production-regime proxy, strategy score max was 0.4242 and pass count was zero: THEORETICALLY_REACHABLE_BUT_EMPIRICALLY_ZERO / REACHABLE_ONLY_UNDER_EXTREME_COMBINATIONS.

Objective defects: 0

Design ambiguities:
- No approved spec defines compression range owner as session-prefix, rolling local range, ORB range, or nearest level. ATR short/long periods vary by owner unless the ORB research proxy 5/30 convention is explicitly selected.
