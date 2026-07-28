# Market Story Engine V1 — Research Contract

## Objective

Implement screenshot-style analysis as five causal layers rather than another flat indicator strategy:

1. dynamic structural map;
2. ordered market-state machine;
3. participation and opportunity quality;
4. option repricing and liquidity confirmation;
5. fail-closed CE/PE/WAIT/REJECT decision construction.

## Critical distinction

This PR certifies **implementation correctness and robustness only**. It does not certify profitable edge, historical option P&L, paper readiness, or live readiness. Economic certification requires the authoritative local underlying, constituent, and option corpus and must preserve a frozen pre-outcome specification.

## Robustness gates

- deterministic bullish and bearish scenario survival;
- failed-break, weak-breadth, weak-option, missing-quote, and crossed-market rejection;
- prefix invariance proving future rows cannot alter past decisions;
- timestamp-shift control blocking stale or misaligned option confirmation;
- mirrored long/short symmetry;
- small-noise stability of at least 90%;
- duplicate and out-of-order timestamp failure;
- redundant-indicator non-influence;
- two-run semantic determinism;
- independent audit with hash mutation detection.

## Safety

- research only;
- no strategy registry activation;
- no broker API calls;
- no order actions;
- no risk, execution, feed, dashboard, credentials, or live configuration changes;
- `allowed_for_live_execution=false` in every decision and certification artifact.
