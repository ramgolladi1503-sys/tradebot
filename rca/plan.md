# RCA: Live Feed Stability

## 1. Branch/base inspected
```bash
git branch --show-current
git diff --stat
```
Inspects master/main branch with zero active modifications at the start of analysis.

## 2. Files inspected
- `core/feed_runtime.py`
- `core/feed_recovery_runtime.py`
- `core/feed_recovery_coordinator.py`
- `core/feed_health_truth.py`
- `core/kite_depth_ws.py`
- `core/engine_phase2_adapter.py`
- `core/orchestrator.py`
- `core/runtime_health.py`
- `core/feed_debug.py`
- `core/feed_execution_truth.py`
- `strategies/trade_builder.py`

## 3. Feed lifecycle map
1. **Connection/Disconnection**: `kite_depth_ws.py` manages websocket state. 1006 errors cause retry unless "main loop terminated" occurs, flagging `ws1006_process_restart_required`.
2. **Snapshot Emission**: `_write_feed_runtime_snapshot` emits ages and token stats to `feed_runtime_latest.json`. Missing `last_db_tick_age_sec` or option ages fall back to snapshot payload processing.
3. **Canonical Health**: `feed_runtime.py` processes raw snapshot variables into a `CanonicalFeedTruthState`.
4. **Health Aggregation & Zombies**: `runtime_health.py` and `feed_zombie_state.py` aggregate state. The zombie rule requires `no_subscriptions AND ws_down AND stale_feed`, which is dangerously permissive and creates false healthy states when partially functioning.
5. **Phase 2 & Orchestrator Gate**: `engine_phase2_adapter.py` drops candidates if `feed_ok` is false in `feed_runtime_latest.json`, but `feed_ok` computation relies on missing or skewed age logic.

## 4. File coverage table
| Module | Coverage | Status |
|---|---|---|
| `core/feed_runtime.py` | Full line by line | RCA finding found |
| `core/feed_recovery_runtime.py` | Full line by line | RCA finding found |
| `core/feed_recovery_coordinator.py`| Full line by line | Clean |
| `core/feed_health_truth.py` | Full line by line | RCA finding found |
| `core/kite_depth_ws.py` | Full line by line | RCA finding found |
| `core/feed_zombie_state.py` | Full line by line | RCA finding found |
| `core/runtime_health.py` | Full line by line | Clean |
| `core/engine_phase2_adapter.py` | Full line by line | RCA finding found |

## 5. RCA findings table
| Finding | File Path | Function/Class Name | Current Behavior | Failure Mode | Runtime Symptom | Evidence | Proposed Modification | Safety Impact | Test Required | Expected Improvement |
|---|---|---|---|---|---|---|---|---|---|---|
| **1. Permissive Zombie State** | `core/feed_zombie_state.py` | `classify_feed_zombie_state` | Evaluates `is_zombie = live_required and no_subscriptions and ws_down and stale_feed`. All components must be False. | If feed goes stale and WS is disconnected, but `no_subscriptions` resolves to false (because stale state has sub counts recorded), the feed avoids Zombie state. | Feed claims healthy or recoverable when it is permanently stuck. | Code uses strict `AND` condition preventing state transition on partial failure. | Modify zombie condition to `is_zombie = live_required and ws_down and stale_feed` (remove `no_subscriptions` dependency or use OR). | None (strictly restricts execution further during broken states). | `test_zombie_state_or_condition` | Fewer false healthy claims during silent disconnections. |
| **2. Exception masks `feed_ok` value** | `core/engine_phase2_adapter.py` | `build_candidates_phase2` | Reads `feed_runtime_latest.json` but falls back to `feed_ok = False` if any exception occurs. | If `feed_ok` logic inside json fails or json is temporarily unreadable, it fails closed silently blocking the pipeline. | Execution stalls completely and candidates are rejected safely, but incorrectly reports feed broken. | `except Exception: feed_ok = False` catches all. | Ensure JSON parse explicitly checks for empty payloads or log parsing errors accurately. | Safe, makes debugging clear. | `test_engine_phase2_feed_ok_read` | Removes false fatal/stale claims. |
| **3. Stale Strikes Reset on Flapping Feed** | `core/kite_depth_ws.py` | `_run_db_tick_watchdog_cycle` | `_STALE_STRIKES = 0` triggers whenever single valid tick arrives. | Prolonged degradation with intermittent single ticks resets the strike counter to zero, never triggering restart thresholds. | Feed gets stuck in degraded state forever bouncing between 0 and 1 stale strikes. | `_STALE_STRIKES = 0` unconditional reset inside db tick check loop. | Add cumulative logic: decrease strikes on good tick instead of full reset, or use time-based window. | None (speeds up recovery trigger). | `test_stale_strikes_cumulative_threshold` | Quicker recovery when feed is flapping instead of dead. |

## 6. Dominant root cause
`kite_depth_ws.py`'s `stale_strikes` logic coupled with permissive zombie and false-positive pipeline gates leads to inconsistent state where the system hangs on recoverable errors or randomly rejects executing safe trades because it mixes up canonical truths. A flapping feed resets the strike counter preventing full reconnects.

## 7. Secondary contributors
- `engine_phase2_adapter` dropping candidates silently due to unlogged exceptions when parsing the payload.
- `feed_zombie_state` requiring all 3 failure conditions to be met simultaneously.

## 8. Proposed patch plan split into small commits
1. Fix `engine_phase2_adapter.py` to properly log and parse `feed_ok` instead of silently failing.
2. Fix `feed_zombie_state.py` logic to accurately declare zombies without requiring a complete 3-way fault intersection.
3. Tune `stale_strikes` windowing in `kite_depth_ws.py` to ensure process restart triggers accurately on flapping feeds (cumulative rather than reset-to-zero).

## 9. Tests to add
- `test_engine_phase2_feed_ok_read`: Validates fallback behavior when json is unreadable vs missing key.
- `test_zombie_state_or_condition`: Validates that a disconnected stale feed with stale subscriptions is marked zombie.
- `test_stale_strikes_cumulative_threshold`: Validates flapping feed hits restart threshold.

## 10. Live-soak validation plan
- Deploy patched branch to SIM environment.
- Force-inject 1006 connection drops and intermittent ticks.
- Monitor `stale_strikes` counter incrementing steadily over 5 hour window.
- Ensure Phase 2 candidate drops correlate perfectly with actual feed drops.

## 11. Acceptance criteria for 5 healthy hours in a 6-hour window
- Feed status must strictly drop to recovering/reconnecting.
- Flapping feeds must hit restart within 3 strikes.
- Must not spend > 15 cumulative minutes in Zombie/Unknown.

## 12. Risks if the fix is wrong
- Increased process restart thrashing if strikes are too sensitive.
- False positive executions if Phase 2 gate is completely unblocked.
