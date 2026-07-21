# ML Strategy Discovery Core

Research-only pipeline for discovering interpretable deterministic strategy hypotheses from completed historical bars.

## What it does

1. validates and normalizes OHLCV bars
2. computes causal point-in-time features
3. creates path-dependent ATR barrier labels
4. assigns deterministic regimes
5. performs chronological development/validation/holdout splitting
6. trains a shallow tree and XGBoost on development data only
7. extracts frozen human-readable tree rules
8. evaluates rules on validation data with negative controls and stability tests
9. writes a research evidence manifest

## What it does not do

- place or approve orders
- modify production ML
- treat spot returns as option returns
- fabricate option fields
- unlock the holdout automatically
- certify structural edge

## Run

```bash
python scripts/run_ml_strategy_discovery.py \
  --bars /path/to/completed_ohlcv.parquet \
  --instrument NIFTY \
  --output-dir /path/to/evidence
```

Optional quote data may be supplied with `--option-quotes`, but this release only audits quote availability. Full option-path labeling must use the strict option replay system after candidate freezing.
