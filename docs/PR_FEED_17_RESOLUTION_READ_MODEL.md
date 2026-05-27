# PR-FEED-17 — Extract Resolution Read Model

## Scope

This PR adds a pure read-model module for feed subscription selection evidence.

The module centralizes deterministic construction for:

- symbol and exchange normalization
- expiry-key normalization
- ATM strike inference
- option identifier normalization and ranking
- selected strike and two-sided strike evidence
- explicit option failure reasons
- per-symbol resolution rows
- combined global read-model maps

## Files

- `core/feed/token_resolution_read_model.py`
- `tests/test_pr_feed_17_resolution_read_model.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no runtime state mutation
- no order behavior

Callers pass resolved observations explicitly. The module returns immutable dataclass read models and payload dictionaries only.

## Safety

This PR does not rewire `core/kite_depth_ws.py`.

That is intentional. The existing websocket file contains sensitive feed selection and subscription behavior. This PR creates the deterministic resolution read-model surface first so future feed-refactor PRs can consume it through a controlled diff with regression coverage.

## Test command

```bash
python -m pytest tests/test_pr_feed_17_resolution_read_model.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No live websocket behavior change
- No subscription behavior changes
- No instrument-cache reads
- No feed evidence file write changes
