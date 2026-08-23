# HTF_RANGE_EXPANSION_CAUSAL_V1 — Dataset Authority Adjudication

Status: `ROBUSTNESS_REQUIRED`

Reason: `REQUIRED_1M_EXECUTION_CORPUS_NOT_AVAILABLE_UNDER_FROZEN_493_SESSION_IDENTITY`

## Frozen 493-session authority

The Strategy Certification Kernel lineage identifies a NIFTY corpus with:

- canonical lineage SHA-256: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- OHLC semantic SHA-256: `cd34d678aabdebeb49b1d4409f8ad4c516503e9a9a06312ba9c6740dd4302eb6`
- rows: 36,849
- sessions: 493
- frozen split: 394 development / 99 locked
- first locked session: `2026-02-10`

Recovered physical lineage points to:

`/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip`

with verified archive SHA-256:

`f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d`

However, committed schema evidence proves the archive contains `UNDERLYING_5M_OHLCV` for the index layer. Representative NIFTY daily files have 75 rows/session. No authoritative one-minute NIFTY layer exists in that archive.

The frozen `HTF_RANGE_EXPANSION_CAUSAL_V1` entry contract requires the next available **1-minute open** strictly after signal availability. Therefore the 493-session 5-minute authority cannot execute the frozen candidate without changing candidate identity.

No synthetic 1-minute reconstruction from 5-minute bars is permitted.

## Separate 1-minute authority

A deterministic canonical NIFTY one-minute warehouse exists at:

`/Users/madhuram/tradebot-repair-11-nifty-sessions-v1/research/unified_nifty_underlying_feature_warehouse_v1/canonical_nifty_1minute.parquet`

Committed evidence records:

- rows: 164,745
- complete sessions: 441
- start: `2024-09-26T09:15:00+05:30`
- end: `2026-07-21T15:29:00+05:30`
- timezone: `Asia/Kolkata`
- expected 1-minute bars/session: 375
- duplicate rows: 0
- incomplete sessions: 0
- OHLC violations: 0
- 1m↔5m reconciliation: `PASS`
- feature causality: `PASS_COMPLETED_BAR_ONLY`
- source hashes verified: true
- canonical 1m semantic SHA-256: `cf7a7c0e385e5f1ccefec772853b7b7b7acbea9c64e7a79c29e36e256a80646c`

Its broader warehouse audit remained `UNDERLYING_WAREHOUSE_PARTIALLY_READY` because of:

1. excluded sessions requiring authorized historical refetch;
2. zero volume on the spot-index source.

The zero-volume blocker is not material to an OHLC-only HTF candidate, but it must remain disclosed. Missing/excluded sessions must also remain explicit and cannot be silently filled.

This 441-session warehouse is NOT the 493-session canonical dataset and may not inherit its partition manifest or fingerprint.

## Decision

`HTF_RANGE_EXPANSION_CAUSAL_V1` remains:

`ROBUSTNESS_REQUIRED`

It is not rejected for economics; it is blocked by an information-resolution mismatch between its frozen next-1m entry rule and the only proven 493-session corpus.

The only legal continuation is a new identity bound to the 441-session one-minute corpus, e.g.:

`HTF_RANGE_EXPANSION_CAUSAL_1M_V1`

That successor must:

- hash the physical one-minute parquet locally;
- independently reproduce semantic SHA-256 `cf7a7c0e...`;
- freeze the exact 441-session universe and explicit missing/excluded sessions;
- create a new chronological partition from that universe before outcome access;
- inherit no historical HTF expectancy or paper authority;
- retain the causal volatility gate, 15m/30m alignment, gap exclusion, next-1m entry, OD stop, 2R target, and 15:15 time stop;
- keep validation/holdout unopened until DEV gates are passed.

Runtime authority remains `NONE`; broker actions remain forbidden.
