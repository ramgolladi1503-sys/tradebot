# ML Strategy Discovery Core

Research-only pipeline for discovering interpretable deterministic strategy hypotheses from completed historical bars.

## What it does

1. validates and normalizes OHLCV bars
2. computes causal point-in-time features
3. creates same-session path-dependent ATR barrier labels for either LONG or SHORT discovery
4. assigns deterministic regimes
5. performs chronological whole-session development/validation/locked-holdout splitting
6. trains a shallow tree and XGBoost on development data only
7. extracts frozen human-readable tree rules
8. evaluates rules on validation data with negative controls and stability tests
9. writes a research evidence manifest

Rows without the complete configured future horizon inside the same trading session are excluded from model training. A next-session opening gap can therefore never satisfy an intraday target label.

## What it does not do

- place or approve orders
- modify production ML
- treat spot returns as option returns
- fabricate option fields
- automatically evaluate the locked holdout
- certify structural edge

## Run

Long-side discovery:

```bash
python scripts/run_ml_strategy_discovery.py \
  --bars /path/to/completed_ohlcv.parquet \
  --instrument NIFTY \
  --side LONG \
  --output-dir /path/to/evidence/long
```

Short-side discovery:

```bash
python scripts/run_ml_strategy_discovery.py \
  --bars /path/to/completed_ohlcv.parquet \
  --instrument NIFTY \
  --side SHORT \
  --output-dir /path/to/evidence/short
```

Optional quote data may be supplied with `--option-quotes`, but this release only audits quote availability. Full option-path labeling must use the strict option replay system after candidate freezing.
