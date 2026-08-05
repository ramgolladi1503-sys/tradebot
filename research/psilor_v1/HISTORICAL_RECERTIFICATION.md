# PSILOR V1 Historical Recertification

## Status

```text
CERTIFIED_FREQUENT_STRUCTURAL_EDGE_FOUND=NO
MARKET_EVENT_GRAPH_PERFORMANCE_CLAIM=INVALID
DORL_V3_EXECUTABLE_EDGE=NOT_EVALUATED
PSILOR_V1_RESEARCH_ELIGIBLE=YES
PSILOR_V1_EDGE_PROVEN=NO
CURRENT_DATA_VERDICT=NOT_EVALUATED_DATA_BLOCKED
PRODUCTION_INTEGRATION=FORBIDDEN
```

## Why this lane exists

The previous Market Event Graph result looked like the strongest frequent candidate, but the retained reproduction runner does not calculate trade return from its recorded causal entry and exit. It assigns `future_return_15` from the signal row and separately records entry and exit prices.

The same runner advances the exit by 15 rows. The frozen dataset contains one-minute and five-minute regimes, so 15 rows can represent approximately 15 minutes or approximately 75 minutes. The resulting partitions are not economically comparable.

The original graph discovery also:

- tested 11,258 graph-direction combinations;
- used holdout performance during final acceptance;
- contained zero option rows.

The event locations may be worth retesting. The old profitability claim is not.

## Frozen mechanism

`PSILOR_V1` means:

```text
broad constituent participation shock
→ index/futures underreaction
→ participation either collapses or persists
→ index reversal or catch-up confirms
→ executable CE/PE ask remains under-repriced versus Black-76 Greek response
→ next causal ask entry and bid exit
```

The mechanism has two preregistered branches:

1. `REVERSAL`: trade opposite the initial participation shock after collapse and index reversal.
2. `CONTINUATION`: trade with the initial shock after persistence and index catch-up.

All windows are elapsed-time contracts. Bar-count horizons are not allowed.

## Implemented integrity gates

The branch implements and tests:

- entry-to-exit PnL reconciliation;
- mixed one-minute/five-minute horizon detection;
- rejection of mismatched precomputed outcomes;
- conservative stop-first handling when stop and target are both touched;
- future/outcome-field rejection from signal rows;
- deterministic signal fingerprints that ignore outcome mutation;
- event direction to CE/PE mapping;
- Black-76 delta, gamma, vega and theta repricing;
- executable ask-side lag eligibility;
- bid-side exit economics;
- quote age, DTE, quantity, OFI and book-flow blockers;
- fail-closed data readiness;
- oracle decomposition from market opportunity through implementability.

## Current Drive evidence

A current Upstox option tick file was inspected with this observed schema:

```text
ts
instrument_key
ltp
bid_price
ask_price
delta
theta
gamma
vega
iv
volume
oi
```

This is useful option quote and Greek evidence, but it is insufficient for a PSILOR replay because it lacks:

- bid quantity;
- ask quantity;
- synchronised futures microstructure;
- point-in-time participation event rows.

A current instrument master exists in Drive, but the qualifying replay still needs at least 30 overlapping sessions across all four authorities.

## Current verdict

```text
BACKTESTER_CALIBRATION=PASS
DATA_AUTHORITY=BLOCKED
EVENT_LOCATION_ENRICHMENT=NOT_RUN
MATCHED_CONTROL_DIFFERENCE=NOT_RUN
OPTION_REPRICING_LAG=NOT_RUN_ON_REAL_CORPUS
STRICT_REPLAY=NOT_RUN
INDEPENDENT_REPLAY=NOT_RUN
FREQUENCY_GATE=NOT_MEASURED
STATISTICAL_POWER=NOT_MEASURED
FINAL_VERDICT=NOT_EVALUATED_DATA_BLOCKED
```

No candidate is emitted. No strategy registration, ranking, risk, broker or execution path is changed.
