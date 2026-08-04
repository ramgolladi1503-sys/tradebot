# Gravity-Well Research — Corrected Results

## Authoritative verdict

```text
PREVIOUS_SOURCE_FIDELITY_CLAIM_INVALID
PUBLISHED_DESCRIPTION_MODES_REBUILT
STATE_PRESERVED_ACROSS_SESSIONS
NO_PRICE_ONLY_PUBLISHED_MODE_VALIDATION_SURVIVOR
TRUE_VWMA_HYPOTHESIS_NOT_EVALUATED
REAL_OPTION_EDGE_NOT_EVALUATED
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

The earlier campaign did not faithfully evaluate the published Gravity Well Trend modes. It tested custom structural extensions and an EMA price-only substitute. Those results remain useful only as evidence about the custom extension families; they are not a valid verdict on the published indicator.

The corrected V2 study evaluates the published-description modes separately:

- `SOURCE_TREND_SLOPE`;
- `SOURCE_TREND_ACCEL_STRICT` as a stricter wording-sensitivity lane;
- `SOURCE_MIDLINE`;
- `SOURCE_BANDS_RECLAIM` with persistent hysteresis.

Directional state is preserved across sessions. Entries occur on the next bar, but outcomes are forced to remain within the same market session. An authoritative `TRUE_VWMA` calculation is implemented and fails closed when positive volume is unavailable.

## Data authority

- 493 NIFTY sessions;
- 36,849 completed five-minute rows;
- 295 development / 99 validation / 99 sealed-holdout sessions;
- zero nonzero-volume NIFTY rows;
- no constituent bars;
- all available option files are mock-named and lack immutable expiry, strike and CE/PE identity.

Therefore, only `UNIFORM_VOLUME_SMA` and `EMA_SENSITIVITY` price-only proxy lanes could run. Neither proxy can certify the true VWMA or option hypothesis.

## Corrected validation results at 2 bps

| Centre mode | Mode | Trades / sessions | Expectancy | PF | 95% session CI | 5 bps expectancy |
|---|---|---:|---:|---:|---:|---:|
| Uniform-volume SMA | Trend slope | 181 / 85 | -1.77 bps | 0.73 | [-3.02, 1.83] | -4.77 bps |
| Uniform-volume SMA | Trend acceleration strict | 179 / 85 | -1.69 bps | 0.74 | [-2.92, 1.84] | -4.69 bps |
| Uniform-volume SMA | Midline | 808 / 99 | -1.81 bps | 0.64 | [-1.17, 1.09] | -4.81 bps |
| Uniform-volume SMA | Bands reclaim | 181 / 86 | -2.36 bps | 0.65 | [-5.33, -1.03] | -5.36 bps |
| EMA sensitivity | Trend slope | 152 / 78 | -1.92 bps | 0.69 | [-3.12, 2.41] | -4.92 bps |
| EMA sensitivity | Trend acceleration strict | 152 / 78 | -1.92 bps | 0.69 | [-3.12, 2.41] | -4.92 bps |
| EMA sensitivity | Midline | 811 / 99 | -1.81 bps | 0.65 | [-1.45, 0.66] | -4.81 bps |
| EMA sensitivity | Bands reclaim | 151 / 80 | -4.82 bps | 0.39 | [-9.08, -4.09] | -7.82 bps |

Bands reclaim is clearly negative on this archive under both centre proxies. Trend and Midline also have negative expectancy and profit factor below one; their intervals sometimes cross zero, so the correct claim is no validated edge—not universal impossibility.

## Source versus extension separation

Published-description families:

```text
SOURCE_TREND_SLOPE
SOURCE_TREND_ACCEL_STRICT
SOURCE_MIDLINE
SOURCE_BANDS_RECLAIM
```

Custom structural extensions:

```text
EXT_ESCAPE_PULLBACK
EXT_FAILED_ESCAPE
EXT_HTF_CLUSTER_BREAK
```

These two lanes must never be pooled under one Gravity-Well performance claim.

## Integrity

- 7/7 focused source-semantic and safety tests passed;
- state persists across session boundaries;
- next-bar entry cannot cross into a new session;
- outcomes cannot cross sessions;
- TRUE_VWMA fails closed without positive volume;
- uniform-volume proxy is SMA, not EMA;
- corrected ledger contains 10,971 events;
- holdout outcomes remain sealed.

Detailed evidence:

```text
scripts/run_gravity_well_source_modes_v2.py
tests/research/test_gravity_well_source_modes_v2.py
research/gravity_well_location_participation_v1/SOURCE_MODE_CORRECTNESS_AUDIT_V2.md
research/gravity_well_location_participation_v1/frozen_source_mode_spec_v2.json
research/gravity_well_location_participation_v1/evidence/source_mode_audit_v2.json
docs/agent_reviews/gravity_well_source_mode_correctness_v2.md
```

## Next legitimate campaign

Use a volume-bearing NIFTY futures source, calculate true VWMA there, preserve the source-mode state machines, and map only qualified directions to real NIFTY CE/PE contracts. Real option validation must include immutable contract identity, delayed entry, costs and separate expiry/non-expiry analysis.
