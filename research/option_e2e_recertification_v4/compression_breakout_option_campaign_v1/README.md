# Compression Breakout Option Campaign V1

This is the first strategy-specific vertical slice for TradeBot's practical
historical options research lane.

It calls the production owner:

```text
strategies.movement.compression_breakout
→ generate_compression_breakout_candidates
```

It does not reimplement or tune the strategy thresholds.

## Causal signal contract

For each underlying session:

1. normalize one-minute completed OHLCV bars;
2. build session VWAP, rolling ATR and pre-breakout compression evidence;
3. use only bars at or before the signal bar;
4. freeze the prior 15-bar resistance/support and range width;
5. call the real movement regime classifier;
6. call the real Compression Breakout candidate generator;
7. map `BUY_CALL` to `BULLISH` and `BUY_PUT` to `BEARISH`;
8. rank strategy candidates without claiming execution-quality ownership;
9. emit a pre-outcome signal ledger;
10. partition sessions chronologically into development, validation and sealed holdout.

The default timestamp contract assumes source bars are start-labelled. A signal
on the 09:45 bar has a 09:46 feature cutoff and is eligible for the 09:46 option
bar open under the option-candle engine.

## Frozen option-economics screen

The campaign uses the existing `option_candle_backtest_v1` engine:

```text
signal
→ CE or PE
→ earliest eligible expiry
→ nearest ATM strike
→ next option-bar open
→ adverse slippage
→ stop-first OHLC path
→ costs
→ CE / PE / combined metrics
```

The frozen slippage grid is:

```text
0 / 25 / 50 / 100 bps per side
```

Controls:

- direction flip;
- one-bar delayed entry.

## Evidence limits

The strongest result is still candle-proxy evidence. This campaign never claims:

- historical ask-entry or bid-exit;
- market-depth availability;
- exact broker fills;
- paper or live readiness;
- production profitability.

Holdout option outcomes are rejected by the development/validation runner.

## CLI

Signal-ledger only:

```bash
python scripts/run_compression_breakout_option_campaign.py \
  --underlying-bars /path/to/underlying_1m.parquet \
  --output-dir /tmp/compression-breakout-signals-v1
```

Development option-candle campaign:

```bash
python scripts/run_compression_breakout_option_campaign.py \
  --underlying-bars /path/to/underlying_1m.parquet \
  --contract-catalog /path/to/development_contract_catalog.parquet \
  --option-bars /path/to/development_option_1m.parquet \
  --partition development \
  --output-dir /tmp/compression-breakout-option-development-v1
```

Use a session-bound contract catalogue. Do not supply holdout option bars to a
development or validation run.
