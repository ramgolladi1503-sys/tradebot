# PR-FEED-11 Runtime Snapshot Builder Agent Review

mode: REVIEW
candidate_id: pr_feed_11_runtime_snapshot_builder
decision: review_ready
reason: runtime_snapshot_builder_tests_docs
timestamp: 2026-05-27T18:38:00Z
source: pr_feed_11_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-11 only.

The PR adds pure, deterministic runtime snapshot builder helpers for feed runtime evidence payloads. It must not wire live websocket runtime behavior, write files, publish overlays, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure runtime snapshot builder helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Runtime file writes.
- Overlay publication changes.
- Token resolution changes.
- Live websocket callback rewiring.
- Hidden config or time calls inside the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live runtime snapshot writes?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can this PR publish feed overlays or write files?

Answer: No. The helper module returns dictionaries only. File writes and overlay publication remain outside this PR.

Question: Can this PR hide runtime timing behind wall-clock calls?

Answer: No. Callers must pass `ts_epoch` and all age fields explicitly. The helper does not call time APIs.

## Hermes Review

The public helper contract is intentionally narrow:

- `FeedRuntimeSnapshotInputs`
- `coerce_epoch(...)`
- `safe_float(...)`
- `safe_int(...)`
- `normalized_runtime_state(...)`
- `trimmed_error(...)`
- `derive_runtime_state_machine(...)`
- `build_feed_runtime_store_payload(...)`
- `build_feed_runtime_latest_payload(...)`

These helpers are pure value transforms. Callers must pass runtime observations explicitly.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No logging side effects.
- No runtime mutation.
- Invalid optional values normalize to deterministic defaults.

## QA / Safety Review

Focused test coverage includes:

- epoch coercion
- safe float normalization
- runtime state normalization
- error trimming
- market-closed state-machine classification
- websocket-disconnected state-machine classification
- awaiting-first-tick state-machine classification
- live tick state-machine classification
- stale/no-message state-machine classification
- runtime-store payload shape
- latest-runtime payload shape
- derivation hook behavior
- stamping hook behavior
- missing optional value defaults

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_11_runtime_snapshot_builder.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- existing runtime-store payload keys remain backward-compatible
- existing latest-runtime payload keys remain backward-compatible
- feed-ok/effective websocket derivation remains unchanged
- runtime stamping remains unchanged
- runtime file writes remain atomic
- unhealthy overlay publication remains unchanged
- no broker/order side effects are introduced

## What This PR Does Not Prove

This PR does not prove live websocket recovery, runtime file-write liveness, broker connectivity, subscription correctness, execution quality, or profitability. It only proves a deterministic runtime snapshot payload-building surface for future feed refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `PR-FEED-17 — Extract Token Resolution Read Model` only from the latest merged main commit.
