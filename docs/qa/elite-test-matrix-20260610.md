# Elite Test Matrix — 2026-06-10
**Branch:** qa/antigravity-elite-test-pack-20260610  
**Source:** antigravity-repo-audit-20260610.md  
**Rule:** No fake tests. Every test must prove real behavior — not just object shape, import success, or key existence.

---

## How to read this matrix

| Column | Meaning |
|--------|---------|
| **Test file** | Exact proposed file name to create in `tests/` |
| **Suite type** | smoke / unit / integration / regression / destruction / contract / replay |
| **Proves** | The precise behavioral assertion that makes this test non-fake |
| **Priority** | P0 = existential safety / P1 = high risk / P2 = medium risk |

---

## Area 1 — Feed Health / Freshness / Feed Runtime

### 1.1 — `tests/test_feed_freshness_gate_stale_allow_quotes_never_executable.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
Given `freshness_status = {ok: True, state: "OK", market_open: True, allow_stale_quotes: True, ltp: {ok: True}, depth: {ok: True}}`, calling `assess_feed_freshness_gate()` must return a decision where:
- `gate_state == "ADVISORY_ONLY"` (not `FRESH`, not `BLOCKED`)
- `allowed_for_live_execution == False`
- `allowed_for_paper_execution == False`
- `"ALLOW_STALE_QUOTES_ACTIVE"` in `blockers`

This test must NOT pass if `allowed_for_paper_execution=True` leaks through.

---

### 1.2 — `tests/test_feed_freshness_gate_degraded_blocked_not_advisory.py`
**Suite type:** unit  
**Priority:** P0  
**Proves:**  
Given `freshness_status = {state: "DEGRADED", ok: False, market_open: True}` and `fail_on_degraded=True`, the decision must have:
- `gate_state == "BLOCKED"` (not `"ADVISORY_ONLY"`)
- `allowed_for_live_execution == False`
- `"FEED_STATE_DEGRADED"` in `blockers`

Parameterize across all `BLOCKING_STATES` to prove each one independently produces `BLOCKED`.

---

### 1.3 — `tests/test_feed_freshness_gate_zombie_feed_blocked.py`
**Suite type:** integration  
**Priority:** P1  
**Proves:**  
A feed state where `ws_connected=True`, `ok=True`, but LTP age exceeds `MAX_OPTION_QUOTE_AGE_SEC` (age = 45s) must produce `allowed_for_live_execution=False` with `"STALE_OPTION_LTP"` in blockers. The test must construct a real freshness payload with `ltp.ok=False` and `ltp.age_sec=45.0` and assert the gate output, not just check that the key exists.

---

### 1.4 — `tests/test_feed_recovery_warmup_gate_blocks_candidates.py`
**Suite type:** regression  
**Priority:** P1  
**Proves:**  
After a simulated reconnect, `FeedRecoveryWarmupGate.is_warmed_up()` returns `False` during the warmup window. Candidates generated during this window must be blocked by the warmup gate. This test must call the gate with `warmup_elapsed_sec < warmup_required_sec` and assert the gate decision is `HOLD`, then call it after the window and assert `FRESH`.

---

## Area 2 — Depth WebSocket Reconnect / Resubscribe

### 2.1 — `tests/test_depth_ws_on_connect_resubscribes_all_option_tokens.py`
**Suite type:** integration  
**Priority:** P0  
**Proves:**  
After WS `on_close` is called, the subsequent `on_connect` callback must invoke `subscribe(tokens)` with the full set of option tokens (not just index tokens). The test must:
1. Set up a mock WS with a known token set.
2. Trigger `on_close`.
3. Trigger `on_connect`.
4. Assert that the captured `subscribe` call argument contains all option tokens from the pre-close subscription.

This test FAILS if the `subscribe` call is never made or only contains index tokens.

---

### 2.2 — `tests/test_depth_ws_grace_period_does_not_mask_stale_after_window.py`
**Suite type:** regression  
**Priority:** P1  
**Proves:**  
`_prune_stale_option_subscription_tokens` with a grace period of 60s must NOT protect stale tokens after 61+ seconds of session start. The test must:
1. Set `_DEPTH_WS_START_EPOCH` to `now - 70`.
2. Set option token ages to 20s (> max_age of 12s default).
3. Call `_prune_stale_option_subscription_tokens` with `consecutive=1`.
4. Assert that the stale tokens are in the pruned set.

This test FAILS if it uses the global module default `_DEPTH_WS_START_EPOCH = 0` because that would make `now - start = now`, not a controlled value.

---

### 2.3 — `tests/test_depth_ws_destruction_reconnect_cycles_no_zombie_subscriptions.py`
**Suite type:** destruction  
**Priority:** P1  
**Proves:**  
After 10 simulated connect/disconnect cycles with the same token set, the final active subscription list must equal the original desired token set. No extra tokens should accumulate. Assert `len(final_tokens) == len(initial_desired_tokens)` and `set(final_tokens) == set(initial_desired_tokens)`.

---

### 2.4 — `tests/test_depth_ws_no_offhours_refresh.py`
**Suite type:** unit  
**Priority:** P2  
**Proves:**  
`_maybe_refresh_stale_option_subscription_universe` must return `(False, {"reason": "market_closed"})` when `is_market_open_ist()` returns `False`. The test must mock the market-open check and assert the tuple, not just check the return type.

---

## Area 3 — Option Tick Verification

### 3.1 — `tests/test_option_tick_stale_ts_epoch_not_fresh.py`
**Suite type:** unit  
**Priority:** P0  
**Proves:**  
A candidate payload with `ts_epoch = now - 30` (30 seconds ago) and `quote_ts = None` must produce `classify_quote_age_truth()` with `effective_age_sec >= 30` and `reason_code != "ok"`. Then `classify_quote_truth()` on the same payload must produce `execution_eligible=False`.

This test must NOT accept `execution_eligible=True` as a pass.

---

### 3.2 — `tests/test_exact_option_token_freshness_gate_hard_blocks_old_token.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
`exact_option_token_freshness_gate` with a token that has `age_sec > MAX_OPTION_QUOTE_AGE_SEC` (e.g., 15.0s when max is 8.0s) must produce a decision with:
- `allowed_for_live_execution == False`
- `allowed_for_paper_execution == False`
- Reason code that maps to `"STALE_OPTION_LTP"` or equivalent blocker

The test must use real freshness payload injection, not a mock of the gate's final return value.

---

### 3.3 — `tests/test_option_tick_never_received_blocks_hard.py`
**Suite type:** unit  
**Priority:** P0  
**Proves:**  
A token that has never received a tick (age=None, epoch=None) must produce a hard blocker — not a warning — in the quote truth decision. `classify_quote_age_truth` with `ts_epoch=None` and all timestamp fields None must return `effective_age_sec=None` and `reason_code` that is NOT `"ok"`.

---

## Area 4 — Quote Truth and Fallback Handling

### 4.1 — `tests/test_quote_truth_recovered_fallback_never_executable.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
A payload with `quote_source="RECOVERED_FALLBACK"` must produce `classify_quote_truth()` output where:
- `execution_eligible == False`
- `rank_eligible == False`
- `source_trust == "fallback"`
- `"fallback_quote_source"` in `reasons`

The test must fail if `execution_eligible=True` is returned for any `FALLBACK_QUOTE_SOURCES` member.

Parameterize across all `FALLBACK_QUOTE_SOURCES` values.

---

### 4.2 — `tests/test_quote_truth_none_ltp_none_status_is_safe.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
A payload with `current_ltp=None`, `quote_validation_status=None`, `quote_source=None`, and `ts_epoch=None` is classified as having `truth_ok=False` (not silently `True`). This documents and asserts the intentional fallback behavior. If the codebase intends this to be `truth_ok=True`, the test must have a comment explaining the safety rationale.

---

### 4.3 — `tests/test_quote_truth_live_transition_from_fallback_requires_live_tick.py`
**Suite type:** regression  
**Priority:** P1  
**Proves:**  
After classifying a payload as `source_trust="fallback"`, updating the same payload with `quote_source="LIVE"` and a fresh timestamp must produce `source_trust="trusted_live"` and `execution_eligible=True`. This proves the transition is not sticky and does not require a process restart.

---

### 4.4 — `tests/test_execution_grade_firewall_rejects_fallback_quote.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
`execution_grade_firewall` must reject (block) a candidate where `quote_truth.execution_eligible=False` regardless of score, regime, or capital availability. The test must show the firewall decision and assert `blocked=True` and `reason` contains a fallback/stale reference.

---

## Area 5 — Candidate Generation

### 5.1 — `tests/test_candidate_generator_stale_context_produces_advisory_only.py`
**Suite type:** integration  
**Priority:** P1  
**Proves:**  
Calling a candidate generator (e.g., `breakout_candidate_generator`) with market context where `allow_stale_quotes=True` must produce candidates that have `ALLOW_STALE_QUOTES_ACTIVE` in their `blockers` field or `status == "BLOCKED_CANDIDATE"`. No candidate from a stale-quote context may have `status == "VALIDATED_CANDIDATE"`.

---

### 5.2 — `tests/test_candidate_generator_market_closed_produces_advisory.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
All strategy generators, when called with `market_open=False` in context, must produce candidates with `advisory_only=True` or `status` in `{"ADVISORY_CANDIDATE", "BLOCKED_CANDIDATE"}`. None may produce `status == "VALIDATED_CANDIDATE"` during market-closed context.

---

### 5.3 — `tests/test_candidate_normalizer_stable_strategy_id.py`
**Suite type:** unit  
**Priority:** P2  
**Proves:**  
Calling `normalize_candidate()` twice with identical input dicts must produce the same `strategy_id`. The test must use at least 3 different input shapes and assert equality across 5 calls per shape.

---

## Area 6 — Candidate Pool

### 6.1 — `tests/test_candidate_pool_dedup_prefers_higher_capability.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
Given two candidates with the same dedup key `(symbol, direction, movement_type, strategy_id)` but different statuses (`VALIDATED_CANDIDATE` and `BLOCKED_CANDIDATE`), the pool must retain the `VALIDATED_CANDIDATE`. The test must assert `pool.candidates[0].status == "VALIDATED_CANDIDATE"` regardless of input order.

**Note:** This test exposes whether the current implementation (first-seen wins) is safe. If it is not safe, the test documents the risk for human review.

---

### 6.2 — `tests/test_candidate_pool_lifecycle_snapshot_accuracy.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
`build_candidate_lifecycle_snapshots()` with a mixed pool (VALIDATED + BLOCKED) must produce lifecycle snapshots where:
- VALIDATED candidates have `lifecycle_state` in `{"RANKED", "SCORED", "CLASSIFIED", "RESOLVED"}`
- BLOCKED candidates have `lifecycle_state == "BLOCKED"` or `"NO_TRADE"`
- `read_only == True` and `is_order_action == False` on every snapshot

---

### 6.3 — `tests/test_candidate_pool_executable_count_not_inflated_by_soft_reject.py`
**Suite type:** regression  
**Priority:** P1  
**Proves:**  
A pool where all candidates have `executable_eligible=True` on the raw `StrategyCandidate` object but are all soft-rejected at the scorer must have `pool.summary().executable_eligible_count > 0` at the pool level (correct — pool reflects raw candidate state) but `ranking_report.executable_count == 0` (correct — ranking reflects post-score state). The test asserts both counts and their difference.

---

## Area 7 — Scoring and Ranking

### 7.1 — `tests/test_ranking_fallback_candidate_demoted_below_clean_low_score.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
Given two candidates:
- Candidate A: `final_score=0.95`, `safety_flags=["fallback_data"]`
- Candidate B: `final_score=0.40`, `safety_flags=[]`

`rank_candidates([A, B])` must produce:
- Candidate B at rank 1
- Candidate A at rank 2
- Candidate A's `score_eligibility == "SUPPRESSED_BY_DOWNGRADE"`

This test FAILS if A is ranked above B.

---

### 7.2 — `tests/test_ranking_no_rank1_suppressed_when_clean_candidates_exist.py`
**Suite type:** regression  
**Priority:** P0  
**Proves:**  
If any candidate with `safety_flags=[]` and `blockers=[]` is present in the input, no `SUPPRESSED_BY_DOWNGRADE` candidate may appear at rank 1 in the output. The test must construct N>=3 candidates (1 clean, 2 suppressed) and assert `ranks[0].score_eligibility != "SUPPRESSED_BY_DOWNGRADE"`.

---

### 7.3 — `tests/test_ranking_idempotent_across_calls.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
Calling `rank_candidates()` twice with the same `OpportunityScoreReport` produces identical rank assignments (same rank numbers for the same strategy_ids). The test must assert `report1.ranks == report2.ranks`.

---

### 7.4 — `tests/test_scoring_feed_risk_tokens_all_produce_suppression.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
For every token in `FEED_RISK_TOKENS`, placing that token in a candidate's `safety_flags` and calling `rank_candidates` on a `SCORE_ELIGIBLE` candidate must produce `score_eligibility == "SUPPRESSED_BY_DOWNGRADE"`. Parameterize across all 14 FEED_RISK_TOKENS.

---

## Area 8 — No-Trade Evidence

### 8.1 — `tests/test_no_trade_fallback_used_true_with_no_source_fires.py`
**Suite type:** unit  
**Priority:** P0  
**Proves:**  
`assess_no_trade()` with `ctx.fallback_used=True` and `ctx.quote_source=None` must produce `no_trade=True` and `primary_reason == "NO_TRADE_FALLBACK_DATA"`. The test must NOT pass if `no_trade=False` is returned when `fallback_used=True` and `quote_source=None`.

---

### 8.2 — `tests/test_no_trade_stale_feed_fires_on_none_age.py`
**Suite type:** unit  
**Priority:** P0  
**Proves:**  
`assess_no_trade()` with `ctx.option_ltp_age_sec=None` must produce a signal with `reason == "NO_TRADE_STALE_FEED"` and `severity == 1.0`. The test must NOT pass if `no_trade=False` when age is None.

---

### 8.3 — `tests/test_no_trade_chop_threshold_is_module_constant_not_config.py`
**Suite type:** smoke  
**Priority:** P2  
**Proves:**  
`no_trade_engine.CHOP_THRESHOLD` equals 0.60 regardless of any config override. The test imports the constant and asserts it, then verifies that `assess_no_trade` with `chop_score=0.60` produces `no_trade=True`, and with `chop_score=0.59` produces `no_trade=False` (for chop only). This proves the threshold is stable and not externally configurable.

---

## Area 9 — Risk and Execution Safety

### 9.1 — `tests/test_execution_guard_live_env_disabled_always_blocks.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
When `LIVE_TRADING_ENABLED=false` is set in the environment, `ExecutionGuard.evaluate()` in LIVE mode must return `allowed=False` even when:
- A valid APPROVED approval exists in the approval store
- `trade.execution_allowed=True`
- `trade.confidence >= min_conf`
- `survival_gates` allows entry

The test must set the env var, construct a fully-valid trade object, and assert `decision.allowed == False`.

---

### 9.2 — `tests/test_execution_guard_survival_gate_takes_priority_over_confidence.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
When `survival_gates.evaluate()` returns `allowed_entries=False`, `ExecutionGuard.evaluate()` must return `allowed=False` with `reason_code == "SURVIVAL_GATE_BREACH"` regardless of confidence level. The test must construct a scenario where confidence exceeds `min_conf` but survival gates are breached, and assert the survival gate reason fires.

---

### 9.3 — `tests/test_execution_guard_destruction_sim_mode_never_leaks_live.py`
**Suite type:** destruction  
**Priority:** P0  
**Proves:**  
1,000 calls to `ExecutionGuard.evaluate()` in SIM mode with randomly varying confidence, regime, and capital values must never produce `allowed=True` with `mode == "LIVE"`. The test seeds `random.seed(42)` for reproducibility and asserts that the `mode` field in every decision that has `allowed=True` is never `"LIVE"`.

---

## Area 10 — Manual Approval and Live-Order Suppression

### 10.1 — `tests/test_approval_store_concurrent_consume_exactly_one_wins.py`
**Suite type:** integration  
**Priority:** P0  
**Proves:**  
Two threads calling `consume_valid_approval()` for the same `order_intent_hash` simultaneously must result in exactly one `(True, "approved_and_consumed")` and one `(False, "approval_used")`. The test uses `threading.Thread`, inserts a APPROVED record, fires both threads simultaneously, collects results, and asserts exactly one success.

---

### 10.2 — `tests/test_approval_store_expired_row_cannot_be_consumed.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
A record that is APPROVED but whose `expires_at_epoch` is in the past (e.g., `now - 1`) must produce `(False, "approval_expired")` from `consume_valid_approval()`. The test must insert a record with `expires_at_epoch = time.time() - 1` and assert the result.

---

### 10.3 — `tests/test_must_have_valid_approval_live_env_disabled_blocks_approved_intent.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
`must_have_valid_approval()` in LIVE mode with `LIVE_TRADING_ENABLED=false` must return `(False, "live_trading_env_disabled")` even when an APPROVED, non-expired record exists. The test must:
1. Insert an APPROVED record.
2. Set `LIVE_TRADING_ENABLED=false` in env.
3. Call `must_have_valid_approval(hash, mode="LIVE")`.
4. Assert `(False, "live_trading_env_disabled")`.

---

### 10.4 — `tests/test_approval_armed_window_enforced_independently_of_ttl.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
An approval that is APPROVED (TTL not expired) but whose armed window has expired (`armed_expires_at_epoch < now`) must fail `consume_valid_approval(require_armed=True)` with reason `approval_arm_expired`. The approval TTL (expires_at_epoch) must still be valid at the time of the test.

---

## Area 11 — Orchestrator Integration

### 11.1 — `tests/test_orchestrator_hold_gate_suppresses_candidates.py`
**Suite type:** integration  
**Priority:** P0  
**Proves:**  
When `feed_readiness_for_candidates()` returns a HOLD state, the orchestrator must not emit any candidates to the scoring pipeline. The test must mock the readiness check to return HOLD, run one orchestrator cycle, and assert that `candidate_pool.summary().total_count == 0` or the pipeline output has `candidates=[]`.

---

### 11.2 — `tests/test_orchestrator_reconnect_clears_stale_ranked_candidates.py`
**Suite type:** regression  
**Priority:** P1  
**Proves:**  
After a simulated WS disconnect + reconnect, the ranked candidates from the previous cycle must be cleared. The test must:
1. Run a cycle with candidates present.
2. Simulate disconnect.
3. Simulate reconnect.
4. Assert the candidate state is reset (not carrying over stale ranks from the pre-disconnect cycle).

---

### 11.3 — `tests/test_orchestrator_e2e_stale_feed_to_no_trade_evidence.py`
**Suite type:** integration  
**Priority:** P1  
**Proves:**  
End-to-end: feed enters STALE → freshness gate blocks → hold gate activates → no candidates emitted → no-trade evidence is written with `primary_reason == "NO_TRADE_STALE_FEED"`. The test must trace this through at least the gate → pipeline boundary.

---

## Area 12 — Dashboard / Runtime Artifact Contracts

### 12.1 — `tests/test_dashboard_does_not_import_execution_modules.py`
**Suite type:** smoke  
**Priority:** P0  
**Proves:**  
All Python modules under `dashboard/` must not directly import `core.execution_engine`, `core.execution_router`, `core.approval_store`, `core.kite_client`, or any `core.orders.*` module. The test uses `importlib` or static AST analysis to scan dashboard module imports and asserts none of the forbidden modules are referenced.

---

### 12.2 — `tests/test_runtime_snapshot_not_empty_after_market_open.py`
**Suite type:** contract  
**Priority:** P1  
**Proves:**  
The runtime snapshot file must not be empty (zero bytes) after any write cycle. The test uses `runtime_snapshot_producer` to write a minimal valid snapshot and asserts the file size > 0 and the JSON parses successfully.

---

### 12.3 — `tests/test_artifact_freshness_guard_fires_within_60s.py`
**Suite type:** unit  
**Priority:** P1  
**Proves:**  
`latest_artifact_freshness_guard` with a snapshot file that has a modification timestamp of `now - 65` seconds must produce a freshness alert/STALE result. The test must simulate file age without actually sleeping, using `os.utime` or a mock.

---

### 12.4 — `tests/test_candidate_executability_evidence_never_executable_for_fallback.py`
**Suite type:** contract  
**Priority:** P0  
**Proves:**  
The candidate executability evidence artifact must set `allowed_for_live_execution=False` for any candidate whose `quote_truth.execution_eligible=False`. The test must build an evidence payload with a fallback candidate and assert the output field value directly.

---

## Matrix Summary

| Area | Test file | Suite type | Priority |
|------|-----------|-----------|----------|
| 1 | test_feed_freshness_gate_stale_allow_quotes_never_executable.py | contract | P0 |
| 1 | test_feed_freshness_gate_degraded_blocked_not_advisory.py | unit | P0 |
| 1 | test_feed_freshness_gate_zombie_feed_blocked.py | integration | P1 |
| 1 | test_feed_recovery_warmup_gate_blocks_candidates.py | regression | P1 |
| 2 | test_depth_ws_on_connect_resubscribes_all_option_tokens.py | integration | P0 |
| 2 | test_depth_ws_grace_period_does_not_mask_stale_after_window.py | regression | P1 |
| 2 | test_depth_ws_destruction_reconnect_cycles_no_zombie_subscriptions.py | destruction | P1 |
| 2 | test_depth_ws_no_offhours_refresh.py | unit | P2 |
| 3 | test_option_tick_stale_ts_epoch_not_fresh.py | unit | P0 |
| 3 | test_exact_option_token_freshness_gate_hard_blocks_old_token.py | contract | P0 |
| 3 | test_option_tick_never_received_blocks_hard.py | unit | P0 |
| 4 | test_quote_truth_recovered_fallback_never_executable.py | contract | P0 |
| 4 | test_quote_truth_none_ltp_none_status_is_safe.py | unit | P1 |
| 4 | test_quote_truth_live_transition_from_fallback_requires_live_tick.py | regression | P1 |
| 4 | test_execution_grade_firewall_rejects_fallback_quote.py | contract | P0 |
| 5 | test_candidate_generator_stale_context_produces_advisory_only.py | integration | P1 |
| 5 | test_candidate_generator_market_closed_produces_advisory.py | unit | P1 |
| 5 | test_candidate_normalizer_stable_strategy_id.py | unit | P2 |
| 6 | test_candidate_pool_dedup_prefers_higher_capability.py | contract | P0 |
| 6 | test_candidate_pool_lifecycle_snapshot_accuracy.py | unit | P1 |
| 6 | test_candidate_pool_executable_count_not_inflated_by_soft_reject.py | regression | P1 |
| 7 | test_ranking_fallback_candidate_demoted_below_clean_low_score.py | contract | P0 |
| 7 | test_ranking_no_rank1_suppressed_when_clean_candidates_exist.py | regression | P0 |
| 7 | test_ranking_idempotent_across_calls.py | unit | P1 |
| 7 | test_scoring_feed_risk_tokens_all_produce_suppression.py | contract | P0 |
| 8 | test_no_trade_fallback_used_true_with_no_source_fires.py | unit | P0 |
| 8 | test_no_trade_stale_feed_fires_on_none_age.py | unit | P0 |
| 8 | test_no_trade_chop_threshold_is_module_constant_not_config.py | smoke | P2 |
| 9 | test_execution_guard_live_env_disabled_always_blocks.py | contract | P0 |
| 9 | test_execution_guard_survival_gate_takes_priority_over_confidence.py | unit | P1 |
| 9 | test_execution_guard_destruction_sim_mode_never_leaks_live.py | destruction | P0 |
| 10 | test_approval_store_concurrent_consume_exactly_one_wins.py | integration | P0 |
| 10 | test_approval_store_expired_row_cannot_be_consumed.py | contract | P0 |
| 10 | test_must_have_valid_approval_live_env_disabled_blocks_approved_intent.py | contract | P0 |
| 10 | test_approval_armed_window_enforced_independently_of_ttl.py | unit | P1 |
| 11 | test_orchestrator_hold_gate_suppresses_candidates.py | integration | P0 |
| 11 | test_orchestrator_reconnect_clears_stale_ranked_candidates.py | regression | P1 |
| 11 | test_orchestrator_e2e_stale_feed_to_no_trade_evidence.py | integration | P1 |
| 12 | test_dashboard_does_not_import_execution_modules.py | smoke | P0 |
| 12 | test_runtime_snapshot_not_empty_after_market_open.py | contract | P1 |
| 12 | test_artifact_freshness_guard_fires_within_60s.py | unit | P1 |
| 12 | test_candidate_executability_evidence_never_executable_for_fallback.py | contract | P0 |

**Total proposed tests:** 41  
**P0 (existential safety):** 22  
**P1 (high risk):** 16  
**P2 (medium risk):** 3
