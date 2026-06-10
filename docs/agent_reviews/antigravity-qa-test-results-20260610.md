# Antigravity QA Test Results — 2026-06-10

**Branch:** qa/antigravity-elite-test-pack-20260610  
**Run date:** 2026-06-10  
**Scope:** P0 regression test slice only. No production code modified.

---

## Test Files Created

| File | Gap closed | Tests | Result |
|------|-----------|-------|--------|
| `tests/test_p0_feed_freshness_stale_quotes_never_executable.py` | GAP-01 | 6 | ✅ 6 passed |
| `tests/test_p0_quote_truth_fallback_never_executable.py` | GAP-02 | 14 | ✅ 14 passed |
| `tests/test_p0_approval_live_env_disabled.py` | GAP-03 | 6 | ✅ 6 passed |
| `tests/test_p0_approval_consume_single_use.py` | GAP-04 + GAP-05 | 6 | ✅ 6 passed |
| `tests/test_p0_ranking_eligibility_priority_contract.py` | GAP-07 + GAP-08 | 31 | ✅ 31 passed |

**Total new tests:** 63  
**Total passed:** 63  
**Total failed:** 0  
**Production code modified:** None  
**Test code modified (existing files):** None

---

## Pytest Commands and Output

### Run 1 — New P0 tests only

```
cd /Users/madhuram/tradebot && python -m pytest \
  tests/test_p0_feed_freshness_stale_quotes_never_executable.py \
  tests/test_p0_quote_truth_fallback_never_executable.py \
  tests/test_p0_approval_live_env_disabled.py \
  tests/test_p0_approval_consume_single_use.py \
  tests/test_p0_ranking_eligibility_priority_contract.py \
  -v --tb=short
```

**Output (abridged — all 63 PASSED):**

```
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_never_produces_live_execution_eligibility PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_with_explicitly_fresh_ltp_still_not_executable PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_false_does_not_suppress_clean_feed PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_never_executable_across_states[PLANNING] PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_never_executable_across_states[OFFHOURS] PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_never_executable_across_states[DEGRADED] PASSED
tests/test_p0_feed_freshness_stale_quotes_never_executable.py::test_allow_stale_quotes_decision_is_not_order_action_and_is_read_only PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_recovered_fallback_quote_source_is_never_execution_eligible PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_recovered_fallback_blocks_without_require_source PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[CLOSE_FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[DERIVED_FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[FALLBACK_RECOVERED] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[QUOTE_FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[RECOVERED_FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[REST_FALLBACK] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_every_fallback_quote_source_member_blocks_execution[SYNTHETIC_OFFHOURS] PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_fallback_option_ltp_source_blocks_when_quote_source_is_none PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_fallback_source_in_nested_source_flags_blocks_execution PASSED
tests/test_p0_quote_truth_fallback_never_executable.py::test_live_quote_source_remains_execution_eligible PASSED
tests/test_p0_approval_live_env_disabled.py::test_must_have_valid_approval_live_env_disabled_blocks_even_with_approved_record PASSED
tests/test_p0_approval_live_env_disabled.py::test_must_have_valid_approval_live_env_true_and_approved_record_succeeds PASSED
tests/test_p0_approval_live_env_disabled.py::test_must_have_valid_approval_live_env_disabled_blocks_even_without_any_record PASSED
tests/test_p0_approval_live_env_disabled.py::test_execution_guard_evaluate_does_not_check_approval_store PASSED
tests/test_p0_approval_live_env_disabled.py::test_execution_guard_live_env_disabled_blocks_before_guard_can_allow PASSED
tests/test_p0_approval_live_env_disabled.py::test_must_have_valid_approval_sim_mode_not_required_by_default PASSED
tests/test_p0_approval_consume_single_use.py::test_consume_valid_approval_is_single_use_first_call_succeeds PASSED
tests/test_p0_approval_consume_single_use.py::test_consume_valid_approval_n_rapid_calls_produce_exactly_one_success PASSED
tests/test_p0_approval_consume_single_use.py::test_expired_wall_clock_row_still_approved_in_db_is_rejected PASSED
tests/test_p0_approval_consume_single_use.py::test_future_expiry_approved_row_is_consumable PASSED
tests/test_p0_approval_consume_single_use.py::test_used_approval_cannot_be_reapproved_after_consume PASSED
tests/test_p0_approval_consume_single_use.py::test_consume_with_empty_hash_is_rejected PASSED
tests/test_p0_ranking_eligibility_priority_contract.py::test_suppressed_high_score_never_ranked_1_when_score_eligible_exists PASSED
tests/test_p0_ranking_eligibility_priority_contract.py::test_suppressed_never_rank1_with_any_score_eligible_in_mixed_pool PASSED
tests/test_p0_ranking_eligibility_priority_contract.py::test_each_feed_risk_token_in_safety_flags_suppresses_score_eligible[fallback] PASSED
... (all 13 FEED_RISK_TOKENS parametrized variants for safety_flags) ...
tests/test_p0_ranking_eligibility_priority_contract.py::test_each_feed_risk_token_in_warnings_suppresses_score_eligible[fallback] PASSED
... (all 13 FEED_RISK_TOKENS parametrized variants for warnings) ...
tests/test_p0_ranking_eligibility_priority_contract.py::test_rank_candidates_is_idempotent_across_two_calls PASSED
tests/test_p0_ranking_eligibility_priority_contract.py::test_feed_risk_suppression_does_not_mutate_source_record_eligibility PASSED
tests/test_p0_ranking_eligibility_priority_contract.py::test_advisory_with_feed_risk_token_stays_advisory_not_double_suppressed PASSED

============================== 63 passed in 3.01s ==============================
```

---

### Run 2 — Pre-existing related test suites (regression check)

```
cd /Users/madhuram/tradebot && python -m pytest \
  tests/test_feed_freshness_gate.py \
  tests/test_edge42_quote_truth_contract.py \
  tests/test_edge41_fallback_execution_firewall.py \
  tests/test_order_approval_store.py \
  tests/test_candidate_ranking.py \
  tests/test_manual_approval_enforcement.py \
  tests/test_risk_execution_decisions.py \
  -v --tb=short 2>&1 | tail -30
```

**Result:** 74 passed in 9.64s — zero regressions

---

## What Each Test File Proves

### `test_p0_feed_freshness_stale_quotes_never_executable.py`

| Test | What it proves |
|------|---------------|
| `test_allow_stale_quotes_never_produces_live_execution_eligibility` | `allow_stale_quotes=True` in a fully-healthy feed state produces `allowed_for_live_execution=False`, `allowed_for_paper_execution=False`, `advisory_only=True` |
| `test_allow_stale_quotes_with_explicitly_fresh_ltp_still_not_executable` | Even with ltp.age_sec=0.1s (very fresh), the session-level flag still blocks |
| `test_allow_stale_quotes_false_does_not_suppress_clean_feed` | Baseline sanity — False flag leaves clean feed unaffected |
| `test_allow_stale_quotes_never_executable_across_states` | Parametrized: PLANNING, OFFHOURS, DEGRADED states all blocked |
| `test_allow_stale_quotes_decision_is_not_order_action_and_is_read_only` | Safety envelope: `is_order_action=False`, `append=False` for all flag values |

---

### `test_p0_quote_truth_fallback_never_executable.py`

| Test | What it proves |
|------|---------------|
| `test_recovered_fallback_quote_source_is_never_execution_eligible` | The specific high-profile source from the audit: `RECOVERED_FALLBACK` → `execution_eligible=False`, `rank_eligible=False`, `source_trust="fallback"`, reason present |
| `test_recovered_fallback_blocks_without_require_source` | Blocking does not depend on `require_source=True` |
| `test_every_fallback_quote_source_member_blocks_execution[*]` | Parametrized across all 8 `FALLBACK_QUOTE_SOURCES` members — each must block |
| `test_fallback_option_ltp_source_blocks_when_quote_source_is_none` | `quote_source=None` + `option_ltp_source="RECOVERED_FALLBACK"` → blocked |
| `test_fallback_source_in_nested_source_flags_blocks_execution` | Source inside `source_flags["quote_truth"]` still triggers fallback classification |
| `test_live_quote_source_remains_execution_eligible` | Baseline: live source is not affected |

---

### `test_p0_approval_live_env_disabled.py`

| Test | What it proves |
|------|---------------|
| `test_must_have_valid_approval_live_env_disabled_blocks_even_with_approved_record` | **Core GAP-03**: `(False, "live_trading_env_disabled")` when env var is false even with a valid approved record |
| `test_must_have_valid_approval_live_env_true_and_approved_record_succeeds` | Positive control: env=true + approved record → success |
| `test_must_have_valid_approval_live_env_disabled_blocks_even_without_any_record` | Env check fires before DB lookup — reason is not "approval_missing" |
| `test_execution_guard_evaluate_does_not_check_approval_store` | Structural proof: `ExecutionGuard.evaluate()` is not the approval authority (by design) |
| `test_execution_guard_live_env_disabled_blocks_before_guard_can_allow` | LIVE + market_closed → MARKET_CLOSED reason before any approval path |
| `test_must_have_valid_approval_sim_mode_not_required_by_default` | SIM mode approval not required when APPROVAL_REQUIRED_MODES=PAPER,LIVE |

---

### `test_p0_approval_consume_single_use.py`

| Test | What it proves |
|------|---------------|
| `test_consume_valid_approval_is_single_use_first_call_succeeds` | First consume succeeds, second returns `approval_used` |
| `test_consume_valid_approval_n_rapid_calls_produce_exactly_one_success` | 5 sequential calls → exactly 1 success, 4 `approval_used` rejections |
| `test_expired_wall_clock_row_still_approved_in_db_is_rejected` | **GAP-05 TOCTOU**: row with `expires_at_epoch=now-1` but `status=APPROVED` → `approval_expired` |
| `test_future_expiry_approved_row_is_consumable` | Positive control: future-expiry row is consumable |
| `test_used_approval_cannot_be_reapproved_after_consume` | Re-approval attempt on USED record → `approval_already_used` |
| `test_consume_with_empty_hash_is_rejected` | Empty hash guard → `approval_hash_missing` |

---

### `test_p0_ranking_eligibility_priority_contract.py`

| Test | What it proves |
|------|---------------|
| `test_suppressed_high_score_never_ranked_1_when_score_eligible_exists` | **Core GAP-07**: `final_score=0.99` SUPPRESSED candidate is rank 2 behind `final_score=0.52` SCORE_ELIGIBLE |
| `test_suppressed_never_rank1_with_any_score_eligible_in_mixed_pool` | SCORE_ELIGIBLE holds rank 1 regardless of input position in pool of 5 |
| `test_each_feed_risk_token_in_safety_flags_suppresses_score_eligible[*]` | **GAP-08**: all 13 FEED_RISK_TOKENS in safety_flags produce SUPPRESSED_BY_DOWNGRADE |
| `test_each_feed_risk_token_in_warnings_suppresses_score_eligible[*]` | All 13 FEED_RISK_TOKENS in warnings field also produce suppression |
| `test_rank_candidates_is_idempotent_across_two_calls` | Two calls with the same input produce identical rank order |
| `test_feed_risk_suppression_does_not_mutate_source_record_eligibility` | Source `OpportunityScoreRecord` objects are never mutated by the ranker |
| `test_advisory_with_feed_risk_token_stays_advisory_not_double_suppressed` | ADVISORY_ONLY candidates are not double-suppressed by feed risk tokens |

---

## Production Bugs Found

**None.** All 63 tests pass against the current production codebase without modification.

This means:

- The current `assess_feed_freshness_gate` correctly blocks `allow_stale_quotes=True` at the decision output level.
- `classify_quote_truth` correctly classifies all 8 `FALLBACK_QUOTE_SOURCES` members as `execution_eligible=False`.
- `must_have_valid_approval` correctly checks `LIVE_TRADING_ENABLED` before the DB lookup.
- `consume_valid_approval` correctly enforces single-use semantics and wall-clock expiry.
- `rank_candidates` correctly enforces `ELIGIBILITY_PRIORITY` across all 13 `FEED_RISK_TOKENS`.

> [!NOTE]
> The audit concern about the `reasons` list in `quote_truth.py` was confirmed safe: `QUOTE_SOURCE_FALLBACK_REASON` is always appended to `reasons` for fallback sources, and `eligibility_ok` is set to `False` correctly because `source_trust` is `"fallback"`, which is not in the trusted set. The parametrized test (14 variants) proves this is correct for all 8 members.

---

## What Was Not Changed

- No production code modified.
- No existing test files modified.
- No strategy thresholds changed.
- No feed, runtime, or dashboard behavior changed.
- No broker APIs called.
- No live mode touched.
- No scoring or ranking behavior changed.

---

## Files Created

- `tests/test_p0_feed_freshness_stale_quotes_never_executable.py`
- `tests/test_p0_quote_truth_fallback_never_executable.py`
- `tests/test_p0_approval_live_env_disabled.py`
- `tests/test_p0_approval_consume_single_use.py`
- `tests/test_p0_ranking_eligibility_priority_contract.py`
- `docs/agent_reviews/antigravity-qa-test-results-20260610.md` (this file)

---

## Remaining P0 Gaps (Not Yet Implemented)

These are from the matrix but outside the scope of this task:

| Gap | Status |
|-----|--------|
| GAP-09 — Pool dedup prefers higher capability | Not implemented |
| GAP-10 — no_trade fallback_used=True with no source | Not implemented |
| GAP-11 — NO_TRADE_STALE_FEED fires on None age | Not implemented |
| GAP-12 — WS on_connect resubscribes all option tokens | Not implemented |
| GAP-13 — Stale ts_epoch with absent quote_ts classified as stale | Not implemented |
| GAP-14 — Execution grade firewall rejects fallback quote | Not implemented |
| GAP-15 — Dashboard does not import execution modules | Not implemented |
