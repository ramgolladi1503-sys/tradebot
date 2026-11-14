# Pre-Market Gap Evidence V1

## Status

Research/offline evidence only. No runtime wiring, broker calls, order authority, strategy authority, or live-execution authority.

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

## Purpose

Create a causal boundary between:

1. the pre-open gap nowcast frozen before the regular market open;
2. strict scoring against the actual opening print; and
3. post-open gap response such as retention, rejection, fill, and overfill.

The gap forecast is evidence. It is not a CE/PE signal.

## Why this exists

The legacy root `premarket.py` is a simple live-LTP/static-threshold bias helper. This research contract does not replace or modify it. V1 is deliberately isolated under `core.analytics` until prospective evidence proves that a richer gap model adds value.

## V1 deterministic baseline

The GIFT signal is basis-corrected. It never treats the absolute GIFT futures level as if it were the NIFTY cash index.

```text
previous_basis = gift_previous_settlement - previous_cash_close
implied_cash_open = gift_last - previous_basis
gift_gap_points = implied_cash_open - previous_cash_close
```

Algebraically, the last line is the GIFT contract's own move from its prior settlement. Keeping the basis calculation explicit prevents the common error of subtracting the previous NIFTY cash close directly from a current GIFT futures price.

The deterministic central estimate can then accept explicitly supplied, externally justified adjustments:

```text
central_gap = gift_gap_points + shock_adjustment_points + auction_adjustment_points
```

V1 does not invent shock coefficients or auction coefficients. Those adjustments must come from a later independently validated feature/estimation layer.

## Fail-closed conditions

The baseline returns `ABSTAIN` when any of these conditions are present:

- GIFT timestamp is later than the prediction cutoff (`FUTURE_DATA_VIOLATION`)
- GIFT observation is older than the allowed freshness window (`STALE_GIFT_DATA`)
- timestamps are not timezone-aware
- price/uncertainty values are invalid or non-finite
- auction adjustment is supplied without auction authority
- any evidence object attempts order, broker, append, or live-execution authority

No silent fallback is allowed.

## Prediction evidence

Each `PreMarketSnapshot` is immutable and receives a canonical SHA-256 over its prediction-time inputs, sources, model version, and authority envelope. The output records:

- previous futures/cash basis
- GIFT own-contract gap signal
- central gap estimate
- predicted cash open
- lower/upper gap interval
- gap class using a configurable flat band
- input-quality label
- immutable snapshot hash

Predictive confidence is intentionally not fabricated in V1. `input_quality` describes source freshness/availability, not model accuracy.

## Strict scoring

`score_gap_prediction()` compares the frozen prediction with the actual opening print and records independently:

- sign correctness
- gap-class correctness
- signed central error
- absolute central error
- interval hit/miss
- miss distance from the nearest interval boundary

An interval miss by one point remains a strict miss.

## Post-open response lane

`measure_gap_response()` is deliberately separate from the pre-open prediction. It calculates:

```text
actual_gap = actual_open - previous_close
gap_surprise = actual_gap - predicted_gap
retention_ratio = (current_price - previous_close) / actual_gap
fill_ratio = 1 - retention_ratio
```

States are:

- `CONTINUING`
- `RETAINING`
- `REJECTING`
- `FILLED`
- `OVERFILLED`
- `NO_GAP`

Post-open values never revise the frozen pre-open prediction.

## 21 Aug 2026 regression evidence

The tests encode the observed 21-Aug opening behavior as regression evidence.

### NIFTY

```text
previous close  = 24231.85
GIFT prev settle= 24294.00
GIFT snapshot   = 24326.00
basis           = +62.15
gift gap signal = +32.00
frozen interval = +20 .. +45
actual open     = 24284.05
actual gap      = +52.20
central abs err = 20.20
interval miss   = 7.20
```

With the V1 default +/-0.15% flat band, +32 points is still `FLAT`, while +52.2 points is `GAP_UP`; therefore strict class scoring is a failure even though the sign is correct. This avoids retroactively upgrading a borderline nowcast to a gap-up success.

At approximately 09:29, NIFTY at 24233.20 retained only about 2.6% of the opening gap, so the response state is `REJECTING`.

### BANK NIFTY

```text
previous close = 57495.90
actual open    = 57613.20
actual gap     = +117.30
09:30 price    = 57592.25
```

About 82% of the opening gap remained, producing `RETAINING` rather than copying NIFTY's rejection state.

### SENSEX

```text
previous close = 77537.72
actual open    = 77701.07
09:29 price    = 77508.95
```

Price crossed below the prior close, so the gap is `OVERFILLED`.

## Promotion boundary

V1 is not eligible for live/runtime promotion. Before any runtime wiring, the program should collect at least 20-50 prospective sessions and compare, out of sample:

1. GIFT-own-move baseline;
2. GIFT + official pre-open auction/weighted constituent breadth;
3. GIFT + auction + global/shock features;
4. only then, a more complex calibrated/nonlinear model.

A more complex model should not be promoted unless it beats the simpler baseline on prospective evidence, including magnitude error and interval calibration, not only directional hit rate.

## Next implementation lane

The next safe step is an offline collector/ledger workflow that writes prediction snapshots under `runtime/analytics/**`, reads them through `core.analytics.store`, and evaluates outcomes using the existing `core.analytics.outcome_replay` boundary. That work should remain shadow-only until separately reviewed and validated.

## Files intentionally not touched

- `premarket.py`
- `main.py`
- `run_live.sh`
- `config/`
- `strategies/`
- broker/order/risk/feed runtime paths
- credentials/secrets/env files
- live runtime artifacts
