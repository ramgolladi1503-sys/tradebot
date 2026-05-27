# PR-FEED-11 — Extract Runtime Snapshot Builder

## Scope

This PR adds a pure runtime snapshot builder module for feed runtime evidence payloads.

The module centralizes deterministic construction for:

- scalar normalization for epochs, floats, runtime state, and error text
- feed runtime state-machine classification
- runtime-store payload shape
- latest-runtime payload shape
- optional effective websocket/feed-ok derivation hooks
- optional stamping hook

## Files

- `core/feed/runtime_snapshot_builder.py`
- `tests/test_pr_feed_11_runtime_snapshot_builder.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no runtime state mutation
- no order or execution behavior

Callers pass all runtime observations explicitly. The module returns payload dictionaries only.

## Safety

This PR does not rewire `core/kite_depth_ws.py`.

That is intentional. The existing websocket file contains sensitive runtime write behavior. This PR creates the deterministic snapshot-building surface first so future feed-refactor PRs can consume it through a controlled diff with regression coverage.

## Test command

```bash
python -m pytest tests/test_pr_feed_11_runtime_snapshot_builder.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No live websocket behavior change
- No runtime file write changes
- No overlay publication changes
- No token resolution work
