# Antigravity QA Architecture Audit — 2026-06-10

**Branch:** qa/antigravity-elite-test-pack-20260610  
**Scope:** Read-only architecture audit. No production code modified. No test files modified.  
**Auditor:** Antigravity Agent  
**Audit date:** 2026-06-10

---

## Audit Summary

This document maps each of the 12 audit areas to: production files, existing tests, the highest-risk behavior in that area, and the explicit gap between what is tested and what must be proven. It is the basis for `elite-test-matrix-20260610.md` and `qa-coverage-gaps-20260610.md`.

All findings are read-only observations. Nothing was changed.

---

## Area 1 — Feed Health / Freshness / Feed Runtime

### Production files
| File | Role |
|------|------|
| `core/feed_freshness_gate.py` | Authoritative freshness → execution gate. Converts a freshness-status payload into `FeedFreshnessGateDecision` with `allowed_for_live_execution`, `allowed_for_paper_execution`, `advisory_only`, and typed blockers. |
| `core/feed_health.py` | Feed health truth state machine. |
| `core/feed_health_truth.py` | Feed health truth collector. |
| `core/feed/health.py` | Feed sub-package health module. |
| `core/feed_runtime.py` | Feed runtime coordinator. |
| `core/feed/runtime.py` | Feed sub-package runtime state manager. |
| `core/feed/runtime_store.py` | Persistent runtime state store (SQLite/file). |
| `core/feed_supervisor.py` | Feed lifecycle supervisor with reconnect escalation. |
| `core/feed_freshness.py` | Lower-level freshness SLA oracle. |
| `core/freshness_sla.py` | Freshness SLA definitions and epoch-based staleness logic. |
| `core/feed_staleness_observability.py` | Staleness observability export. |
| `core/feed_hold_gate.py` | Feed hold gate — prevents candidate emission during feed instability. |
| `core/feed_readiness_for_candidates.py` | Declares when feed state is safe for candidate pipeline. |
| `core/feed_startup_lifecycle.py` | Feed startup sequence lifecycle. |
| `core/feed_recovery_coordinator.py` | Coordinates feed recovery transitions. |
| `core/feed_recovery_runtime.py` | Feed recovery runtime logic. |
| `core/feed_recovery_warmup_gate.py` | Warmup gate after feed recovery (blocks candidates during warmup). |
| `core/feed_zombie_state.py` | Detects zombie (alive but non-emitting) feed states. |
| `core/feed_circuit_breaker.py` | Triggers circuit break after repeated failures. |
| `core/feed_restart_guard.py` | Guards against infinite restart loops. |
| `core/live_truth_feed_runtime_writer_liveness.py` | Runtime liveness writer. |

### Existing test files
- `tests/test_feed_freshness_gate.py` — gate state transitions, STALE/BLOCKED/FRESH, allow_stale_quotes flag
- `tests/test_feed_health.py` — feed health state machine
- `tests/test_feed_health_epoch_missing.py` — missing epoch fallback
- `tests/test_feed_health_market_closed.py` — market-closed boundary
- `tests/test_feed_runtime_state_machine.py` — state machine transitions
- `tests/test_feed_runtime_states.py` — (large, 35KB) state enum coverage
- `tests/test_feed_runtime_store_lifecycle.py` — store lifecycle
- `tests/test_feed_supervisor_state_machine.py` — supervisor state machine
- `tests/test_feed_circuit_breaker.py` — circuit breaker
- `tests/test_feed_restart_guard.py` — restart guard
- `tests/test_feed_startup_lifecycle.py` — startup lifecycle
- `tests/test_feed_startup_root_cause_report.py` — startup root cause
- `tests/test_feed_staleness_observability.py` — staleness observability
- `tests/test_pr_feed_03_feed_hold_gate.py` — hold gate
- `tests/test_pr_feed_04_feed_recovery_warmup_gate.py` — warmup gate
- `tests/test_pr_feed_20_feed_runtime_evidence_bundle.py` — evidence bundle
- `tests/test_live_truth_04_feed_runtime_writer_liveness.py` — liveness
- `tests/test_feed_recovery_coordinator.py` — coordinator
- `tests/test_feed_recovery_runtime.py` — recovery runtime
- `tests/test_feed_recovery_evidence.py` — recovery evidence
- `tests/test_feed_00_canonical_feed_truth.py` — canonical feed truth

### Highest-risk behavior
**`allow_stale_quotes=True` must never produce `allowed_for_live_execution=True`.**  
The gate currently sets `ALLOW_STALE_QUOTES_ACTIVE` as a blocker but this is only correct if the downstream execution path reads `allowed_for_live_execution` and not `allowed_for_paper_execution`. If a caller checks `allowed_for_paper_execution` in paper mode while `allow_stale_quotes` is active, a stale-quote candidate can enter the paper trade path. This boundary is implicitly tested but not explicitly asserted as a combined decision proof.

**Second-highest risk:** A zombie feed (connected=True, ws_connected=True, but no ticks arriving) can produce a freshness state of `OK` if the epoch-based staleness check has a lagging timer. The zombie detection in `feed_zombie_state.py` is not systematically tested with freshness gate integration.

### Gap summary
- No test proves that `allow_stale_quotes=True` + `market_open=True` + `ok=True` never yields `allowed_for_live_execution=True` with direct gate output assertion.
- No integration test proves that a zombie feed state (connected, no ticks > 30s) eventually produces `BLOCKED` from the gate.
- No test proves that `DEGRADED` + `fail_on_degraded=True` produces `BLOCKED` (not `ADVISORY_ONLY`).
- No regression test covers recovery warmup gate blocking candidates during the warmup window after reconnect.

---

## Area 2 — Depth WebSocket Reconnect / Resubscribe

### Production files
| File | Role |
|------|------|
| `core/kite_depth_ws.py` | Core WebSocket depth feed (273KB — largest single production file). |
| `core/depth_subscription_engine.py` | Rewrite scaffold: `build_subscription_tokens`, `_prune_stale_option_subscription_tokens`, `_maybe_refresh_stale_option_subscription_universe`. |
| `core/depth_store.py` | Depth quote store. |
| `core/depth_hook_cleanup.py` | Hook cleanup on disconnect. |
| `core/feed/reconnect_policy.py` | Reconnect decision policy (backoff, quarantine). |
| `core/feed/ws_lifecycle_shell.py` | WS lifecycle shell (connect, on_connect, on_close, on_error callbacks). |
| `core/feed/ws_callback_thin_wiring.py` | Callback thin wiring — separates WS events from depth logic. |
| `core/feed/subscription_budget_policy.py` | Token budget enforcement before subscription. |
| `core/feed/token_resolution_read_model.py` | Token resolution read model. |
| `core/subscription_truth_contract.py` | Subscription truth contract. |

### Existing test files
- `tests/test_kite_depth_restart.py` — (91KB) largest test file; reconnect/restart scenarios
- `tests/test_kite_depth_ws_stability.py` — (56KB) WS stability scenarios
- `tests/test_depth_subscription_tokens.py` — (30KB) subscription token building
- `tests/test_on_connect_forces_subscribe.py` — on_connect resubscription
- `tests/test_pr_feed_09_reconnect_policy.py` — reconnect decision policy
- `tests/test_pr_feed_10_subscription_budget_policy.py` — budget policy
- `tests/test_pr_feed_18_ws_lifecycle_shell.py` — lifecycle shell
- `tests/test_pr_feed_19_ws_callback_thin_wiring.py` — callback thin wiring
- `tests/test_feed_reconnect_quarantine.py` — reconnect quarantine
- `tests/test_kite_depth_rebalance.py` — rebalance logic
- `tests/test_kite_depth_ws_handshake_proof_wiring.py` — handshake proof
- `tests/test_ws_handshake_credential_proof.py` — credential proof
- `tests/test_subscription_truth_contract.py` — subscription truth

### Highest-risk behavior
**After reconnect, `on_connect` must force a full resubscription within a bounded window.**  
`test_on_connect_forces_subscribe.py` exists but it is unclear whether it asserts that all previously-subscribed option tokens are re-sent to the broker WS, not just that the subscribe method is invoked. A partial resubscription (only index tokens, not all option strikes) is a silent failure that leaves option ticks dark for the entire session.

**Second-highest risk:** `_prune_stale_option_subscription_tokens` with `require_session_tick=True` means that if `_SYMBOL_LAST_OPTION_TICK_TS` has no entry for a symbol (first tick not yet received after reconnect), all tokens for that symbol are skipped/retained in a grace state — but the grace period (`FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC`, default 60s) could allow up to 60s of missed option data post-reconnect without a visible feed error.

### Gap summary
- No test proves that after a WS `on_close`, `on_connect` sends `subscribe(all_option_tokens)` within 5 seconds.
- No test proves that the grace period does not prevent a legitimate stale detection from firing after 60+1 seconds.
- No test asserts that `_maybe_refresh_stale_option_subscription_universe` does not trigger during market-closed periods (regression: off-hours refresh attempts).
- No destruction test simulates repeated disconnect/reconnect cycles and asserts that subscription state converges rather than accumulating zombie subscriptions.

---

## Area 3 — Option Tick Verification

### Production files
| File | Role |
|------|------|
| `core/exact_option_token_freshness_gate.py` | Per-token freshness gate for exact option ticks. |
| `core/candidate_quote_freshness.py` | Quote freshness contract for candidates. |
| `core/freshness_evaluator.py` | Freshness evaluator — per-token age computation. |
| `core/quote_age_truth.py` | Canonical quote age truth — handles multiple timestamp fields. |
| `core/tick_store.py` | Tick store — persistent and in-memory. |
| `core/feed/tick_utils.py` | Tick utility helpers — age, epoch normalization. |
| `core/stale_feed_simulator.py` | Stale feed simulator for test injection. |

### Existing test files
- `tests/test_pr_feed_05_exact_option_token_freshness_gate.py` — per-token freshness gate
- `tests/test_candidate_quote_freshness_contract.py` — candidate quote freshness
- `tests/test_trade_builder_stale_option_tick.py` — stale option tick in trade builder
- `tests/test_stale_option_prune_hysteresis.py` — hysteresis behavior
- `tests/test_pr_feed_08_tick_utils.py` — tick utils
- `tests/test_stale_feed_simulator.py` — simulator
- `tests/test_quote_freshness.py` — quote freshness
- `tests/test_feed_freshness_units.py` — freshness SLA units
- `tests/test_freshness_sla_stale_token_ratio.py` — stale token ratio
- `tests/test_feed_sla_epoch_units.py` — epoch units

### Highest-risk behavior
**A tick with a stale but non-None timestamp passes freshness checks if `effective_age` is computed from a field that returns a server-side epoch, not wall-clock-relative age.**  
`quote_age_truth.py` resolves `effective_age_sec` from several candidate fields using fallback order. If `ts_epoch` is set but stale, and `quote_ts` is not set, the tick may show effective_age = 0 if the field resolution order picks a field that is `None`. The `QUOTE_AGE_TIMESTAMP_MISMATCH` detection attempts to catch this, but no test directly injects a candidate with `ts_epoch` set to T-30s and `quote_ts` missing, then asserts `STALE_OPTION_LTP`.

### Gap summary
- No integration test proves that a candidate with a 30-second-old `ts_epoch` and absent `quote_ts` is classified as stale, not fresh.
- No test proves that `exact_option_token_freshness_gate` blocks entry when per-token age exceeds `MAX_OPTION_QUOTE_AGE_SEC` (default 8.0s) and `allowed_for_live_execution=False`.
- No test covers the case where a token has never received a tick (age=None) and proves it produces a hard blocker, not a warning.

---

## Area 4 — Quote Truth and Fallback Handling

### Production files
| File | Role |
|------|------|
| `core/quote_truth.py` | Canonical quote truth decision: source trust, validation status, age, rank/execution eligibility. |
| `core/quote_age_truth.py` | Quote age truth — multi-field timestamp resolution. |
| `core/feed_truth_state.py` | Feed truth state singleton. |
| `core/feed_truth_audit.py` | Feed truth audit module. |
| `core/feed_truth_contract.py` | Feed truth contract definitions. |
| `core/live_fallback_execution_contract.py` | Live fallback execution firewall contract. |
| `core/execution_grade_firewall.py` | Execution grade firewall — blocks fallback/recovered quotes. |
| `core/market_quote_resolver.py` | Market quote resolver entry point. |

### Existing test files
- `tests/test_edge42_quote_truth_contract.py` — quote truth contract
- `tests/test_quote_truth_drift.py` — quote truth drift
- `tests/test_quote_age_truth.py` — quote age truth
- `tests/test_edge41_fallback_execution_firewall.py` — fallback execution firewall
- `tests/test_live_quote_truth_contract_phase2.py` — phase2 live quote truth
- `tests/test_feed_truth_contract.py` — feed truth contract
- `tests/test_feed_truth_audit.py` — (15KB) feed truth audit
- `tests/test_live_dry_run_broker_payload_gate.py` — dry run broker payload gate
- `tests/test_execution_grade_firewall.py` — execution grade firewall
- `tests/test_edge_43_feed_health_truth.py` — feed health truth

### Highest-risk behavior
**A fallback/recovered quote must never become executable.**  
`quote_truth.py` classifies `source_trust = "fallback"` for sources in `FALLBACK_QUOTE_SOURCES`. When `source_trust == "fallback"`, `execution_eligible=False` is returned **only** if `reasons` is non-empty (since `eligibility_ok = truth_ok and source_trust in {"trusted_live", "trusted_cache", "unknown"}`). However, if a fallback source is present but no other reason triggers, `truth_ok=False` is set via `QUOTE_SOURCE_FALLBACK_REASON` in `reasons`, making `eligibility_ok=False`. This appears safe, but the safety depends on `QUOTE_SOURCE_FALLBACK_REASON` always being appended when `source_trust == "fallback"` — which is currently conditional: `if source_trust == "fallback" or validation_status == "REST_FALLBACK"`. There is no explicit test that passes a payload with `quote_source="RECOVERED_FALLBACK"` and asserts `execution_eligible=False` and `rank_eligible=False` simultaneously.

**Second-highest risk:** `_canonical_validation_status` has a silent legacy path: if `existing_status` is empty/None and `current_ltp` is None, it returns `"OK"` (not `"NO_LIVE_OPTION_FEED"`). A candidate with no LTP and no explicit validation status would be classified as OK, not blocked.

### Gap summary
- No test explicitly asserts that `RECOVERED_FALLBACK` source → `execution_eligible=False` (not just `truth_ok=False`).
- No test asserts the silent `current_ltp=None` + `existing_status=None` → `OK` path is actually safe (it is a documentation gap).
- No contract test proves that the execution firewall (`execution_grade_firewall.py`) rejects a candidate where `quote_truth.execution_eligible=False` under all input permutations that include fallback/stale/mismatch states.
- No regression test covers the transition from `RECOVERED_FALLBACK` → `LIVE` as the source re-establishes, proving that the transition from `execution_eligible=False` back to `True` only happens on a confirmed live tick.

---

## Area 5 — Candidate Generation

### Production files
| File | Role |
|------|------|
| `core/candidate_generator.py` | Top-level candidate generator. |
| `core/strategy_candidate_generator.py` | Strategy-specific candidate generator. |
| `core/breakout_candidate_generator.py` | Breakout strategy generator. |
| `core/vwap_candidate_generator.py` | VWAP strategy generator. |
| `core/mean_reversion_candidate_generator.py` | Mean-reversion generator. |
| `core/zero_hero_candidate_generator.py` | Zero-hero (expiry) generator. |
| `core/candidate_normalizer.py` | Candidate normalization and field standarization. |
| `core/candidate_intent.py` | Candidate intent contract. |
| `core/candidate_intent_pool.py` | Candidate intent pool validator. |
| `core/candidate_classifier.py` | Candidate classifier (bucket assignment). |
| `core/candidate_hard_downgrade.py` | Hard downgrade engine. |
| `core/hard_downgrade_engine.py` | Hard downgrade engine (alternate path). |
| `core/candidate_row_classification.py` | Row-level classification. |
| `core/strategy_candidate_classification.py` | Strategy-level classification. |
| `core/strategy_candidate_normalization.py` | Strategy-level normalization. |

### Existing test files
- `tests/test_edge_71_strategy_candidate_generators.py` — strategy generators
- `tests/test_edge_72_breakout_candidate_generator.py` — breakout generator
- `tests/test_edge_73_vwap_candidate_generator.py` — VWAP generator
- `tests/test_edge_74_mean_reversion_candidate_generator.py` — mean reversion
- `tests/test_edge_75_zero_hero_candidate_generator.py` — zero-hero
- `tests/test_candidate_normalizer.py` — normalizer
- `tests/test_edge_69_candidate_intent_contract.py` — intent contract
- `tests/test_edge_70_candidate_intent_pool_validator.py` — intent pool
- `tests/test_edge_71_candidate_classification_layer.py` — classification layer
- `tests/test_candidate_classifier.py` — classifier
- `tests/test_edge_72_hard_downgrade_engine.py` — hard downgrade
- `tests/test_candidate_row_classification.py` — row classification
- `tests/test_edge_70_candidate_normalization_dedup.py` — normalization dedup

### Highest-risk behavior
**A stale-feed candidate must not be generated as `VALIDATED_CANDIDATE`.**  
The feed hold gate (`core/feed_hold_gate.py`) is supposed to block candidate emission when the feed is in a hold state, but the candidate generators themselves do not read the feed state — they receive market context from the orchestrator. If the orchestrator passes stale market context to the generators, candidates are generated against stale data without a visible blocker. This means the generator-level tests with a healthy feed miss the scenario where generators produce candidates from 30-second-old data.

### Gap summary
- No test proves that a breakout generator receiving market context with `allow_stale_quotes=True` produces candidates with `ALLOW_STALE_QUOTES_ACTIVE` in blockers.
- No test proves that a generator receiving `market_open=False` in context produces only advisory candidates (no `VALIDATED_CANDIDATE` status).
- No test proves that the candidate normalizer produces a stable `strategy_id` (deterministic keying) across multiple calls with the same inputs.

---

## Area 6 — Candidate Pool

### Production files
| File | Role |
|------|------|
| `core/candidate_pool.py` | Pool construction, `CandidateLifecycleSnapshot`, deduplication. |
| `core/candidate_pool_orchestrator.py` | Pool orchestrator. |
| `core/candidate_pool_quality.py` | Pool quality analysis (`analyze_candidate_pool`). |
| `core/strategy_candidate_pool.py` | Strategy-layer candidate pool. |
| `core/candidate_finalization.py` | Candidate finalization before scoring. |
| `core/candidate_state_contract.py` | Candidate state contract. |
| `core/candidate_status_contract.py` | Candidate status contract. |
| `core/candidate_readiness_summary.py` | Readiness summary aggregation. |

### Existing test files
- `tests/test_candidate_pool.py` — pool construction and deduplication
- `tests/test_candidate_pool_contract_snapshots.py` — pool contract snapshots
- `tests/test_candidate_pool_orchestrator.py` — orchestrator
- `tests/test_candidate_pool_quality.py` — pool quality
- `tests/test_edge_69_strategy_candidate_pool.py` — strategy candidate pool
- `tests/test_candidate_finalization.py` — finalization
- `tests/test_edge46_candidate_state_contract.py` — state contract
- `tests/test_edge47_candidate_status_contract.py` — status contract
- `tests/test_edge_73_candidate_readiness_summary.py` — readiness summary
- `tests/test_candidate_soft_reject.py` — soft reject
- `tests/test_candidate_exposure.py` — exposure

### Highest-risk behavior
**The advisory/near-executable/executable distinction must be preserved through pool deduplication.**  
`CandidatePool.from_candidates` deduplicates by `(symbol, direction, movement_type, strategy_id)` key. If two candidates with identical keys but different `status` values are submitted, only the first is kept. If the BLOCKED candidate arrives before the VALIDATED candidate, the pool drops the live candidate and retains the blocked one. This depends entirely on the ordering of the input iterable — which is not guaranteed at the orchestrator level.

### Gap summary
- No test proves that deduplication preserves the highest-capability candidate (not just the first-seen).
- No test proves that a pool with mixed statuses (`VALIDATED_CANDIDATE` and `BLOCKED_CANDIDATE` for the same strategy_id) surfaces the correct lifecycle_state.
- No regression test covers the case where the `executable_eligible_count` in the pool summary does not include candidates that have `executable_eligible=True` on their `StrategyCandidate` object but are soft-rejected at the scorer.

---

## Area 7 — Scoring and Ranking

### Production files
| File | Role |
|------|------|
| `core/candidate_scoring.py` | Main scoring engine: `score_candidate()`. |
| `core/candidate_ranking.py` | Ranking engine: `rank_candidates()`. |
| `core/opportunity_scoring.py` | `OpportunityScoreRecord`, `OpportunityScoreReport`. |
| `core/ranking_orchestrator.py` | Ranking orchestrator. |
| `core/opportunity_score.py` | Opportunity score computation. |
| `core/opportunity_scoring.py` | Opportunity scoring module. |
| `core/directional_balance.py` | Directional balance audit. |
| `core/scoring_truth_contract.py` | Scoring truth contract. |
| `core/trade_scoring.py` | Trade-level scoring. |
| `core/execution_first_scoring.py` | Execution-first scoring pass. |

### Existing test files
- `tests/test_candidate_scoring.py` — (23KB) main scoring tests
- `tests/test_candidate_ranking.py` — (12KB) ranking tests
- `tests/test_candidate_ranking_contract_snapshots.py` — ranking contract snapshots
- `tests/test_candidate_ranking_profile_metadata.py` — profile metadata
- `tests/test_ranking_orchestrator.py` — ranking orchestrator
- `tests/test_opportunity_scoring.py` — opportunity scoring
- `tests/test_edge48_scoring_truth_contract.py` — scoring truth contract
- `tests/test_edge_ranking.py` — (13KB) edge ranking cases
- `tests/test_edge_readiness_report.py` — readiness report
- `tests/test_directional_balance.py` — directional balance
- `tests/test_ranked_pipeline_evidence.py` — ranked pipeline evidence
- `tests/test_ranked_pipeline_contract_snapshots.py` — ranked pipeline snapshots
- `tests/test_execution_first_scoring.py` — execution first scoring

### Highest-risk behavior
**Ranking must use real opportunity score, not emitted-row order.**  
`rank_candidates()` sorts by `_sort_key()` which correctly uses `ELIGIBILITY_PRIORITY` first, then safety severity, then `-final_score`. However, the `feed_risk_suppressed` path temporarily overrides `score_eligibility` to `SUPPRESSED_BY_DOWNGRADE` — and `ELIGIBILITY_PRIORITY[SUPPRESSED_BY_DOWNGRADE] = 3`. This means a high-scoring candidate with any `fallback` token in its safety_flags or warnings will be demoted from rank 1 even if its `final_score` exceeds all other non-feed-risk candidates. The key test to prove this is: given a candidate with `final_score=0.95` and `safety_flags=["fallback"]`, assert it is ranked below a candidate with `final_score=0.40` and no feed-risk tokens.

**Second-highest risk:** `_sort_key` secondary sort on `str(record.strategy_id)` can cause ties to resolve by alphabetical strategy name, not by data quality. This makes ranking non-deterministic across score-equal candidates with the same strategy prefix but different symbol.

### Gap summary
- No test proves that a candidate with `safety_flags=["fallback_data"]` is ranked below a lower-scoring but clean candidate.
- No test proves that `feed_risk_suppressed=True` candidates are never emitted as rank-1 in a report where clean candidates exist.
- No test proves that the `SUPPRESSED_BY_DOWNGRADE` bucket cannot be reversed by calling `rank_candidates` twice with the same inputs (idempotency).
- No test covers the alphabetical tie-break behavior of `_sort_key` and asserts it is acceptable.

---

## Area 8 — No-Trade Evidence

### Production files
| File | Role |
|------|------|
| `core/no_trade_engine.py` | `assess_no_trade()` — chop, stale feed, fallback, liquidity, option confirmation, conflict, pool concentration, baseline signals. |
| `core/no_trade_oracle.py` | No-trade oracle (extended/runtime version). |
| `core/runtime_notrade_reason_truth.py` | No-trade reason truth for runtime evidence. |
| `core/candidate_soft_reject.py` | Soft reject engine. |
| `core/blocked_tracker.py` | Blocked candidate tracker. |
| `core/blocker_lifecycle.py` | Blocker lifecycle management. |

### Existing test files
- `tests/test_no_trade_engine.py` — (10KB) no-trade engine
- `tests/test_edge_80_no_trade_oracle.py` — no-trade oracle
- `tests/test_notrade_reason_truth_evidence.py` — (13KB) reason truth evidence
- `tests/test_candidate_soft_reject.py` — soft reject
- `tests/test_strategy_no_qualified_reasons_evidence.py` — (17KB) no-qualified reasons
- `tests/test_blocker_lifecycle.py` — blocker lifecycle
- `tests/test_blocked_tracker_feedback.py` — blocked tracker feedback
- `tests/test_candidate_starvation_trace_evidence.py` — (26KB) starvation trace

### Highest-risk behavior
**`NO_TRADE_FALLBACK_DATA` must fire whenever `ctx.fallback_used=True`, not just when the word "fallback" appears in `quote_source`.**  
In `assess_no_trade()`: `if ctx.fallback_used or "fallback" in str(ctx.quote_source or "").lower()`. The OR condition means either path is sufficient. But `ctx.fallback_used` is a boolean on `StrategyContext` that must be explicitly set; if a caller constructs `StrategyContext` from a dict without setting `fallback_used=True`, only the `quote_source` string check fires. This creates a silent gap where fallback data that is not labeled in the source string bypasses no-trade suppression.

### Gap summary
- No test proves that `assess_no_trade` with `ctx.fallback_used=True` and `ctx.quote_source=None` produces `NO_TRADE_FALLBACK_DATA`.
- No test proves that `NO_TRADE_STALE_FEED` fires when `ctx.option_ltp_age_sec=None` (not just when it exceeds threshold).
- No test proves the chop threshold is non-configurable from config (CHOP_THRESHOLD is a module constant, not from cfg — this is intentional but untested at the boundary).

---

## Area 9 — Risk and Execution Safety

### Production files
| File | Role |
|------|------|
| `core/execution_guard.py` | Main execution gate: market context, regime, confidence, capital, survival gates. |
| `core/risk_engine.py` | Risk engine. |
| `core/risk_decision.py` | Risk decision. |
| `core/risk_state.py` | Risk state. |
| `core/pretrade_risk_engine.py` | Pre-trade risk checks. |
| `core/survival_gates.py` | Survival gates (max loss, drawdown, daily stop). |
| `core/execution_router.py` | Execution router. |
| `core/kill_switch_risk_halt_dry_run_proof.py` | Kill switch dry-run proof. |
| `core/runtime_safety_boot_guard.py` | Safety boot guard (startup safety verification). |
| `core/live_safety.py` | Live mode safety flags. |
| `core/trade_activation.py` | Trade activation gate. |
| `core/trade_permission.py` | Regime-aware trade permission engine. |
| `core/execution_grade_firewall.py` | Execution grade firewall. |

### Existing test files
- `tests/test_execution_guard.py` — (Not present as a dedicated file; covered by test_engine_phase2_adapter.py)
- `tests/test_kill_switch_risk_halt_dry_run_proof.py` — kill switch
- `tests/test_runtime_safety_boot_guard.py` — boot guard
- `tests/test_pretrade_risk_engine.py` — pretrade risk
- `tests/test_risk_decision.py` — risk decision
- `tests/test_risk_engine_offline.py` — risk engine offline
- `tests/test_survival_gates.py` — survival gates
- `tests/test_execution_grade_firewall.py` — firewall
- `tests/test_live_enablement_gate.py` — live enablement gate
- `tests/test_broker_reconciliation_dry_run_proof.py` — broker dry run
- `tests/test_execution_readiness_guard.py` — readiness guard
- `tests/test_trade_permission.py` — trade permission
- `tests/test_no_order_bypass_static.py` — static order bypass check

### Highest-risk behavior
**`LIVE` mode + `LIVE_TRADING_ENABLED=false` (env var) must produce `allowed=False` unconditionally, even when `MANUAL_APPROVAL=True` and approval exists.**  
In `must_have_valid_approval()` (called by `ExecutionGuard`), the `LIVE_TRADING_ENABLED` env check fires first for LIVE mode: `if os.getenv("LIVE_TRADING_ENABLED", "false").lower() != "true": return False`. This is correct. But `ExecutionGuard.evaluate()` does not call `must_have_valid_approval()` directly — it is called by the caller of `ExecutionGuard`, not inside `evaluate()`. The guard itself checks `market_ctx.planning_only` and the `execution_allowed` flag on the trade object. If a trade is incorrectly marked `execution_allowed=True` (e.g., by a bug in the orchestrator), the `ExecutionGuard` may allow it through without checking LIVE_TRADING_ENABLED. This path is not tested with an explicit orchestrator-level injection of `execution_allowed=True` in LIVE mode with the env var set to false.

**Second-highest risk:** Survival gates are tested offline but not in integration with the `ExecutionGuard.evaluate()` flow where both `survival_decision.allowed_entries=False` and `trade.confidence < min_conf` are true — the test should confirm that the survival gate block fires first (not confidence).

### Gap summary
- No test proves that `ExecutionGuard.evaluate()` returns `allowed=False` in LIVE mode when `LIVE_TRADING_ENABLED=false` is set at the orchestrator boundary (not just at the approval store level).
- No test proves that `survival_gates.evaluate()` block takes priority over confidence block in `ExecutionGuard`.
- No destruction test proves that calling `ExecutionGuard.evaluate()` 1,000 times in SIM mode with valid confidence never leaks an `allowed=True` in LIVE mode.

---

## Area 10 — Manual Approval and Live-Order Suppression

### Production files
| File | Role |
|------|------|
| `core/approval_store.py` | Approval store: SQLite-backed PENDING/APPROVED/REJECTED/EXPIRED/USED state machine with atomic `consume_valid_approval`. |
| `core/agent_approval.py` | Agent approval wrapper. |
| `core/config_approval.py` | Config approval. |
| `core/execution_guard.py` | Calls `must_have_valid_approval()` for PAPER/LIVE modes. |
| `core/governance_gate.py` | Governance gate. |
| `core/governance.py` | Governance engine. |
| `core/decision_authority.py` | Decision authority. |
| `core/live_dry_run_broker_payload_gate.py` | Live dry-run broker payload gate. |

### Existing test files
- `tests/test_manual_approval_enforcement.py` — (11KB) manual approval enforcement
- `tests/test_manual_approval_invariant.py` — invariant checks
- `tests/test_manual_approval_sample_run.py` — sample run
- `tests/test_order_approval_store.py` — approval store
- `tests/test_agent_approval.py` — agent approval
- `tests/test_approval_binding.py` — approval binding
- `tests/test_governance_gate.py` — governance gate
- `tests/test_decision_authority.py` — decision authority
- `tests/test_live_dry_run_broker_payload_gate.py` — dry run gate
- `tests/test_live_enablement_gate.py` — live enablement gate
- `tests/test_human_override_audit.py` — human override audit

### Highest-risk behavior
**An EXPIRED approval must never be consumed.**  
`consume_valid_approval()` uses an atomic `BEGIN IMMEDIATE` + `SELECT … FOR UPDATE` pattern in SQLite. If two threads call it simultaneously with the same `order_intent_hash`, one gets `approval_used` rejection. This is correct. However, the EXPIRED transition happens in the same transaction as a failed consume — if the database is locked and the connection times out (`timeout=1.0`), the row may not be marked EXPIRED, and a future caller could attempt to consume it after the wall-clock expiry but before the DB row is updated. This represents a TOCTOU window.

**Second-highest risk:** `require_armed=True` for LIVE mode means the approval must both be APPROVED and armed (within `arm_ttl`). However, `_requires_armed_approval()` defaults to `True` for LIVE but `False` for PAPER via env var or config. If someone sets `PAPER_REQUIRE_ARMED_APPROVAL=true` without also setting the arm TTL, the arm window defaults to 60 seconds from the env var `ORDER_ARM_TTL_SEC`. This could block paper approvals silently if the arm window expires before the order cycle fires.

### Gap summary
- No test proves that a concurrent `consume_valid_approval` for the same hash results in exactly one success and one `approval_used` rejection (thread safety proof).
- No test proves that an EXPIRED row (by wall clock) that has not been marked EXPIRED in the DB cannot be consumed.
- No test proves that `must_have_valid_approval()` returns `False` with reason `live_trading_env_disabled` when `LIVE_TRADING_ENABLED=false` even if an APPROVED record exists.
- No test proves that the armed window for LIVE mode is enforced independently of the approval TTL.

---

## Area 11 — Orchestrator Integration

### Production files
| File | Role |
|------|------|
| `core/orchestrator.py` | Main orchestrator (419KB). Coordinates market data, feed state, candidate pipeline, scoring, ranking, selection, and evidence writing. |
| `core/orchestrator_parts/` | Orchestrator parts (modular decomposition). |
| `core/paper_decision_orchestrator.py` | Paper decision orchestrator. |
| `core/agent_orchestrator.py` | Agent orchestrator. |
| `core/ranking_orchestrator.py` | Ranking orchestrator. |
| `core/candidate_pool_orchestrator.py` | Candidate pool orchestrator. |
| `core/runtime_candidate_flow_trace.py` | Candidate flow trace within orchestrator. |
| `core/runtime_candidate_handoff.py` | Candidate handoff from pipeline to execution. |
| `core/feed_readiness_for_candidates.py` | Feed readiness check before candidates are produced. |
| `core/orchestrator_startup_probe.py` | Startup probe. |

### Existing test files
- `tests/test_orchestrator_decision_event.py` — (15KB) decision event
- `tests/test_orchestrator_strategy_gate_once.py` — (24KB) strategy gate
- `tests/test_orchestrator_status_files.py` — (18KB) status files
- `tests/test_orchestrator_pro_shadow.py` — (15KB) pro shadow
- `tests/test_orchestrator_startup_probe.py` — (10KB) startup probe
- `tests/test_orchestrator_contract_queue_gate.py` — (10KB) contract queue gate
- `tests/test_orchestrator_pilot_feed_ok.py` — pilot feed
- `tests/test_orchestrator_pilot_unlock.py` — pilot unlock
- `tests/test_orchestrator_decision_safe.py` — decision safe
- `tests/test_orchestrator_latency_accounting.py` — latency accounting
- `tests/test_orchestrator_slo_failover_runtime_clear.py` — SLO failover
- `tests/test_orchestrator_allocator_seed.py` — allocator seed
- `tests/test_main_startup_audit.py` — (19KB) main startup audit

### Highest-risk behavior
**The orchestrator must not produce executable candidates when `feed_readiness_for_candidates` returns `HOLD`.**  
`feed_readiness_for_candidates.py` emits a hold status that is read at the beginning of each orchestrator cycle. If the hold status check runs before a slow-path feed state refresh, there is a window where the orchestrator emits candidates under an outdated feed state. No test currently simulates the orchestrator cycle running twice: first pass (feed OK, candidates generated), then second pass (feed enters HOLD mid-cycle) and asserts the second pass output is empty.

### Gap summary
- No test proves that the orchestrator's candidate pipeline is empty when `feed_readiness_for_candidates` returns `HOLD`.
- No integration test proves end-to-end: feed health → freshness gate → hold gate → no candidate emission → no-trade evidence produced.
- No test proves that the orchestrator properly resets stale candidates after a feed reconnect (old ranked candidates should not persist into the next cycle after reconnect).

---

## Area 12 — Dashboard / Runtime Artifact Contracts

### Production files
| File | Role |
|------|------|
| `core/runtime_snapshot_producer.py` | Produces runtime snapshots written to disk. |
| `core/runtime_snapshot_store.py` | Runtime snapshot store. |
| `core/latest_artifact_freshness_guard.py` | Guards artifact freshness (alert if snapshot is stale). |
| `core/live_truth_latest_artifact_preservation.py` | Artifact preservation (non-empty on close). |
| `core/runtime_execution_truth.py` | Runtime execution truth (21KB). |
| `core/runtime_truth_breakdown.py` | Runtime truth breakdown report. |
| `core/candidate_executability_evidence.py` | Candidate executability evidence artifact (30KB). |
| `core/top_opportunity_executable_truth.py` | Top opportunity executable truth artifact. |
| `dashboard/` | Dashboard Streamlit app reading runtime snapshots (read-only). |

### Existing test files
- `tests/test_edge50_latest_artifact_freshness_guard.py` — artifact freshness guard
- `tests/test_edge51_runtime_snapshot_freshness_wiring.py` — snapshot freshness wiring
- `tests/test_edge52_dashboard_snapshot_freshness_visibility.py` — dashboard visibility
- `tests/test_live_truth_02_latest_artifact_preservation.py` — artifact preservation
- `tests/test_live_truth_03_runtime_snapshot_freshness.py` — snapshot freshness
- `tests/test_dashboard_snapshot_readers.py` — snapshot readers
- `tests/test_dashboard_reads_snapshot_only.py` — dashboard reads snapshot only
- `tests/test_runtime_evidence_capture_guard.py` — evidence capture guard
- `tests/test_runtime_execution_truth_evidence.py` — (19KB) execution truth evidence
- `tests/test_candidate_executability_evidence.py` — (12KB) executability evidence

### Highest-risk behavior
**The dashboard must never read execution state directly from the order engine — only from the runtime snapshot.**  
`test_dashboard_reads_snapshot_only.py` exists, but it is a lightweight import/mock test. No test proves that all code paths in the dashboard modules that display trade status, approval state, or candidacy read exclusively from snapshot files and do not import or call `core.execution_engine`, `core.execution_router`, `core.approval_store`, or `core.kite_client` directly.

### Gap summary
- No test asserts that snapshot artifacts are never empty (non-zero byte) at market open.
- No test proves that the artifact freshness guard fires within 60 seconds of a stale snapshot.
- No static analysis test proves that dashboard modules do not directly import execution/order modules.

---

## Audit Sign-Off

| Criterion | Status |
|-----------|--------|
| Production code read | ✅ Read-only |
| Test code read | ✅ Read-only |
| Production code modified | ❌ Not modified |
| Test code modified | ❌ Not modified |
| New tests written | ❌ Not written (see test-matrix doc) |
| Strategy thresholds changed | ❌ Not changed |
| Broker APIs called | ❌ Not called |
| Live mode touched | ❌ Not touched |

**Next step:** Review `docs/qa/elite-test-matrix-20260610.md` for exact proposed tests and `docs/qa/qa-coverage-gaps-20260610.md` for prioritized gap list.
