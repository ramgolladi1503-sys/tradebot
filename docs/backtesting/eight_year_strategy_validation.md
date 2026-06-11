# Eight-Year Strategy Validation

## Purpose

This Phase 1 surface answers what historical data is actually available before any long-horizon backtest claims are made.

It does not place orders, call broker APIs, weaken live gates, or invent option history that does not exist.

## Commands

Diagnostics:

```bash
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
```

Catalog scan:

```bash
python scripts/import_historical_data.py --config configs/backtest_8y.example.json --dry-run
```

## Honest mode meanings

- `TRUE_OPTIONS_INTRADAY`: real intraday option candles or ticks exist with sufficient span and symbol coverage.
- `OPTIONS_EOD`: only daily option contract history exists.
- `UNDERLYING_SIGNAL_WITH_OPTION_PROXY`: underlying or futures history exists, but option behavior would be proxy-only.
- `LIVE_CAPTURE_REPLAY`: only runtime-captured replay evidence exists.
- `HYBRID`: underlying and some real option coverage exist, but not necessarily enough for full eight-year intraday realism.

## Verdict meanings

- `READY_FOR_PHASE_2`: true intraday option history appears sufficient to proceed with execution-layer work.
- `BLOCKED_BY_DATA_SCHEMA`: files exist but required columns are missing or malformed.
- `INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS`: lower-confidence modes are possible, but true eight-year intraday option proof is not.
- `NEED_USER_HISTORICAL_DATA`: local historical inputs are too sparse to support meaningful progress.

## Questions Phase 1 answers

1. What historical data exists?
2. What symbols are covered?
3. What dates are covered?
4. Do we have true intraday option data?
5. Do we only have EOD/proxy/runtime replay data?
6. Which backtest modes are feasible?
7. What exact fields are missing?
8. Is true eight-year intraday options backtesting possible or inconclusive?

## Safety boundary

Phase 1 is read-only evidence work. Fallback, synthetic, recovered, stale, or proxy data must never be mislabeled as real executable intraday options proof.
