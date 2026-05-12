# Elite Runtime Truth Roadmap

Branch: `hardening/elite-runtime-truth-roadmap`
Base: `main` at `fdd83bac14c8f31e03e1545c496bdb7805acbbdf`

## Purpose

This branch turns Tradebot from an MVP that can emit/display candidates into an elite runtime-truth system that can safely survive live-market validation.

The goal is not more strategies. The goal is cleaner truth, stricter execution permission, reliable feed state, fallback isolation, ranking separation, and repeatable live-shadow/paper validation.

---

## Non-Negotiable Rules

1. `core/decision_engine.py` is the only final execution authority.
2. Review queue, dashboard, persistence, and finalization may preserve or downgrade decisions, but must never upgrade them.
3. Fallback, synthetic, recovered, stale, weak-signal, or softened candidates are never executable.
4. Runtime feed truth overrides strategy confidence.
5. UI displays backend truth; UI must not infer execution readiness.
6. CI must be green before live validation.
7. Live validation proves runtime behavior; it does not replace tests.

---

## MVP+ Definition

The MVP+ version must provide:

- canonical candidate lifecycle
- single execution permission contract
- exact blocker/reason for every non-executable candidate
- feed/runtime readiness truth
- option-token resolution truth
- fallback lineage
- ranking separation report
- live-shadow validation
- paper execution validation
- tiny-live readiness gates

Out of scope until MVP+ is stable:

- new ML models
- reinforcement learning
- option selling
- multi-broker abstraction
- auto live expansion
- new strategy families
- dashboard cosmetics without backend truth

---

## Canonical Candidate Lifecycle

```text
RAW_SIGNAL
  -> CANDIDATE
  -> SCORED
  -> RANKED
  -> SELECTED
  -> EXECUTION_READY
  -> ORDER_INTENT
  -> PAPER_RESULT / LIVE_RESULT
```

Invalid states:

```text
softened but executable
fallback but selected
queue_only but promoted
advisory but tradable
unknown quote source but execution_ok
```

---

## Phase 1 — Stop Execution Permission Corruption

### Goal

Only the decision engine may produce final `EXECUTE` permission.

### Files

```text
core/decision_engine.py
core/review_queue.py
core/candidate_finalization.py
core/orchestrator.py
dashboard/ui/table_model.py
strategies/trade_builder.py
```

### Rules

```text
QUEUE_ONLY cannot become EXECUTE outside decision_engine
ADVISORY_ONLY cannot become QUEUE_ONLY or EXECUTE outside decision_engine
fallback cannot become EXECUTE
weak_signal cannot become EXECUTE
low raw_rank cannot become EXECUTE
```

### Tests

```bash
pytest -q tests/test_review_queue_decision_engine.py tests/test_review_queue_fallback_execution.py tests/test_advisory_level_reconciliation.py
```

---

## Phase 2 — Lock Soft-Reject Candidates to Advisory/Debug

Soft-reject rows are useful for visibility, but they must not contaminate ranked, selected, executable, or capital-allocation pools.

Required contract:

```text
softened_builder_path -> ADVISORY_ONLY
weak_signal -> QUEUE_ONLY or ADVISORY_ONLY only
no_signal -> ADVISORY_ONLY/debug only
missing_quote -> ADVISORY_ONLY
missing_depth -> ADVISORY_ONLY
latency_guard_cooldown -> ADVISORY_ONLY/debug only
no_candidates_survived -> ADVISORY_ONLY/debug only
```

Required fields for softened/debug rows:

```text
execution_allowed = False
execution_ok = False
eligible_for_execution = False
permission = ADVISORY_ONLY
final_action = ADVISORY_ONLY
execution_status = advisory_only
```

Tests:

```bash
pytest -q tests/test_decision_traceability.py tests/test_orchestrator_decision_event.py tests/test_trade_builder_soft_vetoes.py tests/test_trade_builder.py
```

---

## Phase 3 — Feed and Readiness Truth

Hard runtime block rules:

```text
ws_connected = false -> BLOCKED
runtime_state = SUBSCRIBE_FAILED -> BLOCKED
subscribed_option_tokens_count = 0 -> BLOCKED
live option depth missing -> BLOCKED or DEGRADED
stale option LTP -> not executable
missing tick stream -> not executable
```

Files:

```text
core/readiness_gate.py
core/freshness_sla.py
core/kite_depth_ws.py
core/market_data.py
core/tick_store.py
```

Tests:

```bash
pytest -q tests/test_feed_health_epoch_missing.py tests/test_feed_freshness_units.py tests/test_readiness_snapshot_consistency.py tests/test_stale_option_prune_hysteresis.py
```

---

## Phase 4 — Centralized Timestamp Normalization

Create/centralize:

```text
core/time_normalization.py
```

Required helpers:

```text
coerce_epoch_seconds(value)
coerce_utc_datetime(value)
format_ist(value)
normalize_timestamp_payload(row)
```

Must support ISO strings, datetimes, pandas timestamps, epoch seconds, milliseconds, microseconds, and nanoseconds.

Tests:

```bash
pytest -q tests/test_normalize_trade_df.py tests/test_timestamp_formatting.py tests/test_ui_table_model.py tests/test_feed_freshness_units.py
```

---

## Phase 5 — Contract and Quote Lineage

Rules:

```text
exact_contract_match + live/depth quote -> potentially executable
safe_nearest_contract_fallback -> advisory only
fallback quote -> advisory only
synthetic chain -> advisory only
unknown quote source -> advisory only
missing contract -> reject/advisory only
```

Cherry-pick safe resolver hardening from `hardening/main-stale-executable-quality` after Phase 1-4 gates are stable.

Tests:

```bash
pytest -q tests/test_option_token_resolver.py tests/test_option_tradability_precondition.py tests/test_option_premium_units.py tests/test_trade_builder_mark_price.py
```

---

## Phase 6 — Candidate Pool and Ranking Separation

Architecture:

```text
strategies -> candidate_pool -> data_quality -> scoring -> ranking -> selection -> decision_engine
```

Required ranking metrics:

```text
candidate_count
ranked_count
executable_count
fallback_count
synthetic_count
soft_reject_count
top_score
median_score
score_spread
top_minus_median
raw_rank_min
raw_rank_max
```

Bad ranking example:

```text
0.46, 0.45, 0.44
```

Good ranking example:

```text
top_score >= 0.75
median_score 0.35-0.60
top_minus_median >= 0.15
```

Cherry-pick from `feature/elite-opportunity-engine-bible` only in controlled pieces, not as one large merge.

---

## Phase 7 — Dashboard Truth Model

Dashboard sections:

```text
1. Runtime health
2. Top executable opportunities
3. Near-executable queue
4. Advisory/debug candidates
5. Rejection wall
6. Feed/contract/quote lineage
7. Paper execution results
```

UI must never promote, repair, or infer execution readiness.

Tests:

```bash
pytest -q tests/test_ui_table_model.py tests/test_dashboard_live_suggestions.py tests/test_advisory_timestamp_semantics.py
```

---

## Phase 8 — Offline Elite Validation

Required commands:

```bash
PYTHONPATH=. pytest -q
python scripts/offline_elite_pipeline_validate.py --inputs tests/fixtures/candidates_truth_sample.json --out-json logs/offline_elite_pipeline_report.json --out-md logs/offline_elite_pipeline_report.md --fail-on-dirty-capital --print-summary
```

Pass condition:

```text
no fallback executable
no synthetic executable
no weak_signal executable
no stale executable
ranking separation present
capital allocation only touches clean executable candidates
```

---

## Phase 9 — Live Shadow Validation

No live orders.

Metrics:

```text
ws_connected
runtime_state
subscribed_option_tokens_count
ltp_age_sec
depth_age_sec
candidate_count
ranked_count
executable_count
fallback_count
soft_reject_count
score_spread
top_candidate_truth_quality
top_candidate_contract_resolution_path
top_candidate_quote_source
```

Stop conditions:

```text
SUBSCRIBE_FAILED
0 option tokens subscribed
fallback executable > 0
synthetic executable > 0
weak_signal executable > 0
stale executable > 0
missing entry/stop/target in executable rows
```

---

## Phase 10 — Paper Execution Validation

Rules:

```text
paper only
max 1-3 candidates
exact contract only
fresh quote only
depth available
no fallback
no synthetic
no weak signal
```

Required evidence:

```text
paper entry price
expected slippage
fill probability
stop loss
target
exit reason
paper P&L
runtime feed state at entry
runtime feed state at exit
```

---

## Phase 11 — Tiny Live Readiness

Only after CI, offline validation, live shadow, and paper validation pass.

Required controls:

```text
kill switch enabled
daily max loss configured
one trade max
smallest practical quantity
broker reconciliation enabled
duplicate order guard enabled
manual monitoring active
feed stale kill-switch enabled
```

---

## Immediate Work Order

1. Remove review queue upward promotion.
2. Lock soft-reject candidates to advisory/debug only.
3. Fix readiness gate runtime blocking.
4. Centralize timestamp normalization.
5. Enforce fallback/synthetic advisory-only contract.
6. Cherry-pick safe resolver hardening from PR #32.
7. Add candidate-pool ranking separation metrics.
8. Add live shadow truth report.
9. Clean dashboard to display backend truth only.
10. Run full CI before live validation.
