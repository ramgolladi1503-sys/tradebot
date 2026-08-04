# Agent Review — Gravity-Well Multi-Session Replay Update (2026-08-04)

## Scope reviewed

Evidence-only update to draft PR #785 using the uploaded `kite_candidate_replay(11).zip`. No production strategy, runtime, ranking, risk, broker, order, dashboard, or execution path is changed.

## Source integrity

- source ZIP SHA-256: `f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d`;
- 1,509 Parquet files discovered and 1,509 parsed;
- 493 independent NIFTY sessions and 36,849 completed five-minute rows;
- all underlying authority flags were non-synthetic, non-fallback and non-mock;
- every underlying volume value was zero;
- no NIFTY constituent bars existed;
- all 30 option files were explicitly named `OPT_MOCK` and lacked expiry, strike, CE/PE and immutable contract identity.

## Causal and statistical controls

- completed-bar features only;
- prior-completed 15-minute and 30-minute levels;
- next-bar entries;
- chronological 295/99/99 development/validation/sealed-holdout split;
- 2 bps primary and 5 bps severe cost stress;
- session bootstrap intervals;
- top-winner and top-session removal;
- predeclared EMA-centre neighbours 14 and 30;
- matched random baselines;
- holdout performance never calculated.

## Review findings

- escape acceptance failed clearly in validation: `-3.49 bps` after 2 bps costs, PF `0.39`, 95% session CI `[-5.23, -1.90]`;
- cluster-break acceptance failed: `-3.96 bps`, PF `0.46`;
- failed escape showed `+0.77 bps` across only seven validation trades, then collapsed under severe costs, winner removal, session removal and both centre-length neighbours;
- no diagnostic family survived the frozen gates.

## Final review verdict

```text
DATA_BLOCKED_MISSING_VOLUME_CONSTITUENTS_AND_REAL_OPTIONS
NO_PRICE_ONLY_VALIDATION_SURVIVOR
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

The full volume + participation + real-option hypothesis remains untested, not validated. The available price-only substitute has been falsified strongly enough that further threshold tuning would be post-selection.
