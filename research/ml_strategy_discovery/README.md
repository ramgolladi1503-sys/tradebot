# ML Strategy Discovery Core

Research-only pipeline for discovering interpretable deterministic strategy hypotheses from completed historical bars.

## What it does

1. binds either a certified manifest-selected Upstox corpus or an explicit OHLCV file
2. makes START versus END bar timestamps explicit
3. uses bar end as the decision and feature-availability timestamp
4. validates and normalizes completed OHLCV bars
5. computes causal point-in-time features
6. creates same-session ATR barrier labels for separate LONG or SHORT discovery runs
7. assigns deterministic regimes
8. performs chronological whole-session development, validation, and locked-holdout splitting
9. trains a shallow tree and XGBoost comparison on development data only
10. freezes readable tree rules with source leaf ID, dataset hash, side, and imputation values
11. evaluates frozen rules on validation data with negative controls and stability slices
12. writes source, dataset, candidate, and research evidence manifests

Rows without the complete configured future horizon inside the same trading session are excluded. A next-session opening gap cannot satisfy an intraday target label.

## Timestamp rule

For a start-labelled one-minute source row at 09:15:

```text
bar_start_timestamp = 09:15
bar_end_timestamp = 09:16
decision_timestamp = 09:16
```

The row's high, low, close, and volume are not available at 09:15. Explicit-file input must declare `--timestamp-semantics START` or `END`; the CLI refuses to guess.

## What it does not do

- place, approve, modify, or cancel orders
- import or modify production ML inference
- treat underlying label returns as option P&L
- fabricate bid/ask, IV, OI, depth, liquidity, or strike selection
- enforce durable one-time holdout consumption without an external record
- certify strict option-replay WFA
- certify structural edge or profitability

## Run against the certified Upstox corpus

The source root must contain both the committed certified source manifest and the local `runtime/upstox_candidate_replay` files.

Long-side discovery:

```bash
python scripts/run_ml_strategy_discovery.py \
  --source-project-root /Users/madhuram/tradebot \
  --instrument NIFTY \
  --side LONG \
  --output-dir /path/to/evidence/nifty-long
```

Short-side discovery:

```bash
python scripts/run_ml_strategy_discovery.py \
  --source-project-root /Users/madhuram/tradebot \
  --instrument NIFTY \
  --side SHORT \
  --output-dir /path/to/evidence/nifty-short
```

The default manifest is:

`docs/agent_reviews/opening_range_retest_causal_replay_source_manifest_v2.json`

Every selected parquet file is contained beneath `runtime/upstox_candidate_replay`, SHA-256 checked, reopened, schema checked, and verified as a complete 375-row Asia/Kolkata session before use.

## Run against an explicit file

```bash
python scripts/run_ml_strategy_discovery.py \
  --bars /path/to/completed_ohlcv.parquet \
  --timestamp-semantics START \
  --source-timezone Asia/Kolkata \
  --bar-interval-minutes 1 \
  --strict-bar-cadence \
  --instrument NIFTY \
  --side LONG \
  --output-dir /path/to/evidence/explicit-long
```

Optional quote data may be supplied with `--option-quotes`, but this release only audits quote availability. Full option-path labeling and executable Profit Factor must use the strict option replay system after candidate freezing.
