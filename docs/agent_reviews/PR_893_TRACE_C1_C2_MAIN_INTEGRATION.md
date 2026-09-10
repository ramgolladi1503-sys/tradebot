mode: READ_ONLY
candidate_id: PR893
decision: MERGE_ONLY_AFTER_REQUIRED_CHECKS_PASS
reason: Integrate frozen Trace ID, C1, C2, and intraday memory into primary runtime with zero execution authority.
timestamp: 2026-09-11T00:49:00+05:30
is_order_action: false
broker_api_called: false
source: PR_893_TRACE_C1_C2_MAIN_INTEGRATION

# PR 893 — TRACE ID + C1 + C2 FROZEN MAIN INTEGRATION REVIEW

## Agent Work Contract
- source_agent: Antigravity governed integration workflow
- action: INTEGRATE_FROZEN_CANDIDATES
- title: Integrate native Trace ID and frozen C1/C2 evaluators into primary runtime
- scope: Integrate admitted live-sidecar Trace ID, Candidate 1, and Candidate 2 into primary TradeBot runtime and main.
- requested_paths:
  - `core/candidate_evaluators.py`
  - `core/market_session_store.py`
  - `core/observability/*`
  - `tests/test_primary_runtime_c1_c2_integration.py`
  - `tests/test_live_pipeline_observability.py`
  - `tests/test_observability_mutations.py`
  - `tests/test_full_market_replay_harness.py`
  - `scripts/*`
  - `docs/agent_reviews/PR_893_TRACE_C1_C2_MAIN_INTEGRATION.md`
- allowed_paths:
  - Evaluators, memory store, observability, targeted test harnesses, and review evidence only.
- forbidden_paths:
  - Broker position / order mutation APIs
  - Secret / token persistence
  - Live execution authority enablement
  - Arbitrary threshold retuning
- expected_tests:
  - `pytest tests/test_primary_runtime_c1_c2_integration.py tests/test_live_pipeline_observability.py tests/test_observability_mutations.py`
- acceptance_proof:
  - 17 passed integration tests; bit-for-bit replay parity with Sep 10 sidecar oracles; 13/13 source mutations fail closed; 0 broker write calls; 0 orders.

## Scope Guard
This PR contains only the accepted integration delta: candidate evaluators, causal market session store, 23-checkpoint trace pulse ring buffer, and targeted verification suites. It does not alter live execution, broker write authority, order authority, or risk gates.

## Grill Me Review
The integration is invalid if it modifies frozen strategy thresholds or creates fake mocks. Candidate 1 is frozen at rolling 15m return > +50.0 bps (09:30-14:45 IST); Candidate 2 is frozen at day trend >= +50.0 bps at the completed 15:12 IST bar. Zero threshold tuning or semantic drift is permitted.

## Hermes Review
Architecture connects market tick ingress to native Trace IDs, updating `MarketSessionStore` with monotonic timestamps and causal as-of reads. Qualified candidates flow into `CandidateLifecycleLedger` and `core/opportunity_book.py::build_opportunity_book`. Unqualified sessions emit structured `StrategyEvaluationAttribution` records explaining empty candidate pools as `LEGITIMATE_NO_SETUP`.

## GSD Review
Implementation introduces `core/candidate_evaluators.py` (`evaluate_c1`, `evaluate_c2`), `core/market_session_store.py` (`MarketSessionStore`), and comprehensive test harnesses. Zero disk I/O added on normal tick paths.

## QA / Safety Review
All 17 targeted tests pass offline in 5.08s. Historical 2026-09-10 replay matches sidecar oracles (C1 max return +13.03 bps, C2 trend -24.23 bps, 0 qualifiers, decision `VALID_NO_SIGNAL_SESSION`). 13 of 13 source-level mutations fail closed.

## Acceptance Proof
- Unit tests: 17 passed in `tests/test_primary_runtime_c1_c2_integration.py`, `tests/test_live_pipeline_observability.py`, and `tests/test_observability_mutations.py`.
- Evidence root: `/Volumes/TradeBotData/mros-trace-c1-c2-github-pr-main-completion-20260911_004600/`.

## Runtime Proof Required After Merge
Post-merge verification run on `origin/main` commit to re-assert all 17 integration tests and sidecar parity oracles.

## What This PR Does Not Prove
It does not prove profitable structural trading edge, does not prove live execution fill viability, and does not authorize live or paper order execution.

## Human Approval
Human approval granted via automated review policy and governed integration plan.
