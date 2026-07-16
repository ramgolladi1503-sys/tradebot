# Feed Reconnect Resource Soak Audit

## Agent Work Contract
- `source_agent`: Codex
- `action`: GENERATE_PATCH, GENERATE_TESTS, UPDATE_DOCS
- `title`: Feed reconnect resource soak proof repair and evidence closure
- `scope`: Offline reconnect soak harness correctness, websocket recovery lifecycle proof, negative-control descriptor cleanup proof, and audit-grade documentation
- `requested_paths`:
  - `core/kite_depth_ws.py`
  - `scripts/run_feed_reconnect_resource_soak.py`
  - `tests/test_feed_reconnect_resource_soak.py`
  - `tests/test_kite_depth_ws_stability.py`
  - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
- `allowed_paths`:
  - `core/kite_depth_ws.py`
  - `scripts/run_feed_reconnect_resource_soak.py`
  - `tests/test_feed_reconnect_resource_soak.py`
  - `tests/test_kite_depth_ws_stability.py`
  - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
- `forbidden_paths`:
  - `core/trade_store.py`
  - `strategies/`
  - `config/`
  - `credentials.py`
  - `.env`
  - `runtime/live*`
  - `logs/broker*`
  - Antigravity worktree files
- `expected_tests`:
  - `pytest -q tests/test_feed_reconnect_resource_soak.py`
  - targeted negative-profile reruns via `scripts/run_feed_reconnect_resource_soak.py`
  - explicit storage regression suite
- `acceptance_proof`: exact JSON evidence for guarded, positive, owner-failure, and negative cleanup profiles plus clean git diff and pushed branch

## Scope Guard
- Worktree: `/Users/madhuram/.codex/worktrees/tradebot/feed-reconnect-resource-soak-recovery`
- Branch: `codex/feed-reconnect-resource-soak-recovery`
- Base commit: `4235c012874757707a14322e3d5457fe0cb1896a`
- Checkpoint commit used for scale proof: `30b13a55489ed744a257d2c58d18448eddbbd02b`
- Scope freeze honored:
  - no Antigravity worktree access
  - no broker/auth/config edits
  - no strategy threshold edits
  - no `core/trade_store.py` edits
  - no rerun of the 1000-cycle soak after checkpoint
- Later code after checkpoint is limited to negative-control cleanup reporting in `scripts/run_feed_reconnect_resource_soak.py` and its tests

## Objective
Prove whether repeated websocket disconnect, reconnect, resubscription, recovery, and shutdown cycles keep process resources bounded under offline synthetic stress, while also proving that the detector catches intentional descriptor leaks and that cleanup returns the process to the post-warmup baseline.

## Starting Baseline
- Existing fresh worktree already contained checkpoint commit `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- `git show --stat --oneline 30b13a55` confirmed the checkpoint touched only:
  - `core/kite_depth_ws.py`
  - `scripts/run_feed_reconnect_resource_soak.py`
  - `tests/test_feed_reconnect_resource_soak.py`
  - `tests/test_kite_depth_ws_stability.py`
- `git status --short --untracked-files=all` was clean before the final evidence pass.

## Rejected Prior Evidence
- Initial non-1000-cycle claims were insufficient.
- Retired websocket generations previously remained reachable at `44`, which invalidated lifecycle proof.
- Dummy ticker and factory retention previously masked generation cleanup.
- Unique-path-only FD counting was invalid because process-wide FD bounds must include all descriptors.
- SQLite descriptors were previously excluded from the leak detector, which invalidated the stated objective.
- Global safeguard bypass without explicit profile scoping was unsafe.
- FD threshold widening was rejected because it weakened proof instead of fixing root cause.
- Assertion weakening from `100/100` to `80/100` and from `1000/1000` to `800/1000` was rejected.
- Retired-generation weakening from exact `0` to `<= 5` was rejected.
- Hard-coded subscription metrics were rejected because they did not prove replay truth.
- Invalid RSS parser fallbacks were rejected.
- Dirty Antigravity handoff output was rejected because it mixed branches and stale claims.

## Architecture Decision
- Keep the production lifecycle fix in `core/kite_depth_ws.py`.
- Keep scale-proof evidence tied to checkpoint `30b13a55`.
- Add only a reporting-boundary correction after the checkpoint so negative controls persist both:
  - the intentional leak snapshot in `final`
  - the explicit cleanup snapshot in `post_cleanup_final`
- Do not change positive reconnect semantics after the checkpoint.

## Implementation Changes
- `core/kite_depth_ws.py`
  - `_resubscribe_full()` now computes `option_verification_required` with `any(int(count or 0) > 0 for count in _LAST_OPTION_COUNTS_BY_SYMBOL.values())`.
  - This fixes a real production lifecycle bug: a non-empty zero-count option map previously forced recovery to stay uncleared even though no option verification was actually required.
- `scripts/run_feed_reconnect_resource_soak.py`
  - separates runtime cleanup helpers from result assembly
  - preserves pre-cleanup leak evidence in `final`
  - records explicit `post_cleanup_final` for `negative_fd_leak` and `sqlite_same_path_multi_descriptor_negative`
- `tests/test_feed_reconnect_resource_soak.py`
  - locks the cleanup-reporting contract for both negative profiles
- `tests/test_kite_depth_ws_stability.py`
  - proves exact recovery-clear behavior, including the zero-count option-map case

## High-Risk Path Review
- High-risk path touched on this branch: `core/kite_depth_ws.py`
- Review outcome:
  - no broker/order path changes
  - no risk-gate weakening
  - no feed-freshness weakening
  - change is constrained to reconnect lifecycle clearing logic after exact subscription replay
  - zero-count option maps no longer hold `_RECOVERY_IN_PROGRESS` open indefinitely
- Evidence:
  - `core/kite_depth_ws.py:5955-5974`
  - `tests/test_kite_depth_ws_stability.py:252-278`

## Guarded Policy Evidence
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile reconnect_guarded --cycles 10 --sample-every 10 --seed 42 --output-json /tmp/codex_reconnect_guarded.json`
- Result:
  - verdict: `RECONNECT_GUARDED_POLICY_PASS`
  - `disconnect_count=3`
  - `verified_successful_reconnect_count=2`
  - `generation_transition_count=2`
  - `hard_failures=0`
  - `first_mismatch=guarded_policy_blocked_at_cycle_2: recovery blocked by original safety limits`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
- Interpretation:
  - Original safety policy still blocks excess recovery attempts when synthetic overrides are not enabled.

## Unbounded 100-Cycle Evidence
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile reconnect_unbounded_resource_stress --cycles 100 --sample-every 10 --seed 42 --output-json /tmp/codex_reconnect_unbounded_100.json`
- Result:
  - verdict: `RECONNECT_RESOURCE_100_CYCLE_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `hard_failures=0`
  - `first_mismatch=null`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`
  - `reconnect_lock_held=false`

## Unbounded 1000-Cycle Evidence
- This 1000-cycle proof applies to checkpoint `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- The later change affects negative-control cleanup reporting only.
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile reconnect_unbounded_resource_stress --cycles 1000 --sample-every 100 --seed 42 --output-json /tmp/codex_reconnect_unbounded_1000.json`
- Wrapper timing:
  - start: `2026-07-16T11:50:39.919820+05:30`
  - end: `2026-07-16T12:09:10.252856+05:30`
  - duration: `1110.3322761058807` seconds
  - exit code: `0`
- Result:
  - verdict: `RECONNECT_RESOURCE_1000_CYCLE_PASS`
  - `disconnect_count=1000`
  - `reconnect_attempt_count=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `same_generation_reused_count=1557`
  - `generation_creation_failures=0`
  - `terminal_failure_count=0`
  - `hard_failures=0`
  - `first_mismatch=null`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `watchdog_thread_count 1 -> 1 -> 0`
  - `python_thread_count 2 -> 3 -> 1`
  - `retired_websocket_generations_reachable=0`
  - `reconnect_lock_held=false`
  - `missing_token_count=150` in final shutdown snapshot because the ticker is intentionally stopped before the final sample
  - `unexpected_token_count=0`
  - `duplicate_subscription_count=0`
  - `final.rss_slope_bytes_per_sample=62259.2`

## Owner-Failure Evidence
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile owner_failure --cycles 100 --sample-every 10 --seed 42 --reconnect-failure-every 5 --output-json /tmp/codex_owner_failure_100.json`
- Result:
  - verdict: `RECONNECT_OWNER_FAILURE_RECOVERY_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `owner_failures_injected_count=19`
  - `owner_failures_observed_count=19`
  - `owner_recoveries_completed_count=19`
  - `hard_failures=0`
  - `fd_count 7 -> 7 -> 7`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `reconnect_lock_held=false`

## Negative FD Detector And Cleanup Evidence
- Post-checkpoint reporting correction added explicit cleanup proof.
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile negative_fd_leak --cycles 20 --sample-every 5 --seed 42 --output-json /tmp/codex_negative_fd_leak_20.json`
- Result:
  - verdict: `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `cycle_samples=[0,5,10,15,19]`
  - `post_warmup_baseline.fd_count=7`
  - `final.fd_count=27`
  - `post_cleanup_final.fd_count=7`
  - `post_warmup_baseline.sqlite_fd_count=0`
  - `final.sqlite_fd_count=0`
  - `post_cleanup_final.sqlite_fd_count=0`
- Interpretation:
  - The detector still sees the synthetic FD leak before cleanup.
  - Cleanup demonstrably returns the process to the warm baseline afterward.

## SQLite Same-Path Descriptor And Cleanup Evidence
- Post-checkpoint reporting correction added explicit cleanup proof.
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile sqlite_same_path_multi_descriptor_negative --cycles 20 --sample-every 5 --seed 42 --output-json /tmp/codex_sqlite_same_path_negative.json`
- Result:
  - verdict: `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `cycle_samples=[0,5,10,15,19]`
  - `post_warmup_baseline.fd_count=7`
  - `final.fd_count=47`
  - `post_cleanup_final.fd_count=7`
  - `post_warmup_baseline.sqlite_fd_count=0`
  - `final.sqlite_fd_count=40`
  - `post_cleanup_final.sqlite_fd_count=0`
- Interpretation:
  - The detector counts same-path descriptors correctly.
  - Cleanup closes all same-path SQLite descriptors and returns to baseline.

## Subscription Reconciliation Evidence
- Positive profiles end each sampled cycle with exact replay equality:
  - `subscription_tokens_match_exactly=true`
  - `missing_token_count=0`
  - `unexpected_token_count=0`
  - `duplicate_subscription_count=0`
- Final shutdown snapshots intentionally show no active requested tokens because the ticker has been stopped before `final`.

## Watchdog Lifecycle Evidence
- 100-cycle and 1000-cycle positive profiles do not leak watchdog threads.
- 1000-cycle proof recorded:
  - `post_warmup_baseline.watchdog_thread_count=1`
  - `high_water.watchdog_thread_count=1`
  - `final.watchdog_thread_count=0`

## Recovery-Clear Contract Evidence
- Production fix:
  - `core/kite_depth_ws.py` clears recovery after exact subscription replay only when positive-count option verification is actually required.
- Direct tests:
  - `test_on_connect_does_not_clear_recovery_before_option_verification`
  - `test_on_connect_clears_recovery_only_after_exact_subscription_replay_without_option_verification`
  - `test_on_connect_zero_count_option_map_does_not_block_recovery_clear`
  - `test_on_connect_replay_exception_keeps_recovery_uncleared_and_marks_subscribe_failed`
  - `test_on_connect_incomplete_subscription_replay_keeps_recovery_uncleared`
  - `test_option_verification_success_clears_recovery_exactly_once`
  - `test_option_verification_failure_keeps_recovery_fail_closed`

## Grill Me Review
- Prior evidence overclaimed and mixed real proof with weakened criteria.
- Current branch is acceptable only because the relaxed criteria were rejected and the later patch stayed reporting-only for negative controls.
- Remaining concern:
  - offline synthetic soak still does not prove live broker/runtime behavior.

## Hermes Review
- Design choice is correct:
  - production lifecycle logic lives in `core/kite_depth_ws.py`
  - evidence-only cleanup reporting lives in the soak harness
  - scale proof remains tied to the exact checkpoint that was run
- No broader refactor was needed.

## GSD Review
- Execution stayed within the allowed file set.
- No unrelated runtime or storage logic was modified.
- Validation covered:
  - harness contract tests
  - storage regressions
  - explicit negative reruns
  - prior short-suite result

## QA / Safety Review
- No broker APIs were called.
- No order, execution, or risk paths changed.
- No auth or environment files changed.
- Synthetic stress overrides remain scoped to soak profiles only.
- The negative-control cleanup patch does not affect positive reconnect semantics.

## Test Evidence
- Short-suite result from checkpointed implementation state:
  - command:
    - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -vv tests/test_feed_reconnect_resource_soak.py tests/test_kite_depth_ws_stability.py tests/test_feed_recovery_coordinator.py tests/test_kite_depth_restart.py -k "not test_reconnect_stress_1000_has_bounded_resources and not test_control_1000_has_no_cycle_correlated_fd_growth" --tb=long`
  - result:
    - `145 passed, 2 deselected in 370.38s`
- Reporting-contract rerun after the final patch:
  - command:
    - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -q tests/test_feed_reconnect_resource_soak.py -k "synthetic_fd_leak or sqlite_negative_cleanup or metrics_schema_is_complete or profile_contract_is_explicit or verdict_engine_negative_leak_rejected" --tb=long`
  - result:
    - `6 passed, 17 deselected in 89.38s`

## Storage Evidence
- Enumerated storage files:
  - `tests/test_analytics_schema_store.py`
  - `tests/test_decision_store.py`
  - `tests/test_depth_store_rate_limit.py`
  - `tests/test_feed_debug_runtime_store.py`
  - `tests/test_feed_runtime_store_lifecycle.py`
  - `tests/test_order_approval_store.py`
  - `tests/test_order_store_persistence.py`
  - `tests/test_position_state_store.py`
  - `tests/test_storage_subsystem.py`
  - `tests/test_tick_store.py`
  - `tests/test_tick_store_nonblocking_decision_path.py`
  - `tests/test_trade_store_depth_snapshot_resilience.py`
  - `tests/test_trade_store_identity.py`
  - `tests/test_ws_tick_ingestion_updates_tick_store.py`
  - `tests/core/test_market_snapshot_store.py`
  - `tests/core/test_runtime_snapshot_store.py`
  - `tests/core/test_tick_store_db_truth.py`
  - `tests/analytics/test_store.py`
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -q tests/test_analytics_schema_store.py tests/test_decision_store.py tests/test_depth_store_rate_limit.py tests/test_feed_debug_runtime_store.py tests/test_feed_runtime_store_lifecycle.py tests/test_order_approval_store.py tests/test_order_store_persistence.py tests/test_position_state_store.py tests/test_storage_subsystem.py tests/test_tick_store.py tests/test_tick_store_nonblocking_decision_path.py tests/test_trade_store_depth_snapshot_resilience.py tests/test_trade_store_identity.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/core/test_market_snapshot_store.py tests/core/test_runtime_snapshot_store.py tests/core/test_tick_store_db_truth.py tests/analytics/test_store.py --tb=long`
- Result:
  - `66 passed in 2.60s`

## Acceptance Proof
- Positive reconnect proofs are bounded and exact.
- Guarded policy remains enforced when overrides are not enabled.
- Owner-failure recovery releases ownership/lock state and later recovers.
- Negative controls now prove both detection and post-cleanup restoration.
- Storage regression suite passed.
- Scope stayed inside the approved file list.

## Runtime Proof Required After Merge
- Live or paper websocket sessions under real Kite auth.
- Real market-open option-universe transitions.
- Real network churn with broker-side websocket behavior.
- Long-duration runtime beyond the synthetic 1000-cycle harness.

## What This PR Does Not Prove
- It does not prove live trading readiness.
- It does not prove paper trading readiness.
- It does not prove broker correctness.
- It does not prove unbounded real-runtime stability.
- It does not prove profitability or strategy quality.

## Human Approval
- Human approval is still required for any merge or live/paper rollout.
- No PR was opened in this Codex pass.
- No merge was performed in this Codex pass.

## Limitations
- The 1000-cycle JSON does not include explicit `pre_shutdown_snapshot` or `post_shutdown_snapshot`; absent fields must remain `UNMEASURED` rather than inferred.
- The final positive snapshot is a post-stop snapshot, so token counts there reflect shutdown, not in-flight replay.
- Synthetic overrides are necessary for stress profiles and must not be conflated with guarded production behavior.

## Final Verdict
- Offline reconnect resource soak proof is established for the exact claimed checkpoint and the later evidence gap is closed for negative-control cleanup reporting.
