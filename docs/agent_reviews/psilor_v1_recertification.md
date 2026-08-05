# Agent Review — PSILOR V1 Recertification

## Agent Work Contract

Recertify the strongest remaining frequent structural-edge direction without reusing the invalid Market Event Graph outcome calculation and without tuning ordinary price-shape strategies.

## Scope Guard

Allowed paths are limited to the isolated `research/psilor_v1` package, its focused runner, tests, evidence documentation and dedicated workflow. Strategy registration, TradeBuilder, ranking, risk, broker, orders, execution, feeds, dashboards and live configuration are excluded.

## Grill Me Review

The implementation does not prove that constituent participation leads the index, that the lag is directionally exploitable or that an option remains underpriced after spread and costs. The old Market Event Graph PF cannot be inherited because its runner used a precomputed `future_return_15`, advanced exits by row count across mixed intervals, selected from 11,258 graph-direction combinations and had zero option rows.

The current Drive option sample contains bid, ask, Greeks, IV, volume and OI, but lacks bid and ask quantities and is not synchronized with point-in-time event rows and futures microstructure. Returning `NOT_EVALUATED_DATA_BLOCKED` is mandatory.

## Hermes Review

The new lane:

- selects entries and exits by elapsed time rather than bar count;
- calculates P&L from recorded entry and exit prices;
- rejects mismatched precomputed outcomes;
- treats simultaneous stop and target touches conservatively as stop-first;
- rejects future and outcome fields from signal construction;
- freezes reversal and continuation event branches separately;
- maps event direction to CE or PE explicitly;
- evaluates Black-76 delta, gamma, vega and theta response;
- measures observed repricing at the executable ask;
- requires bid-side exit economics;
- fails closed on quote age, DTE, quantity, OFI and book-flow authority;
- decomposes opportunity through event, direction, contract, exit and implementability oracles.

## GSD Review

The mechanism is frozen before real-corpus outcome inspection:

```text
participation shock
→ index underreaction
→ collapse plus reversal OR persistence plus catch-up
→ executable option repricing lag
```

The initial numeric values are preregistration anchors, not promoted thresholds. No outcome-driven neighbor search is authorized. The frequency target is reported separately and cannot be achieved by relaxing the mechanism after observing results.

## QA / Safety Review

Focused validation reconstructed before publication:

```text
16 focused tests passed
Python compilation passed
deterministic readiness evidence generated
```

Covered defects and controls:

- profitable and losing known-answer trades;
- mixed one-minute/five-minute horizon detection;
- fixed 15-minute elapsed exit on five-minute data;
- precomputed outcome mismatch;
- same-bar stop/target ambiguity;
- future-field leakage;
- outcome-insensitive fingerprints;
- reversal and continuation CE/PE mapping;
- executable ask-entry/bid-exit semantics;
- repricing-already-closed rejection;
- missing quantity rejection;
- LTP spread trap;
- cost monotonicity;
- current Drive schema blocking;
- complete synthetic readiness;
- monotonic oracle ladder.

No broker API or order action is present. No production file is modified.

## Acceptance Proof

Committed contracts:

```text
research/psilor_v1/calibration.py
research/psilor_v1/contracts.py
research/psilor_v1/repricing.py
research/psilor_v1/readiness.py
research/psilor_v1/oracle.py
research/psilor_v1/spec.json
research/psilor_v1/historical_family_registry.json
research/psilor_v1/HISTORICAL_RECERTIFICATION.md
scripts/run_psilor_v1_recertification.py
tests/test_psilor_v1_recertification.py
.github/workflows/psilor_v1_recertification.yml
```

The runner emits zero candidates and the claim boundary:

```text
NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN
```

## Runtime Proof Required After Merge

None. This PR is research-only and should remain draft until an independent review accepts the evidence contracts. A real replay requires at least 30 overlapping sessions of event rows, futures bid/ask and quantity, option bid/ask and quantity, flow evidence and point-in-time instrument masters.

## What This PR Does Not Prove

It does not prove event enrichment, directional edge, contract-selection edge, executable option profit, frequency adequacy, statistical power, walk-forward stability, fresh confirmation or production readiness.

## Human Approval

The user requested direct work on the recertification candidate. No approval was given to merge, register a strategy or enable paper/live execution.

## Final Review Verdict

```text
BACKTESTER_CALIBRATION=PASS
DATA_AUTHORITY=BLOCKED
EVENT_LOCATION_ENRICHMENT=NOT_RUN
OPTION_REPRICING_LAG=NOT_RUN_ON_REAL_CORPUS
STRICT_REPLAY=NOT_RUN
INDEPENDENT_REPLAY=NOT_RUN
FINAL_VERDICT=NOT_EVALUATED_DATA_BLOCKED
NO_STRATEGY_INTEGRATION
```

mode: RESEARCH
candidate_id: PSILOR_V1
decision: NOT_EVALUATED_DATA_BLOCKED
reason: The evidence and replay contracts are repaired, but the synchronized executable microstructure corpus is incomplete.
timestamp: 2026-08-05T22:30:00+05:30
is_order_action: false
broker_api_called: false
source: agent
