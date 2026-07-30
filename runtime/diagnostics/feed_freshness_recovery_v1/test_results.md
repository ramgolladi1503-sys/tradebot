# Test Results

Initial focused regression:

```text
pytest -q tests/test_kite_depth_ws_stability.py::test_e_partial_recovery tests/test_kite_depth_ws_stability.py::test_partial_recovery_requires_three_stable_cycles tests/test_kite_depth_ws_stability.py::test_partial_recovery_stale_critical_stays_degraded tests/test_feed_runtime_states.py::test_partial_recovery_snapshot_preserves_transport_truth
```

Result: `4 passed`.

Required deterministic suite:

```text
pytest -q tests/test_feed_subscription_generation.py tests/test_kite_depth_ws_stability.py tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_feed_reconnect_safety.py
```

Result: `144 passed`.

Requested broader selector, unmodified:

```text
pytest -q tests/ -k "feed or websocket or reconnect or recovery or freshness or subscription or runtime_state or tick_store"
```

Result: blocked during collection by unrelated `tests/test_meta_labeler.py` import. `xgboost` could not load `libomp.dylib` on this host.

Broader selector with the unrelated ML collection blocker ignored:

```text
pytest -q tests/ --ignore=tests/test_meta_labeler.py -k "feed or websocket or reconnect or recovery or freshness or subscription or runtime_state or tick_store"
```

Run 1: `883 passed, 4775 deselected, 1 warning`.

Run 2: `883 passed, 4775 deselected, 1 warning`.

Run 3: `883 passed, 4775 deselected, 1 warning`.

Static checks:

```text
python -m py_compile core/kite_depth_ws.py core/feed/runtime_store.py core/feed_truth_state.py core/feed_health_truth.py tests/test_kite_depth_ws_stability.py tests/test_feed_runtime_states.py
python -m json.tool runtime/diagnostics/feed_freshness_recovery_v1/instrumented_startup_truth.json
git diff --check
```

Result: passed.
