# Issues 1–6 preservation check

## Scope and evidence

The prior live-run extraction at `/Users/madhuram/Downloads/Pasted text(20261002-065110).txt` describes Issues 1–6 as launch-plan option metadata, recovery identity mapping, option subscription counts, depth persistence pressure, MEG interval alignment, and duplicate session processes. The Issues 7–11 campaign prompt says to protect that work and not expand into separate repairs without a proven shared root cause. PR #936 remains excluded.

The current worktree is based on `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`, which includes the merged PR commits #949–#956 and #958. Relevant feed/token/depth configuration and the pinned observation-universe manifest are byte-identical to that baseline; see `TOKEN_UNIVERSE_COMPARISON.md`.

## Regression evidence

Command:

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_depth_ws_stability.py tests/test_depth_subscription_tokens.py tests/test_market_event_graph_live_observation_registry.py tests/test_market_event_graph_live_launch_plan.py tests/test_depth_persistence_batching.py tests/test_depth_store_accounting.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_governed_morning_orchestrator.py tests/test_feed_recovery_coordinator.py tests/test_check_option_pipeline_health.py tests/test_subscription_truth_contract.py tests/test_pulse_issues_and_feed_consistency.py`

Result: **221 passed, 1 warning in 24.16s**. The repaired-source repository regression also passed **8,608 passed, 9 skipped, 29 deselected**, with the exclusions and limits in `FINAL_VERDICT.json`.

| Finding | Current regression evidence | Remaining limit |
|---|---|---|
| 1. Launch-plan option metadata rejection | Valid and inconsistent launch-plan metadata tests; token-universe merge/budget tests | No named test exercises an empty per-symbol `tokens` row while its underlying token remains in the outer production set. This edge remains a protection gap and is not changed in this campaign. |
| 2. Reconnect proof identity mapping | Recovery-context alignment, complete/mismatched recovery proof and coordinator tests | The exact captured partial 53-underlying mapping failure has no authoritative current-session replay. |
| 3. Zero option counts under token budget | Depth token resolution, budget, stale-prune, option-health and observation-universe tests | No captured active-token comparison proves the historical per-symbol option counts recovered in live operation. |
| 4. Depth persistence pressure | Queue backlog drain/accounting, lock skip, overload rejection and depth-store accounting tests | No production-rate 2,000-tick/second soak was run in this continuation. |
| 5. Constituent interval mismatch | Bridge test proves misaligned constituent bars are rejected with diagnostics | No forward-fill was added: the captured hypothesis does not authorize synthesizing missing constituent data. Live aligned-bar parity remains unknown. |
| 6. Duplicate session processes | Governed morning orchestrator single-instance regression and process-lock coverage in repository tests | No live PID/session ownership observation was performed. |

Disposition: this is a scoped preservation regression, not proof that Issues 1–6 are live-resolved. The direct empty-row metadata case and live operational checks remain open for their owning workstream. No Issue 1–6 production files were changed in this campaign continuation.
