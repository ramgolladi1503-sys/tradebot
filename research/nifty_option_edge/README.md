# NIFTY Direction + Magnitude -> Option Translation V1

## Research question

Can a timestamp-safe NIFTY forecast identify both the **direction** and a **large enough 15–30 minute move** to justify buying a CE or PE after realistic option frictions, and can the best strike be selected prospectively from ATM/ITM/OTM candidates?

## Scope

This package is research-only. It does not place orders, call a broker, mutate live strategy thresholds, or claim an options edge from underlying-only data.

### Phase A — Underlying edge

For each completed NIFTY decision bar, labels are generated from the **next legal bar open** for 15, 20 and 30 minute horizons. Measured outcomes include:

- signed terminal move in points and bps
- absolute move
- direction
- maximum favorable/upward excursion
- maximum downward excursion
- threshold events (default 15/25/40/60 points)

A forecast should provide at minimum:

- `probability_up`
- `expected_signed_points`

It is evaluated on both direction and magnitude. Selective evaluation requires both a probability threshold and a minimum expected move; therefore a forecast can be directionally correct but still produce `NO_TRADE` when the move is too small.

### Phase B — Prospective strike translation

`rank_option_strikes` accepts a real option-chain snapshot plus an underlying forecast. It:

1. maps bullish -> CE and bearish -> PE;
2. compares ATM and configurable nearby ITM/OTM strikes;
3. requires bid, ask and delta;
4. rejects invalid quotes, excessive spread, insufficient forecast probability or insufficient expected NIFTY movement;
5. estimates premium response using delta plus gamma/theta when supplied;
6. subtracts full current spread plus caller-supplied slippage/fees;
7. emits `NO_TRADE` if the best candidate has non-positive expected net premium change.

The output claim boundary is explicitly `OPTION_TRANSLATION_APPROXIMATION_NOT_REALIZED_PNL`.

### Phase C — Real option-P&L certification

A tradable options edge **cannot** be certified from OHLCV plus Greek approximations. Historical selection needs authoritative timestamped option-chain snapshots at decision/entry time and an authoritative future quote path for the exact selected instrument.

For a long option, realized evaluation is conservative:

- enter at actual ask;
- exit at actual bid;
- subtract explicit slippage and fees;
- use the lot size supplied by the authoritative instrument metadata for that date.

Only this layer may use the claim boundary `REAL_OPTION_QUOTES_ASK_TO_BID_REALIZED_PNL`.

## Required experimental comparisons

At each horizon, compare:

1. direction-only selection vs direction + magnitude selection;
2. ATM vs one/two strikes ITM vs one/two strikes OTM;
3. ranking by expected premium points vs expected return on premium;
4. CE and PE independently rather than assuming symmetry;
5. raw signal vs cost-qualified signal;
6. all signals vs high-confidence/high-magnitude selective signals.

Do not tune these choices on locked holdout data.

## Immediate blocker for full certification

The current repository discovery pipeline explicitly marks historical option evidence unavailable when authoritative bid/ask paths are not supplied. Therefore V1 can establish or reject an **underlying direction+magnitude edge** now, and can test the prospective strike-selection contract on live/synthetic snapshots, but it must not claim historical strike-level profitability until real option quote paths are available.
