# PR-FEED-19 — Callback Thin-Wiring Refactor

## Scope

This PR adds a thin pure adapter layer between websocket callback facts and the PR-FEED-18 lifecycle shell.

The adapter centralizes deterministic mapping for:

- callback runtime facts into lifecycle state
- connected callback outcome
- subscribe callback outcome
- error callback outcome
- close callback outcome
- runtime-state and runtime-error mapping
- lifecycle evidence payloads with explicit non-action safety fields

## Files

- `core/feed/ws_callback_thin_wiring.py`
- `tests/test_pr_feed_19_ws_callback_thin_wiring.py`

## Design

The adapter is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no callback mutation
- no order or execution behavior

Callers pass callback facts explicitly. The adapter returns a `WsCallbackLifecycleResult` containing state, transition, next state, evidence, runtime-state text, runtime-error text, and the snapshot connection flag.

## Safety

This PR does not yet rewire `core/kite_depth_ws.py` callback bodies.

That is intentional. The adapter creates the tested thin-wiring seam first so a later controlled callback diff can consume it with minimal behavior drift.

## Test command

```bash
python -m pytest tests/test_pr_feed_19_ws_callback_thin_wiring.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No dashboard/UI work
- No live callback behavior change
- No subscription behavior change
- No reconnect behavior change
- No runtime file-write change
