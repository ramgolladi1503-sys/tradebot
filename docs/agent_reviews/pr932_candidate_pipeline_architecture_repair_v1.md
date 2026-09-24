# PR #932 Candidate Pipeline Architecture Repair — Agent Review Evidence

mode: PAPER
candidate_id: PR932_CANDIDATE_PIPELINE_ARCHITECTURE_REPAIR
decision: REVIEW_PASS_READ_ONLY_REPAIR
reason: Strategy qualification cleanly separated from execution eligibility with full telemetry conservation and truth adherence.
timestamp: 2026-09-24T03:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr932_candidate_pipeline_architecture_repair_v1.md

## Agent Work Contract

- **source_agent**: Hermes -> GSD
- **action**: PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
- **title**: Candidate pipeline architecture repair and truth reconciliation
- **scope**: Separate strategy qualification from execution eligibility across the 12-hop causal pipeline; remove fake pricing fallbacks; enforce strict observation logging.
- **requested_paths**:
  - `core/causal_strategy_harness.py`
  - `tools/code_excellence/cerberus_gate.py`
  - `tests/test_candidate_pipeline_architecture_repair.py`
  - `docs/agent_reviews/pr932_candidate_pipeline_architecture_repair_v1.md`
- **allowed_paths**:
  - `core/causal_strategy_harness.py`
  - `tools/code_excellence/cerberus_gate.py`
  - `tests/test_candidate_pipeline_architecture_repair.py`
  - `tests/test_causal_strategy_and_truth.py`
  - `docs/agent_reviews/pr932_candidate_pipeline_architecture_repair_v1.md`
  - `docs/candidate_pipeline_architecture_repair_v1_20260923T074715Z/**`
  - `docs/pr932_candidate_pipeline_repair_v2_20260923_203938/**`
- **forbidden_paths**:
  - `core/broker*`
  - `core/order*`
  - `core/execution*`
  - `config/**`
  - `.env`
  - `main.py`
  - `run_live.sh`
- **expected_tests**: 15 passing unit and integration tests across candidate pipeline repair and causal strategy truth.
- **acceptance_proof**: Clean test execution, 100% kill rate on 5-mutation suite, deterministic replay against 2026-09-23 live market data, unified CE gates passing.

## Scope Guard

The changes are strictly scoped to analytical strategy qualification and candidate admission semantics in `core/causal_strategy_harness.py`, type-annotated non-action field matching in `tools/code_excellence/cerberus_gate.py`, accompanying test suites, and documentation. No broker adapters, execution routers, order engines, live credentials, or live order policies were touched.

## Grill Me Review

- **Does separating qualification from execution eligibility risk phantom trades?**
  No. Execution eligibility is evaluated as a separate strict boolean gate requiring healthy feeds (`feed_ok=True` and `feed_age <= 2.5s`). Candidates with stale quotes remain in `candidate_pool.jsonl` tagged as `QUALIFIED_EXECUTION_BLOCKED` and are strictly excluded from `executable_candidates`.
- **Do missing prices fabricate synthetic default values?**
  No. Arbitrary numeric fallbacks (such as 100.0) were eliminated. Unpriced fields strictly preserve `None` adhering to Truth Law.
- **Can out-of-universe assets leak into candidates?**
  No. Out-of-universe symbols are strictly marked `INAPPLICABLE` and emit zero candidates, conforming with strategy registry authority.

## Hermes Review

The candidate pipeline architecture establishes an explicit distinction:
1. **Strategy Qualification**: An intrinsic property of completed market information (e.g. 5-minute bars or session return milestones).
2. **Execution Eligibility**: An extrinsic runtime state governed by live tick freshness, orderbook spread, and risk readiness.

Ledgers flow deterministically:
`native_pulse_stream.jsonl` -> `strategy_observations.jsonl` -> `candidate_pool.jsonl` -> `executable_pool.jsonl` -> `candidate_decisions.jsonl` -> `trade_truth_stream.jsonl`.

## GSD Review

Implementation details:
- Implemented `StrategyObservation` and three-tier observation logging.
- Preserved `None` for unpriced candidate fields.
- Fixed dataclass type-annotated field recognition in `tools/code_excellence/cerberus_gate.py`.
- Replaced whitespace irregularities across documentation files.
- Executed full 2026-09-23 market replay with zero fake passes.

## QA / Safety Review

- `read_only = true`
- `is_order_action = false`
- `broker_api_called = false`
- `allowed_for_live_execution = false`
- `orders_placed = 0`
- `orders_modified = 0`
- `orders_cancelled = 0`
- `broker_write_authority = false`
- `order_authority = false`

## High-Risk Path Review

No high-risk paths (`config/`, `core/auth.py`, `core/kite_depth_ws.py`, `core/orchestrator.py`, `core/execution/`, `core/risk`, `strategies/`) were modified.
All changes reside in causal evaluation harness, CI gate tooling, test suites, and audit documentation.

## Acceptance Proof

1. **Unit & Integration Tests**: 15/15 passing (`tests/test_candidate_pipeline_architecture_repair.py`, `tests/test_causal_strategy_and_truth.py`).
2. **Cerberus & Unified CE Gates**: Exit code 0, 0 blocks across 42 changed paths.
3. **Mutation Suite**: 5/5 targeted safety mutations killed (100% kill rate).
4. **Market Replay**: 2026-09-23 real parquet capture verified. CAS Morning Reversal triggered at 10:00:00 IST (+12.05 bps return, SELL/PE advisory) cleanly without synthetic fallbacks.
5. **Clean Whitespace Diff**: `git diff --check origin/main` passes with 0 errors.

## Runtime Proof Required After Merge

Validation during subsequent paper observation run:
- Confirm `strategy_observations.jsonl` logs every symbol evaluated.
- Confirm candidates with stale quotes are tagged `QUALIFIED_EXECUTION_BLOCKED` and not routed to broker.

## What This PR Does Not Prove

- This PR does not prove live execution profitability or alpha edge.
- This PR does not claim real broker order fills.
- This PR does not alter live execution risk limits.

## Human Approval

Human review and approval required before merging PR #932 into `main`.
