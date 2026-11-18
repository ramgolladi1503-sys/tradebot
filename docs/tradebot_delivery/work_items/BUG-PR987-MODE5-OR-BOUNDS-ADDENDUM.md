# BUG-PR987-MODE5-OR-BOUNDS-ADDENDUM

## Accepted opening-range contract

This addendum records the approved Mode5 opening-range (OR) gate for PR #987. It does not change strategy thresholds or certify strategy performance.

- Before 09:45 Asia/Kolkata, one or more same-session spot ticks may establish partial OR bounds. Each accepted tick must have a finite positive price and a positive source timestamp no later than the decision timestamp. No minimum tick count, elapsed duration, or OR width is imposed.
- At or after 09:45 Asia/Kolkata, actionable Mode5 evaluation requires exactly 30 unique, timezone-aware minute-start candles for that same session, covering 09:15 through 09:44. Each OHLC value must be a finite positive JSON number; booleans and strings are invalid. Same-session rows at or after 09:45 are validated and excluded from the OR calculation. Malformed, duplicate, stale-session, incomplete, or otherwise invalid source data fails closed.
- The target index and its existing companion mapping must both have valid same-session OR evidence: NIFTY pairs with SENSEX; BANKNIFTY and SENSEX pair with NIFTY. The gate is checked at completed-bar evaluation and again under the advisor state lock immediately before local APM entry authorization. The lock is released before the existing dispatcher call.
- A failed gate yields an explicit abstention and prevents local APM entry authorization. Strategy thresholds and execution routing remain unchanged.

## Evidence and limitations

Focused offline tests cover exact/invalid candle coverage, later same-session row validation and exclusion, partial-bound causality and expiry, target/companion rejection, rollover between initial evaluation and final authorization, and dispatcher invocation after releasing the advisor lock. Tests mock all HTTP requests before advisor construction and use only a mock dispatcher.

The Upstox v2 provider's candle completeness, finality, timestamp semantics, and point-in-time availability are not independently established here. Matching this payload shape is a local structural check, not proof of provider guarantees. A race after the final locked authorization and before the downstream dispatcher consumes the request remains possible and cannot be prevented within this scope. This work does not establish fill correctness, GTT behavior, durable restart reconciliation, or profitability.

`allowed_for_live_execution=false`. Live readiness and strategy-efficacy claims remain blocked pending independent evidence and the remaining delivery gates.
