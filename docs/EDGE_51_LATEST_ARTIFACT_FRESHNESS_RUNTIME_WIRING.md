# EDGE-51 — Latest Artifact Freshness Runtime Wiring

## Purpose

Wire the EDGE-50 latest artifact freshness guard into the runtime snapshot read layer without changing the legacy `read_snapshot()` contract.

This PR gives future dashboard/runtime readers a safe helper that returns both the snapshot and freshness evidence, so old `latest` files are not silently treated as current truth.

## Implementation

Updated `core/runtime_snapshot_store.py` with:

- `read_snapshot_with_freshness(...)`
- `_snapshot_freshness_payload(...)`
- `_snapshot_freshness_input(...)`
- `_parse_snapshot_epoch(...)`

## Behavior

`read_snapshot_with_freshness(path, ...)` returns:

- `snapshot`: raw snapshot envelope when readable, otherwise `None`
- `freshness`: EDGE-50 freshness decision payload
- `fresh`: boolean freshness flag
- `blockers`: freshness reasons when not fresh
- explicit non-action fields:
  - `is_order_action=false`
  - `broker_api_called=false`
  - `live_order_action=false`
  - `broker_order_action=false`

## Compatibility

Existing `read_snapshot(path)` remains unchanged.

## Scope Guard

Out of scope:

- no dashboard migration
- no runtime decision blocking
- no artifact writer changes
- no strategy changes
- no broker integration changes
- no live runtime behavior changes
- no order placement or order intent

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge51_runtime_snapshot_freshness_wiring.py
```

The tests prove:

- fresh snapshot is marked fresh
- stale snapshot is marked non-fresh
- absent file fails closed
- invalid JSON fails closed
- missing generated timestamp fails closed
- legacy `read_snapshot()` remains unchanged
- non-object JSON still raises from the legacy reader
