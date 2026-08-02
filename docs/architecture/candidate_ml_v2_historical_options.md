# Candidate ML V2: Historical Option Reconstruction

## Objective

This lane answers a narrower question than raw market pretraining:

> When frozen TradeBot strategy callables emitted historical NIFTY option intents, could causal information available at the signal timestamp have selected better post-cost option outcomes?

It consumes the immutable outputs of the audited historical replay campaign rather than reimplementing strategy or option-pricing logic inside the ML package.

## Input Contract

Required artifacts:

```text
canonical_option_intents.csv
option_trade_ledger.csv
option_replay_blockers.csv  # optional but recommended
```

The canonical intent ledger is produced from the historical Kite five-minute underlying corpus by frozen TradeBot strategy owners. The option trade ledger is produced by joining those intents to real Upstox expired-option one-minute OHLC with expiry, strike, CE/PE and contract identity.

Every input file is hashed before conversion. Intent and trade rows must agree on identity, strategy, underlying, option type and signal timestamp. Entry must occur after both the signal and requested entry time. Exit must occur after entry.

## Exact and Proxy Evidence

The lane creates two physically separate datasets:

```text
historical_option_exact_atm_dataset.parquet
historical_option_nearest_strike_proxy_dataset.parquet
```

Only exact-ATM rows may enter model fitting or certification. A nearest-strike row may be retained as research evidence only when its distance is within the configured cap. Exact and proxy identities may never overlap, and proxy rows are never silently mixed into training support.

## Label and Return Semantics

The binary label is whether the resolved option outcome is positive after the replay engine's recorded friction. `future_net_r` is unit net option P&L divided by the frozen option risk amount:

```text
risk_points = entry_premium * stop_loss_pct
future_net_r = unit_net_pnl / risk_points
```

The default stop percentage is 25%, matching the audited common option overlay used by the source replay. This is a research label, not a broker-fill claim.

## Causal Features

The exact-ATM model receives only fields available at the historical signal timestamp:

- call/put direction;
- underlying signal price;
- raw, confidence and price-structure scores emitted by the strategy candidate;
- blocker and warning counts;
- minute of session and cyclical time features;
- days to expiry;
- requested entry delay;
- ATM distance in strike steps.

Exit reason, exit price, option P&L, net return and resolution timestamp remain evaluation-only.

## Validation and Custody

The latest 20% of exact-ATM sessions is physically sealed when session support allows it. Research certification uses only the remaining chronological sessions, retains the configured minimum row gates, and applies the same purged walk-forward, calibration, permutation, delay, ablation and concentration controls as Candidate ML V2.

The nearest-strike proxy dataset and locked holdout are never consumed by this training command.

## Authority Boundary

```text
model_authority=REAL_OPTION_CANDLE_RESEARCH_ONLY
option_truth=UPSTOX_EXPIRED_OPTION_MINUTE_OHLC
execution_grade=false
nearest_strike_proxy_consumed=false
allowed_for_paper_execution=false
allowed_for_live_execution=false
```

Minute OHLC cannot prove historical bid/ask, depth, quote age, slippage, partial fills or intrabar ordering. Any model that survives this lane would still require a separate execution-grade shadow campaign.

## Local Campaign

The full Kite and Upstox archives are local Mac corpora and are not materialized in the main-based PR checkout. The source replay must first produce the three input artifacts using the audited PR #718 campaign. Candidate ML then runs:

```bash
python scripts/run_candidate_ml_historical_options.py \
  --intents-csv <campaign>/canonical_intents/canonical_option_intents.csv \
  --trade-ledger-csv <campaign>/option_replay/option_trade_ledger.csv \
  --blockers-csv <campaign>/option_replay/option_replay_blockers.csv \
  --output-root <campaign>/candidate_ml_historical_options
```

No outcome should be claimed until that command runs against the immutable local artifacts and its hashes, row counts, session support and certification report are recorded.
