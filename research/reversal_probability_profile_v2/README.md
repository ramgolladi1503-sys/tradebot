# RPP NIFTY Zone Interaction V2

## Purpose

This V2 implements the interpretation that actually matters for the public **Reversal Probability Profile** concept:

> **RPP is a market-memory / price-location engine first. It is not a direct next-bar reversal predictor.**

The profile answers:

> Where has price historically demonstrated repeated confirmed turning behavior?

The state machine then asks:

> What is price doing now when it reaches one of those historically important locations?

Only the second question is allowed to create a directional research event.

## What the displayed density means

Confirmed pivot highs and lows are placed into price bins, nearby bins are smoothed, and each bin is divided by the tallest profile bin.

Therefore:

```text
relative_density = smoothed_density_at_zone / maximum_smoothed_density
```

A score of `0.80` means the zone has 80% of the density of the strongest historical zone in the active profile. It does **not** mean there is an 80% calibrated probability that the next visit will reverse.

The implementation records this explicitly:

```text
relative_density_is_calibrated_probability=false
```

## Layer 1 — market memory / location

The causal location map contains:

- confirmed pivot highs and lows only;
- support clusters from smoothed pivot-low peaks;
- resistance clusters from smoothed pivot-high peaks;
- nearest support and resistance;
- relative density of each zone;
- ATR-normalized distance to each zone;
- maximum reversal-density zone;
- recent approach direction and ATR-normalized approach momentum.

### Non-negotiable pivot causality

With `pivot_right=5`, a pivot centered on bar `t` does not exist for research until bar `t+5` has closed.

The pivot is inserted into market memory at the confirmation bar. It is never backdated to the center bar.

## Layer 2 — interaction state machine

Every interaction is evaluated against the **previous completed bar's already-known zone**. The current bar is not permitted to generate a new support/resistance zone and then claim that it crossed the same newly-created zone.

The frozen states are:

### `NO_DECISION`

Price has not produced a sufficiently clear completed-bar interaction.

### `REJECTED`

Price touched a prior-known zone and closed back away from it.

- support rejection -> `BULLISH_REJECTED`
- resistance rejection -> `BEARISH_REJECTED`

The rejection is not emitted merely because intrabar price touched the level. The completed bar must close back away by the frozen rejection margin.

### `BROKEN`

Price closes materially through a prior-known zone for the first time.

- resistance broken upward -> bullish break context
- support broken downward -> bearish break context

**BROKEN is diagnostic only. It is not a forecast/trade event in V2.**

This prevents the experiment from treating a single first close through a level as confirmed acceptance.

### `ACCEPTED`

After a break, price remains materially beyond the zone for the frozen number of completed bars.

- accepted above former resistance -> bullish
- accepted below former support -> bearish

### `RECLAIMED`

After a break, price retests the broken zone and closes again in the breakout direction.

- broken resistance retested from above and held -> bullish reclaim
- broken support retested from below and held -> bearish reclaim

This explicitly captures the idea that a historically important reversal zone can switch roles after acceptance rather than automatically causing reversal.

## Forecast events

Only these close-confirmed states may become directional research events:

```text
REJECTED
ACCEPTED
RECLAIMED
```

`BROKEN` remains observable but cannot enter the forecasting sample.

A zone also must meet the already-frozen minimum relative-density requirement (`0.65`). The `0.80` threshold is recorded only as a high-density diagnostic; V2 does not search a threshold grid.

Directional mapping is mechanical:

```text
support rejection         -> bullish
resistance rejection      -> bearish
resistance acceptance     -> bullish
support acceptance        -> bearish
resistance->support hold  -> bullish reclaim
support->resistance hold  -> bearish reclaim
```

## Outcome contract

The research question is:

```text
historical location
    x current approach
    x completed interaction state
        -> next 15 / 20 / 30 minute NIFTY direction
```

Entry is the **next actual bar open**, so the same code works on 1-minute or 5-minute data without pretending a 1-minute fill exists in a 5-minute corpus.

Primary horizon: `15 minutes`  
Diagnostics: `20 minutes`, `30 minutes`

A 5 bps round-trip cost proxy is subtracted by default. This is an underlying directional cost proxy, not option fill certification.

## Negative controls

The fixed state-machine output must add value versus both:

1. **same-event approach momentum** at the exact event timestamps;
2. **+30 minute shifted-time control** preserving the original signal direction.

A positive result that is no better than simple momentum or a shifted clock effect is rejected.

## No threshold rescue / no candidate search

V2 does not train-select among reversal/breakout candidates.

The state machine is frozen before the physical result is read. Evaluation slices it chronologically without changing its parameters based on outcomes.

The final 63 sessions are removed **before** building the profile/state/outcome tables and remain sealed:

```text
sealed_tail_feature_rows_processed=0
sealed_tail_outcomes_processed=0
holdout_evaluated=false
```

## Verdict discipline

The strongest allowed research verdict is:

```text
ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY
```

That verdict is emitted only if every frozen gate passes. Otherwise the result remains:

```text
NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE
```

A negative result is a valid experiment. The runner exits successfully for a scientifically valid negative result; it does not convert failed edge gates into a process failure and it does not mutate thresholds to manufacture a pass.

## What this does NOT claim

This V2 does not claim:

- that relative density is calibrated reversal probability;
- that AlgoAlpha's private/exact Pine implementation has been copied;
- that the chosen research parameters are the author's defaults;
- that RPP itself has an edge;
- that CE/PE selection is profitable;
- that ATM/ITM/OTM strikes are validated;
- that live execution is authorized.

It is a causal, falsifiable implementation of the **market-memory -> zone interaction -> confirmation -> 15–30 minute direction** mechanism.
