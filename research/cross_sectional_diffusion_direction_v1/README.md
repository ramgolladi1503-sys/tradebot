# Cross-Sectional Diffusion Direction V1

Campaign ID: `HYP_CROSS_SECTIONAL_DIFFUSION_DIRECTION_V1`

## Research question

When a large share of the historically correct NIFTY constituents move coherently before the NIFTY has fully repriced, does the NIFTY/futures contract continue in that direction over the next 15 minutes strongly enough to remain positive after an explicit round-trip cost assumption?

This is a **derived executable hypothesis**. It is not claimed to be the exact strategy formula from any paper or website. Literature/source material motivates the information-diffusion mechanism; this repository owns and freezes the implementation choices below.

## Primary target

Primary horizon: **15 minutes**.

Secondary diagnostic horizon: **30 minutes**. The 30-minute result does not rescue a failed 15-minute primary verdict.

All features use only the decision bar and earlier bars. Execution is mapped to the **exact next-minute open**, not the decision close. Five-minute feature lookbacks and 15/30-minute exits use exact timestamp offsets; a missing bar is not silently replaced by the fifth observed row.

## Features

For constituent `i`:

`r_i,5(t) = ln(C_i(t) / C_i(t-5))`

For NIFTY:

`r_N,5(t) = ln(C_N(t) / C_N(t-5))`

Using historical index weights when they are authoritative, otherwise using explicitly declared equal weights across the historically valid membership universe:

`B_5(t) = sum_i w_i * sign(r_i,5(t))`

`I_5(t) = sum_i w_i * r_i,5(t)`

`G_5(t) = I_5(t) - r_N,5(t)`

`B_5` is breadth, `I_5` is constituent impulse, and `G_5` is the diffusion/lag gap.

Equal weighting is a deliberate feature definition when official historical weights are absent. It must never be described as an official index-weight reconstruction.

## Frozen parameter family

Only four train-selected threshold combinations are allowed:

- breadth quantile: `0.80` or `0.90`
- gap quantile: `0.75` or `0.90`

Threshold values are estimated on the training fold only. No threshold may be fitted on the OOS test sessions.

Long signal:

- breadth >= train long breadth quantile
- impulse > 0
- gap >= train long gap quantile

Short signal:

- breadth <= train short breadth quantile
- impulse < 0
- gap <= train short gap quantile

Signals are de-overlapped by the evaluation horizon in clock time so repeated adjacent minutes do not create artificial sample size.

## Walk-forward

The canonical runner uses rolling trading-session folds rather than calendar-year folds:

- 252 completed sessions training
- 63 completed sessions OOS test
- 63-session step
- at least 4 OOS folds required for a positive terminal verdict

This structure is intentional. A 3-year-train/1-year-test annual split can yield only one fold when constituent authority begins in 2023, which is not enough to establish regime stability.

Each fold independently selects one of the four frozen parameter combinations using training-only after-cost session-equal mean return, freezes that choice, and evaluates the next 63 sessions.

## Incremental-value baseline

Every selected diffusion signal is compared with a NIFTY-momentum-only baseline. The baseline uses only `r_N,5` and is fitted to approximately the same long/short event frequency observed for the diffusion signal in the training fold.

A constituent signal cannot receive a positive terminal verdict if its OOS session-equal after-cost estimate does not exceed the index-only baseline estimate.

## Negative control

An exact 30-minute lagged constituent-feature control is evaluated with the same frozen thresholds. If the lagged control retains at least half of the main estimated effect, the campaign fails the negative-control gate.

This is intended to detect broad momentum/regime effects that are not genuinely tied to contemporaneous constituent diffusion.

## Execution and costs

The signal can be generated from NIFTY + constituents, but the chosen success criterion is after-cost tradability. The runner therefore requires a separate tradable execution series, preferably authoritative NIFTY futures minute OHLC.

Entry: execution-series open at exact `t+1 minute`.

Exit: execution-series close at exact `t+horizon`.

Gross signed return is converted to basis points and the user-supplied round-trip cost in bps is deducted from every event. There is deliberately **no zero-cost default**; the CLI requires `--roundtrip-cost-bps > 0`.

Minute OHLC plus a cost haircut does **not** prove exact historical bid/ask fills, queue position, depth, or market impact. Therefore the strongest positive verdict from this campaign is `ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY`, not an exact execution certification.

## Data authority

A positive verdict requires both:

1. authoritative effective-dated historical NIFTY membership, and
2. an authoritative tradable execution series.

Using today's NIFTY 50 basket across older years is survivorship-biased and is prohibited. The report records whether constituent features use historical official weights or historical-membership equal weights.

All four input sources are SHA-256 bound in the output report.

## Terminal positive verdict

`ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY` is emitted only when the 15-minute primary horizon satisfies all of the following:

- historical membership marked authoritative
- execution series marked authoritative
- at least 4 rolling OOS folds
- at least 100 OOS events
- at least 50 OOS sessions
- 95% session-bootstrap lower bound of after-cost return > 0
- at least 60% of OOS folds have positive session-equal after-cost return
- no single positive fold contributes more than 50% of total positive fold P&L
- lagged constituent control estimate < 50% of the main estimate
- main estimate > frequency-matched NIFTY-momentum-only baseline estimate

Otherwise the result is `NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE` with explicit blockers.

These gates are research-governance choices, not claims from an external source.

## Input schemas

Index/execution files:

- `timestamp` (aliases `datetime`, `date`, `ts` accepted)
- `open` (if absent, close is used by the generic loader, so such an execution file must **not** be marked authoritative)
- `close`

Constituent file(s):

- `timestamp`
- `symbol`
- `open` optional
- `close`

Membership file:

- `symbol`
- `effective_from`
- `effective_to` optional/open-ended
- `weight` optional

CSV and Parquet are supported. A directory may be supplied; supported files are concatenated recursively.

## Run

```bash
python scripts/run_cross_sectional_diffusion_direction_v1.py \
  --index /path/to/nifty_minute.parquet \
  --constituents /path/to/constituent_partitions \
  --membership /path/to/historical_nifty50_membership.csv \
  --execution /path/to/nifty_futures_minute.parquet \
  --roundtrip-cost-bps 3.0 \
  --membership-authoritative \
  --execution-authoritative \
  --output runtime/research/cross_sectional_diffusion_direction_v1/report.json
```

Do not set either authority flag merely to force a pass. They represent evidence claims that must be supported by the corpus/provenance registry.

## Current status

Implementation-ready / not yet empirically evaluated against the external local market-data corpus from this GitHub environment. No edge is claimed by the existence of this module.
