# QA Coverage Gaps — 2026-06-10
**Branch:** qa/antigravity-elite-test-pack-20260610  
**Source:** antigravity-repo-audit-20260610.md + elite-test-matrix-20260610.md  
**Rule:** Gaps are ranked by the actual damage they can cause in production, not by how easy they are to test.

---

## How to read this document

Each gap describes:
- **What is missing** — the specific test behavior that does not exist
- **Why it matters** — the production failure scenario that would remain hidden without the test
- **Severity** — P0 / P1 / P2
- **Proposed test** — the exact test file name from the matrix
- **Blocked path** — what safety invariant is currently unproven

---

## P0 Gaps — Existential safety; these are tests that must exist before any live trading

---

### GAP-01 — `allow_stale_quotes` never produces a live-executable decision
**Severity:** P0  
**Missing test:** `test_feed_freshness_gate_stale_allow_quotes_never_executable.py`  
**Production failure scenario:** A config change sets `ALLOW_STALE_QUOTES=true` (e.g., for off-hours testing) and is not reverted before market open. The feed freshness gate with `allow_stale_quotes=True` permits advisory candidates but must never set `allowed_for_live_execution=True`. Without this test, that boundary is asserted only implicitly by the gate state machine test, not by a combined output assertion.  
**Blocked safety invariant:** `allowed_for_live_execution=False` where applicable  
**What currently exists:** `test_feed_freshness_gate.py` covers gate state transitions but does not explicitly assert `allowed_for_live_execution` with `allow_stale_quotes=True` in market-open context.

---

### GAP-02 — `RECOVERED_FALLBACK` source always produces `execution_eligible=False`
**Severity:** P0  
**Missing test:** `test_quote_truth_recovered_fallback_never_executable.py`  
**Production failure scenario:** A recovered fallback quote (source = `RECOVERED_FALLBACK`, which is in `FALLBACK_QUOTE_SOURCES`) passes into the ranking pipeline after a feed reconnect. If `classify_quote_truth()` returns `execution_eligible=True` for this source (possible if the `reasons` list is empty due to a condition short-circuit), the candidate would be marked as execution-grade with fallback data.  
**Blocked safety invariant:** `broker_api_called=false` and `allowed_for_live_execution=false` for fallback quotes  
**What currently exists:** `test_edge41_fallback_execution_firewall.py` covers the firewall decision but not the `classify_quote_truth` output for each member of `FALLBACK_QUOTE_SOURCES`.

---

### GAP-03 — `LIVE_TRADING_ENABLED=false` blocks execution even with valid approval
**Severity:** P0  
**Missing test:** `test_execution_guard_live_env_disabled_always_blocks.py` and `test_must_have_valid_approval_live_env_disabled_blocks_approved_intent.py`  
**Production failure scenario:** An operator sets `MANUAL_APPROVAL=True` and creates a valid APPROVED approval for a trade intent. If `LIVE_TRADING_ENABLED=false` is checked at the approval store level only (inside `must_have_valid_approval`), but the `ExecutionGuard.evaluate()` path is called without the approval check (e.g., in SIM-emulated-as-LIVE path), the env var check is bypassed. The gap is that `ExecutionGuard.evaluate()` itself does not call `must_have_valid_approval()` — it is the caller's responsibility. This is a structural safety assumption, not a tested guarantee.  
**Blocked safety invariant:** `allowed_for_live_execution=false unless explicitly scoped and human-approved`  
**What currently exists:** `test_live_enablement_gate.py` covers the enablement gate but not the combined path from `ExecutionGuard.evaluate()` → `must_have_valid_approval()` → env var check in sequence.

---

### GAP-04 — Concurrent approval consumption is exactly-once
**Severity:** P0  
**Missing test:** `test_approval_store_concurrent_consume_exactly_one_wins.py`  
**Production failure scenario:** Under high-frequency paper or live conditions, two concurrent execution cycles for the same order hash both call `consume_valid_approval()`. SQLite WAL with `BEGIN IMMEDIATE` should serialize this, but the timeout fallback (`approval_store_locked` after 5 retries) could cause both threads to fail (not one success + one used-rejection), which is the correct behavior but is unproven under thread contention.  
**Blocked safety invariant:** `is_order_action=false` (an accidental double-consume would cause a duplicate order)  
**What currently exists:** `test_order_approval_store.py` covers the state machine but not concurrent access from multiple threads.

---

### GAP-05 — Expired approval cannot be consumed even if not yet marked EXPIRED in DB
**Severity:** P0  
**Missing test:** `test_approval_store_expired_row_cannot_be_consumed.py`  
**Production failure scenario:** A TOCTOU window: an approval's `expires_at_epoch` is `now - 0.5` but the row status is still `APPROVED` (not yet updated to `EXPIRED`). `consume_valid_approval()` checks `now_epoch > expires` and transitions the row to EXPIRED, then returns `approval_expired`. This is the correct behavior. But if a connection timeout occurs (SQLite lock for > 1s on the `BEGIN IMMEDIATE` attempt), the row may remain `APPROVED` and a subsequent caller could consume it after wall-clock expiry. The test must prove that `now_epoch > expires_at_epoch` always produces rejection, even if the row status is still `APPROVED`.  
**Blocked safety invariant:** `is_order_action=false`  
**What currently exists:** No explicit test for this TOCTOU window.

---

### GAP-06 — SIM mode `ExecutionGuard` never leaks `mode=LIVE`
**Severity:** P0  
**Missing test:** `test_execution_guard_destruction_sim_mode_never_leaks_live.py`  
**Production failure scenario:** A bug in `_requested_mode()` that reads `execution_mode` from a nested dict path returns `"LIVE"` when the market_data context has a nested `market_context.execution_mode = "LIVE"` field but the outer `mode` parameter is `"SIM"`. The destructor test would catch this by randomizing context inputs.  
**Blocked safety invariant:** SIM/PAPER/LIVE boundary must be strict  
**What currently exists:** `test_execution_guard.py`-equivalent coverage exists but does not do 1,000-call randomized input destruction testing.

---

### GAP-07 — Ranking never places a `SUPPRESSED_BY_DOWNGRADE` candidate at rank 1 when clean candidates exist
**Severity:** P0  
**Missing test:** `test_ranking_no_rank1_suppressed_when_clean_candidates_exist.py`  
**Production failure scenario:** The top opportunity displayed to the operator is a suppressed/fallback candidate instead of a clean lower-scoring candidate. The operator acts on the displayed rank-1 candidate without realizing it is suppressed. Under the current `_sort_key` implementation, this should not happen (ELIGIBILITY_PRIORITY puts SCORE_ELIGIBLE above SUPPRESSED_BY_DOWNGRADE). But it is not explicitly regression-tested.  
**Blocked safety invariant:** ranking must use real opportunity truth, not emitted-row order  
**What currently exists:** `test_candidate_ranking.py` tests ELIGIBILITY_PRIORITY but not a direct "clean candidate beats suppressed candidate at rank 1" assertion with a mixed input.

---

### GAP-08 — All `FEED_RISK_TOKENS` produce suppression in ranking
**Severity:** P0  
**Missing test:** `test_scoring_feed_risk_tokens_all_produce_suppression.py`  
**Production failure scenario:** A new FEED_RISK_TOKEN is added to `FEED_RISK_TOKENS` list but the suppression code in `rank_candidates` only checks a hardcoded subset. A feed-risk candidate would pass ranking without suppression. The parameterized test ensures the list is complete.  
**Blocked safety invariant:** fallback/recovered quote must never become executable  
**What currently exists:** `test_candidate_ranking.py` tests suppression for specific tokens but not for every member of `FEED_RISK_TOKENS`.

---

### GAP-09 — Candidate pool dedup preserves highest-capability candidate
**Severity:** P0  
**Missing test:** `test_candidate_pool_dedup_prefers_higher_capability.py`  
**Production failure scenario:** When a BLOCKED candidate and a VALIDATED candidate share the same dedup key, the current first-seen-wins policy means that if the BLOCKED candidate is processed first (e.g., from an earlier pipeline stage), the VALIDATED candidate is silently dropped. This reduces the executable candidate count without any visibility or error.  
**Blocked safety invariant:** candidate pool must preserve advisory/near-executable/executable distinction  
**What currently exists:** `test_candidate_pool.py` tests deduplication but does not assert priority ordering for status resolution.

---

### GAP-10 — `no_trade_engine` fires `NO_TRADE_FALLBACK_DATA` on `fallback_used=True` with no source string
**Severity:** P0  
**Missing test:** `test_no_trade_fallback_used_true_with_no_source_fires.py`  
**Production failure scenario:** A `StrategyContext` is built from a dict that sets `fallback_used=True` but leaves `quote_source=None`. The OR condition `if ctx.fallback_used or "fallback" in str(ctx.quote_source or "").lower()` should still fire, producing `NO_TRADE_FALLBACK_DATA`. Without this test, a refactor that removes `ctx.fallback_used` from the check (leaving only the string check) would silently break fallback detection for programmatically-constructed contexts.  
**Blocked safety invariant:** fallback/recovered quote must never become executable  
**What currently exists:** `test_no_trade_engine.py` tests fallback detection but may rely on `quote_source` containing "fallback" in the string.

---

### GAP-11 — `NO_TRADE_STALE_FEED` fires when `option_ltp_age_sec=None`
**Severity:** P0  
**Missing test:** `test_no_trade_stale_feed_fires_on_none_age.py`  
**Production failure scenario:** An option that has never received a tick has `option_ltp_age_sec=None`. The no-trade engine checks `if age is None or age > MAX_OPTION_LTP_AGE_SEC`. The `None` branch must produce severity=1.0 (maximum stale severity). Without this test, a refactor that changes `is None` to `== 0` would silently allow the none-age case through.  
**Blocked safety invariant:** stale feed must not produce executable candidates  
**What currently exists:** `test_no_trade_engine.py` likely covers stale ages > threshold but may not cover the `None` age case explicitly.

---

### GAP-12 — WS `on_connect` resubscribes all option tokens
**Severity:** P0  
**Missing test:** `test_depth_ws_on_connect_resubscribes_all_option_tokens.py`  
**Production failure scenario:** After a WS disconnect, the `on_connect` callback is invoked but only resubscribes index tokens (NIFTY, BANKNIFTY), leaving all option strike tokens dark. The feed appears healthy (index ticks arrive) but all option quotes are stale. This scenario cannot be detected by feed health checks that only verify index-level data freshness.  
**Blocked safety invariant:** stale feed must not produce executable candidates (because the stale options would pass a coarse freshness check)  
**What currently exists:** `test_on_connect_forces_subscribe.py` verifies `subscribe()` is called but does not capture and assert the specific tokens passed.

---

### GAP-13 — Option tick with stale `ts_epoch` and absent `quote_ts` is classified as stale
**Severity:** P0  
**Missing test:** `test_option_tick_stale_ts_epoch_not_fresh.py`  
**Production failure scenario:** A tick payload has `ts_epoch = now - 30` (server-set, 30 seconds ago) but `quote_ts = None`. The quote age truth resolver picks `ts_epoch` as the best timestamp and computes `effective_age_sec = 30`. But if the field resolution order in `classify_quote_age_truth` checks `quote_ts` first and falls through to a default of None (because quote_ts is absent), `effective_age_sec` becomes None. None is then treated as fresh (no explicit staleness check for None age in some code paths). The result: a 30-second-old option tick passes freshness checks.  
**Blocked safety invariant:** stale feed must not produce executable candidates  
**What currently exists:** `test_quote_age_truth.py` covers age truth but may not cover this specific field-resolution failure mode.

---

### GAP-14 — Execution grade firewall rejects candidates with `execution_eligible=False`
**Severity:** P0  
**Missing test:** `test_execution_grade_firewall_rejects_fallback_quote.py`  
**Production failure scenario:** The execution grade firewall is the last line of defense before an order is sent. If the firewall reads `quote_truth.execution_eligible` from the wrong field (e.g., `rank_eligible` instead of `execution_eligible`), a fallback candidate that is rank-eligible but not execution-eligible would pass through.  
**Blocked safety invariant:** `broker_api_called=false` for non-execution-eligible candidates  
**What currently exists:** `test_execution_grade_firewall.py` covers the firewall but field-level assertion coverage is unclear.

---

### GAP-15 — Dashboard does not import execution modules
**Severity:** P0  
**Missing test:** `test_dashboard_does_not_import_execution_modules.py`  
**Production failure scenario:** A dashboard developer adds an import of `core.approval_store` to display approval status inline. This creates a direct dependency from the UI layer to the execution layer, violating the runtime artifact contract. Any test that only checks runtime behavior would miss this import-level coupling.  
**Blocked safety invariant:** Dashboard must read-only from runtime snapshots; never access execution engines directly  
**What currently exists:** `test_dashboard_reads_snapshot_only.py` is a runtime mock test, not a static import analysis.

---

## P1 Gaps — High risk; these tests should exist before paper trading

---

### GAP-16 — `DEGRADED` state produces `BLOCKED` (not `ADVISORY_ONLY`) when `fail_on_degraded=True`
**Severity:** P1  
**Missing test:** `test_feed_freshness_gate_degraded_blocked_not_advisory.py`  
**Why it matters:** Operators may observe `ADVISORY_ONLY` output and assume the gate is allowing advisory candidates safely. If the gate is incorrectly returning `ADVISORY_ONLY` instead of `BLOCKED` for a degraded feed with `fail_on_degraded=True`, advisory candidates could be promoted to executable by downstream code that treats `ADVISORY_ONLY` as a weaker block.

---

### GAP-17 — Zombie feed (connected, no ticks > 30s) eventually produces `BLOCKED`
**Severity:** P1  
**Missing test:** `test_feed_freshness_gate_zombie_feed_blocked.py`  
**Why it matters:** A zombie feed is indistinguishable from a healthy feed at the connection level. Without per-token age checking, the feed health reports `ok=True` while option ticks are missing. The freshness gate must catch this via the `ltp.age_sec` check.

---

### GAP-18 — Recovery warmup gate blocks candidates during warmup window
**Severity:** P1  
**Missing test:** `test_feed_recovery_warmup_gate_blocks_candidates.py`  
**Why it matters:** After a feed reconnect, there is a warmup period during which indicator values are being re-computed. Candidates generated during this period are based on incomplete market data. The warmup gate blocks emission until the window passes, but this is not regression-tested.

---

### GAP-19 — Grace period does not mask stale tokens after window expires
**Severity:** P1  
**Missing test:** `test_depth_ws_grace_period_does_not_mask_stale_after_window.py`  
**Why it matters:** A 60-second grace period after session start protects against false pruning on first tick. But after 61 seconds, tokens that have not ticked must be pruned. If the grace period calculation uses a global mutable start epoch that is not reset on reconnect, the grace period never expires on session 2+.

---

### GAP-20 — Never-received option tick produces hard blocker
**Severity:** P1  
**Missing test:** `test_option_tick_never_received_blocks_hard.py`  
**Why it matters:** A token that was subscribed but never received a tick (e.g., subscription failed silently) has age=None. This must produce a hard blocker (not a warning), preventing the token's candidate from entering ranking.

---

### GAP-21 — Candidates from stale context produce advisory-only, not validated
**Severity:** P1  
**Missing test:** `test_candidate_generator_stale_context_produces_advisory_only.py`  
**Why it matters:** Candidate generators receive market context from the orchestrator. If the context contains stale data (`allow_stale_quotes=True`), generated candidates must inherit that blocker. This is not tested at the generator level.

---

### GAP-22 — Candidates during market-closed are advisory-only
**Severity:** P1  
**Missing test:** `test_candidate_generator_market_closed_produces_advisory.py`  
**Why it matters:** Off-hours candidates (generated for pre-market analysis) must never be `VALIDATED_CANDIDATE`. All generators must respect `market_open=False` in context.

---

### GAP-23 — Pool lifecycle snapshots have `read_only=True` and `is_order_action=False`
**Severity:** P1  
**Missing test:** `test_candidate_pool_lifecycle_snapshot_accuracy.py`  
**Why it matters:** Lifecycle snapshots are persisted to disk and used for evidence replay. If a snapshot has `is_order_action=True` (even by accident), it could be interpreted as a trade action by a replay tool.

---

### GAP-24 — Ranking is idempotent across two calls with the same input
**Severity:** P1  
**Missing test:** `test_ranking_idempotent_across_calls.py`  
**Why it matters:** The orchestrator may call `rank_candidates` multiple times in a cycle (e.g., after a regime update). Non-idempotent ranking would produce different rank orderings for the same opportunity data, making evidence unreliable.

---

### GAP-25 — Survival gates take priority over confidence in `ExecutionGuard`
**Severity:** P1  
**Missing test:** `test_execution_guard_survival_gate_takes_priority_over_confidence.py`  
**Why it matters:** The execution guard evaluates survival gates before confidence. If a code change reorders these checks, a high-confidence trade could bypass a survival gate breach (e.g., max daily loss exceeded). This priority must be regression-tested.

---

### GAP-26 — Armed approval window enforced independently of TTL
**Severity:** P1  
**Missing test:** `test_approval_armed_window_enforced_independently_of_ttl.py`  
**Why it matters:** For LIVE mode, the armed window (60s) is a final confirmation gate after the approval TTL (600s). If the armed window expiry check is skipped (e.g., `require_armed=False` is passed by default), the 60-second execution confirmation window provides no protection.

---

### GAP-27 — Orchestrator properly resets candidates after reconnect
**Severity:** P1  
**Missing test:** `test_orchestrator_reconnect_clears_stale_ranked_candidates.py`  
**Why it matters:** After a WS reconnect, options pricing is stale until fresh ticks arrive. If the orchestrator carries over ranked candidates from the pre-reconnect cycle, those stale candidates would be displayed as current top opportunities to the operator.

---

### GAP-28 — End-to-end stale feed → no-trade evidence
**Severity:** P1  
**Missing test:** `test_orchestrator_e2e_stale_feed_to_no_trade_evidence.py`  
**Why it matters:** The no-trade evidence chain has multiple hops: feed state → freshness gate → hold gate → no-trade engine → evidence writer. Without an integration test spanning all hops, a break at any intermediate link could silently suppress the no-trade evidence while still emitting candidates.

---

### GAP-29 — Artifact freshness guard fires within 60s of stale snapshot
**Severity:** P1  
**Missing test:** `test_artifact_freshness_guard_fires_within_60s.py`  
**Why it matters:** If the dashboard is showing a 90-second-old snapshot without a visible staleness alert, operators may act on stale opportunity data.

---

### GAP-30 — Runtime snapshot is non-empty after write
**Severity:** P1  
**Missing test:** `test_runtime_snapshot_not_empty_after_market_open.py`  
**Why it matters:** An empty snapshot file (zero bytes) would cause the dashboard to either crash or show blank data without a clear error. The artifact non-empty contract must be explicitly proven.

---

### GAP-31 — `quote_truth`: None LTP + None status classification is safe
**Severity:** P1  
**Missing test:** `test_quote_truth_none_ltp_none_status_is_safe.py`  
**Why it matters:** The silent `OK` return for `current_ltp=None` + `existing_status=None` is an intentional legacy compatibility path documented in the code. But without a test, this path is not monitored. A future refactor that changes the condition to `return "NO_LIVE_OPTION_FEED"` would be a breaking change with no failing test to alert the developer.

---

### GAP-32 — Fallback → live source transition restores `execution_eligible=True`
**Severity:** P1  
**Missing test:** `test_quote_truth_live_transition_from_fallback_requires_live_tick.py`  
**Why it matters:** After feed recovery, the quote truth for a symbol must transition from `source_trust="fallback"` to `source_trust="trusted_live"`. If this transition is sticky (requires process restart), candidates from recovered symbols would remain blocked indefinitely even with fresh data.

---

## P2 Gaps — Medium risk; these tests improve observability and maintainability

---

### GAP-33 — Off-hours WS refresh does not trigger when market is closed
**Severity:** P2  
**Missing test:** `test_depth_ws_no_offhours_refresh.py`  
**Why it matters:** `_maybe_refresh_stale_option_subscription_universe` should no-op when the market is closed. Off-hours refresh attempts could generate unnecessary broker API calls or log noise that masks real issues.

---

### GAP-34 — Candidate normalizer produces stable `strategy_id`
**Severity:** P2  
**Missing test:** `test_candidate_normalizer_stable_strategy_id.py`  
**Why it matters:** Non-deterministic `strategy_id` generation would cause the same candidate to create duplicate entries in the pool across cycles, inflating candidate counts and breaking deduplication.

---

### GAP-35 — Chop threshold is a module constant, not config
**Severity:** P2  
**Missing test:** `test_no_trade_chop_threshold_is_module_constant_not_config.py`  
**Why it matters:** If `CHOP_THRESHOLD` were accidentally moved to a config value, it could be tuned by a non-expert operator, weakening the no-trade protection in choppy regimes. The test documents and enforces the intentional design choice.

---

### GAP-36 — Reconnect destruction: no zombie subscriptions after 10 cycles
**Severity:** P2  
**Missing test:** `test_depth_ws_destruction_reconnect_cycles_no_zombie_subscriptions.py`  
**Why it matters:** Repeated connect/disconnect cycles could accumulate tokens in the subscription set if `on_close` cleanup is incomplete. Zombie subscriptions consume quota and can interfere with subscription budget enforcement.

---

## Gap Prioritization Summary

| Gap | Severity | Proposed test | Days to write |
|-----|----------|--------------|--------------|
| GAP-01 | P0 | test_feed_freshness_gate_stale_allow_quotes_never_executable.py | 0.5 |
| GAP-02 | P0 | test_quote_truth_recovered_fallback_never_executable.py | 0.5 |
| GAP-03 | P0 | test_execution_guard_live_env_disabled_always_blocks.py | 0.5 |
| GAP-04 | P0 | test_approval_store_concurrent_consume_exactly_one_wins.py | 1.0 |
| GAP-05 | P0 | test_approval_store_expired_row_cannot_be_consumed.py | 0.5 |
| GAP-06 | P0 | test_execution_guard_destruction_sim_mode_never_leaks_live.py | 0.5 |
| GAP-07 | P0 | test_ranking_no_rank1_suppressed_when_clean_candidates_exist.py | 0.5 |
| GAP-08 | P0 | test_scoring_feed_risk_tokens_all_produce_suppression.py | 0.5 |
| GAP-09 | P0 | test_candidate_pool_dedup_prefers_higher_capability.py | 0.5 |
| GAP-10 | P0 | test_no_trade_fallback_used_true_with_no_source_fires.py | 0.5 |
| GAP-11 | P0 | test_no_trade_stale_feed_fires_on_none_age.py | 0.5 |
| GAP-12 | P0 | test_depth_ws_on_connect_resubscribes_all_option_tokens.py | 1.0 |
| GAP-13 | P0 | test_option_tick_stale_ts_epoch_not_fresh.py | 0.5 |
| GAP-14 | P0 | test_execution_grade_firewall_rejects_fallback_quote.py | 0.5 |
| GAP-15 | P0 | test_dashboard_does_not_import_execution_modules.py | 0.5 |
| GAP-16 | P1 | test_feed_freshness_gate_degraded_blocked_not_advisory.py | 0.5 |
| GAP-17 | P1 | test_feed_freshness_gate_zombie_feed_blocked.py | 1.0 |
| GAP-18 | P1 | test_feed_recovery_warmup_gate_blocks_candidates.py | 1.0 |
| GAP-19 | P1 | test_depth_ws_grace_period_does_not_mask_stale_after_window.py | 0.5 |
| GAP-20 | P1 | test_option_tick_never_received_blocks_hard.py | 0.5 |
| GAP-21 | P1 | test_candidate_generator_stale_context_produces_advisory_only.py | 1.0 |
| GAP-22 | P1 | test_candidate_generator_market_closed_produces_advisory.py | 0.5 |
| GAP-23 | P1 | test_candidate_pool_lifecycle_snapshot_accuracy.py | 0.5 |
| GAP-24 | P1 | test_ranking_idempotent_across_calls.py | 0.5 |
| GAP-25 | P1 | test_execution_guard_survival_gate_takes_priority_over_confidence.py | 0.5 |
| GAP-26 | P1 | test_approval_armed_window_enforced_independently_of_ttl.py | 0.5 |
| GAP-27 | P1 | test_orchestrator_reconnect_clears_stale_ranked_candidates.py | 1.0 |
| GAP-28 | P1 | test_orchestrator_e2e_stale_feed_to_no_trade_evidence.py | 1.5 |
| GAP-29 | P1 | test_artifact_freshness_guard_fires_within_60s.py | 0.5 |
| GAP-30 | P1 | test_runtime_snapshot_not_empty_after_market_open.py | 0.5 |
| GAP-31 | P1 | test_quote_truth_none_ltp_none_status_is_safe.py | 0.5 |
| GAP-32 | P1 | test_quote_truth_live_transition_from_fallback_requires_live_tick.py | 0.5 |
| GAP-33 | P2 | test_depth_ws_no_offhours_refresh.py | 0.5 |
| GAP-34 | P2 | test_candidate_normalizer_stable_strategy_id.py | 0.5 |
| GAP-35 | P2 | test_no_trade_chop_threshold_is_module_constant_not_config.py | 0.25 |
| GAP-36 | P2 | test_depth_ws_destruction_reconnect_cycles_no_zombie_subscriptions.py | 1.0 |

**Total P0 gaps:** 15  
**Total P1 gaps:** 17  
**Total P2 gaps:** 4  
**Estimated total implementation effort:** ~20 engineering days (P0 only: ~8 days)

---

## Acceptance Criteria for Gap Closure

A gap is closed when:
1. The exact proposed test file exists in `tests/`.
2. `pytest tests/<test_file> -v` exits 0 with at least 1 real assertion (not just `assert True`).
3. The test does NOT use `monkeypatch` to replace the actual safety decision with a mocked result.
4. A human reviewer confirms the test would fail if the production behavior were reverted to the unsafe state.

---

## Files Not Touched

The following files were read for audit purposes only. None were modified:

- `core/feed_freshness_gate.py`
- `core/depth_subscription_engine.py`
- `core/candidate_ranking.py`
- `core/candidate_pool.py`
- `core/trade_permission.py`
- `core/quote_truth.py`
- `core/execution_guard.py`
- `core/no_trade_engine.py`
- `core/approval_store.py`
- `core/candidate_scoring.py`
- All existing test files

No production code was modified. No test files were modified. No config was changed. No strategy thresholds were changed. No broker APIs were called. No live mode was touched.
