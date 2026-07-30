# SENSEX Late-Session Convexity V1 Data Readiness

Final verdict: `INVALID_DATA_ACQUISITION`

## Answers
1. Complete SENSEX underlying candles: NOT_PROVEN_COMPLETE.
2. Historically valid SENSEX constituent panel: NO.
3. Historical weights: not proven; approximate/equal-weight panels only if later sourced and labelled.
4. Expiry regimes covered: UNRESOLVED
5. Historical SENSEX option tokens recovered: 0.
6. Expiries with usable option OHLCV: 0.
7. Normal-day versus expiry-day underlying discovery: BLOCKED until complete underlying plus calendar audit passes.
8. Constituent-event-graph discovery: BLOCKED until historical constituent membership/weights and >=27/30 coverage pass.
9. Option-premium discovery: BLOCKED unless recovered tokens also produce complete OHLCV.
10. Without historical bid/ask: no executable entry/exit, spread, profitability, or production-readiness claims.

## Kite Limitation
- Kite historical candles are fetched by instrument_token. Implication: Symbol-only recovery is insufficient for historical candles.
- The current Kite instrument master describes currently tradable instruments. Implication: Current dumps are not a complete registry of expired derivatives.
- Expired futures and options receive contract-specific instrument tokens. Implication: A token cannot be inferred from the underlying symbol alone.
- Expired option tokens generally cannot be rediscovered from the current instruments dump. Implication: Historical option acquisition needs cached old dumps, sidecars, old files, or still-live contracts.
- Kite continuous history does not solve intraday expired-option retrieval. Implication: Continuous mode is not a substitute for expired option token authority.
- Current contracts must not be substituted for expired contracts. Implication: Any option lane without recovered contract tokens remains blocked.

## Inventory Summary
- Sources indexed: 1638
- SENSEX-like sources: 1626
- Instrument/contract registries: 13

## Blockers
- Inventory was bounded to the active clean worktree and known immutable evidence subtrees; exhaustive traversal of every prior worktree/evidence file was too large for this interactive run.
- No complete historically valid SENSEX constituent membership and weight table was proven.
- SENSEX option token recovery did not verify any Kite historical lookups in this run.
- No complete one-minute raw/canonical acquisition was certified by the independent audit.
- Historical bid/ask is unavailable, so executable option certification remains impossible from OHLCV alone.
