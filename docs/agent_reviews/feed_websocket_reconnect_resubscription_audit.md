# Feed Websocket Reconnect and Resubscription Audit

## Date
2026-07-13

## Summary
This audit reviews the implementation of websocket feed robustness mechanisms, explicitly covering disconnects, reconnect concurrency, resubscription, and tick freshness validation.

## Modifications Made
1. **Concurrency and Duplicate Prevention**: Validated that `_RESTART_LOCK` correctly gates `restart_depth_ws`, preventing duplicate concurrent reconnect workers. 
2. **Tick Freshness on Reconnect**: Enforced strict freshness tracking by explicitly resetting `_LAST_WS_TICK_EPOCH` to `0.0` inside `on_connect`. This guarantees that immediately after a socket connection succeeds, the system correctly classifies the data as stale (`is_market_data_fresh() == False`) until actual provider ticks arrive.
3. **Out-of-Order Tick Discarding**: Addressed a critical flaw where `_normalized_tick_epoch` would blindly cap older tick timestamps to the most recent high-water mark and allow the outdated payload to overwrite current best prices. Ticks with an `exchange_timestamp` older than the last seen epoch for the token are now strictly discarded before state mutation.
4. **Resubscription Safety**: Validated that `safe_subscribe_full_mode` respects socket state, queuing the requests when the socket is unready and skipping duplicate redundant subscriptions when tokens are already cached.
5. **Null Socket Guard**: Verified that outer boundaries and queue handlers properly handle `ws=None` states without raising `AttributeError`.

## Test Suite Coverage
Introduced deterministic unit tests (Tests A-G) in `tests/test_kite_depth_ws_stability.py` that trigger and assert on:
- Null websocket scenarios
- Concurrent restart triggers
- Safe token resubscription boundaries
- Immediate post-reconnect stale status
- Out-of-order `on_ticks` payload rejection

All core tests (including new edge case tests) passed deterministically. 

## Verdict
- `WEBSOCKET_DISCONNECT_HANDLED`
- `WEBSOCKET_RECONNECT_SINGLE_OWNER_PASS`
- `WEBSOCKET_RESUBSCRIBE_COMPLETE`
- `TICK_FRESHNESS_STRICT_VALIDATED`
- `OUT_OF_ORDER_TICK_DROPPED`
