# PR 651 - Canonical Regime Session-Context Propagation

mode: PAPER
candidate_id: pr651-canonical-regime-session-context-propagation
decision: REVIEW_ONLY
reason: propagate canonical session context from event timestamps through regime, market-data, decision, gate-status, and orchestrator paths without changing strategy thresholds or execution behavior.
timestamp: 2026-07-13T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr651_agent_review.md

## Agent Work Contract

```text
source_agent: Codex (GPT-5)
action: GENERATE_PATCH
title: Fix canonical regime session-context propagation
scope: propagate canonical timestamp-derived session context through market-data, regime probability, decision DAG, gate-status logging, and orchestrator consumers; add regression tests and evidence docs; do not change thresholds, coefficients, strategy eligibility, risk rules, broker/order behavior, or live execution behavior
requested_paths:
  - core/regime_session_context.py
  - core/regime_prob_model.py
  - core/market_data.py
  - core/decision_dag.py
  - core/gate_status_log.py
  - core/orchestrator.py
  - tests/test_market_data_warm_seed.py
  - tests/test_entropy.py
  - tests/test_gate_status_log.py
  - tests/test_breakout_entropy_override.py
  - docs/research/regime_session_fix_shared_failure_classification.md
  - docs/agent_reviews/pr651_agent_review.md
allowed_paths:
  - core/regime_session_context.py
  - core/regime_prob_model.py
  - core/market_data.py
  - core/decision_dag.py
  - core/gate_status_log.py
  - core/orchestrator.py
  - tests/test_market_data_warm_seed.py
  - tests/test_entropy.py
  - tests/test_gate_status_log.py
  - tests/test_breakout_entropy_override.py
  - docs/research/*
  - docs/agent_reviews/*
forbidden_paths:
  - strategies/*
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - python3 -m pytest -q tests/test_market_data_warm_seed.py tests/test_entropy.py tests/test_gate_status_log.py tests/test_breakout_entropy_override.py
  - python3 -m pytest -q tests/test_decision_dag.py tests/test_entropy_contract.py
  - python scripts/validate_agent_review_evidence.py
acceptance_proof:
  - canonical session bucket is derived from market-event timestamp rather than defaulting silently to DEFAULT
  - timestamp-derived session context propagates to all listed runtime consumers
  - replay evidence preserves genuine high-entropy decisions while removing propagation-caused false blocks
  - no thresholds, coefficients, or execution behavior changed
```

## Scope Guard

In scope:

- Canonical session-context derivation from event timestamps.
- Propagation through regime model, market-data consumers, decision DAG, gate-status logging, and orchestrator paths.
- Regression coverage for session-bucket boundaries and propagation.
- Evidence-only documentation for the fix and shared blocker classification.

Out of scope:

- No entropy threshold changes.
- No regime coefficient changes.
- No strategy eligibility changes.
- No broker/order changes.
- No live execution behavior changes.
- No fix for shared CI blockers unrelated to this branch.

Boundary verification:

- [x] No broker code changed.
- [x] No order code changed.
- [x] No execution code changed.
- [x] No strategy files changed.
- [x] No threshold changes.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk files touched by this PR:

- `core/market_data.py`
- `core/orchestrator.py`

Why this is high-risk:

- These are runtime paths that influence session classification and downstream gating.
- Silent fallback to `DEFAULT` was the failure mode being corrected.

Safety constraints preserved:

- Session context is derived from event time, not from an implicit default.
- The propagation is read-only with respect to thresholds, coefficients, and strategy logic.
- No broker or order actions are introduced.
- No live behavior is enabled.

## Grill Me Review

Verdict: PASS

Main risk:

- A partial propagation fix could leave one consumer on `DEFAULT` while others use canonical session buckets, recreating silent divergence.

What was checked:

- Regime model, market-data, decision DAG, gate-status log, and orchestrator consumers were all updated to accept canonical session context.
- Replay evidence showed the branch removes the propagation-caused false blocks without changing the legitimate high-entropy set.

What this does not prove:

- It does not prove the entropy model itself is optimal.
- It does not prove the shared CI blockers are fixed.

## Hermes Review

Verdict: PASS

Architecture notes:

- Canonical session resolution is separated into a dedicated module.
- Runtime consumers receive the same timestamp-derived session context instead of recomputing ad hoc defaults.
- The design is conservative and fail-closed relative to the previous silent fallback.

## GSD Review

Verdict: PASS

Delivery notes:

- The PR stays scoped to session-context derivation and propagation.
- Regression tests and evidence docs are included.
- Shared blockers were classified separately instead of being mixed into the fix.

## QA / Safety Review

Safety properties preserved:

- `is_order_action=false`
- `broker_api_called=false`
- no risk gate weakening
- no threshold or coefficient edits
- no broker/order/runtime execution changes

Validation evidence:

- Focused regression suites passed locally.
- The replay evidence preserved `1,050` genuine high-entropy decisions while reducing incorrect `DEFAULT` usage to `0`.
- Branch-only regressions were not introduced relative to `origin/main`.

## Acceptance Proof

Observed validation:

- `4,214 -> 0` events incorrectly using `DEFAULT`
- `168 -> 0` false high-entropy decisions
- `0` false passes introduced
- `0` consumer entropy divergences
- `1,050` genuine high-entropy decisions preserved

Commands used:

```bash
python3 -m pytest -q tests/test_market_data_warm_seed.py tests/test_entropy.py tests/test_gate_status_log.py tests/test_breakout_entropy_override.py
python3 -m pytest -q tests/test_decision_dag.py tests/test_entropy_contract.py
python scripts/validate_agent_review_evidence.py
git diff --check
```

## Runtime Proof Required After Merge

Required after merge:

- Replay the same July 9 captured dataset through the production path.
- Confirm `DEFAULT` session usage remains `0`.
- Confirm no new consumer divergence appears at runtime.
- Confirm the fix remains regression-clean relative to `origin/main`.

## What This PR Does Not Prove

This PR does not prove:

- the entropy model is calibrated for profitability
- the strategy is production-optimal
- the shared CI blockers are branch-specific
- live execution behavior changed
- broker behavior changed

## Human Approval

Human approval required before merge.

This PR must stay limited to canonical session-context propagation and documentation of the shared blockers. Do not mix in fixes for `libomp.dylib`, hardcoded `python` subprocess calls, or the pre-existing orchestrator report failure.
