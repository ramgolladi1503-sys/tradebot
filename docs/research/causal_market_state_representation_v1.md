# Causal Market-State Representation V1

## Status

Implementation scaffold complete. Empirical validation is pending execution against the local historical corpus.

Current truthful verdict:

`MARKET_STATE_DATASET_BUILT_NOT_VALIDATED`

## Scope

This research layer creates descriptive state variables from completed bars only. It does not emit trades, alter strategy thresholds, or modify production execution.

Implemented families:

- trend persistence;
- compression and expansion;
- balance and imbalance;
- acceptance and rejection;
- participation;
- exact-option responsiveness;
- absorption and exhaustion proxies;
- observability and reliability.

## Causality

The implementation sorts by session and timestamp and computes rolling features from the current and earlier completed rows only. Prefix-invariance tests verify that appending future rows does not alter earlier state values.

Option-specific fields are never imputed from aggregate chain behaviour. When exact-option columns are unavailable, option states remain missing and `option_observable=0`.

## Required input columns

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Optional but preferred:

- `session_date`
- `vwap`
- `option_close`
- `option_volume`

The adapter for the full local exact-contract corpus remains the next integration step because those datasets are not stored in GitHub.

## Local execution

```bash
python scripts/run_causal_market_state_representation_v1.py \
  --input /absolute/path/to/input.parquet \
  --output-dir research/causal_market_state_representation_v1/evidence
```

Run tests with:

```bash
pytest -q tests/market_state/test_representation.py
```

## Outputs

- `market_state_dataset.parquet`
- `market_state_contract.json`
- `dataset_build_summary.json`

## What is not yet claimed

The implementation has not yet established that the state variables:

- predict future market behaviour;
- outperform time-of-day or indicator baselines;
- survive walk-forward analysis;
- support a profitable strategy.

Those claims require execution against the local historical corpus, frozen future-behaviour labels, chronological validation, controls, and an independent audit.
