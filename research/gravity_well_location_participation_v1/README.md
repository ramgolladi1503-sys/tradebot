# Gravity-Well Research

## Scope

This directory now contains two explicitly separate research lanes:

1. the published-description Gravity Well modes; and
2. custom location/participation extensions inspired by the indicator.

They must not be pooled into one performance claim.

## Corrected current verdict

```text
PREVIOUS_SOURCE_FIDELITY_CLAIM_INVALID
PUBLISHED_DESCRIPTION_MODES_REBUILT
NO_PRICE_ONLY_PUBLISHED_MODE_VALIDATION_SURVIVOR
TRUE_VWMA_HYPOTHESIS_NOT_EVALUATED
REAL_OPTION_EDGE_NOT_EVALUATED
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

The earlier campaign did not test all published modes faithfully. It omitted Midline and Bands reclaim hysteresis, used an EMA proxy for a VWMA centre, and mixed custom failed-escape and HTF-cluster families into the Gravity-Well narrative.

## Published-description lane

The corrected runner implements:

```text
SOURCE_TREND_SLOPE
SOURCE_TREND_ACCEL_STRICT
SOURCE_MIDLINE
SOURCE_BANDS_RECLAIM
```

Its contracts are:

- indicator state persists across sessions;
- signal uses completed bars;
- entry is next-bar open;
- outcome is same-session only;
- exit is next opposite entry, 30 minutes or end of session;
- `TRUE_VWMA` requires positive volume and fails closed otherwise;
- SMA and EMA lanes are labelled price-only diagnostics;
- exact source-code replication is not claimed.

## Custom extension lane

The original research families are retained only as custom extensions:

```text
EXT_ESCAPE_PULLBACK
EXT_FAILED_ESCAPE
EXT_HTF_CLUSTER_BREAK
```

These are not the indicator's built-in Trend, Midline and Bands modes.

## Data authority

The multi-session archive contains:

- 493 NIFTY sessions;
- 36,849 five-minute rows;
- zero nonzero-volume NIFTY rows;
- no constituent bars;
- only mock-named option files without immutable contract identity.

Consequently, the true VWMA and real-option hypotheses remain untested. The corrected price-only mode study produced no validation survivor.

## Authoritative files

```text
RESULTS.md
SOURCE_MODE_CORRECTNESS_AUDIT_V2.md
frozen_source_mode_spec_v2.json
evidence/source_mode_audit_v2.json
scripts/run_gravity_well_source_modes_v2.py
tests/research/test_gravity_well_source_modes_v2.py
```

Historical V1 manifests and evidence are retained for traceability, not as the current source-fidelity verdict.

## Safety boundary

Research only. No strategy registration, TradeBuilder, ranking, feed runtime, dashboard, risk, approval, broker, order, execution or live-launcher path is changed. Keep the PR draft and unmerged.
