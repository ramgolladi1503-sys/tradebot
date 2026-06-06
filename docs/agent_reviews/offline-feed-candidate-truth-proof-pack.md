# Offline Feed/Candidate Truth Proof Pack

mode: REVIEW
candidate_id: PR-OFFLINE-FEED-CANDIDATE-TRUTH-PROOF-PACK
decision: add_offline_feed_candidate_truth_proof_pack
reason: Add a deterministic offline proof pack that demonstrates the truth chain from FeedTruth through runtime execution truth, candidate classification, Phase2 evidence, and final emit eligibility without changing runtime behavior.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/offline-feed-candidate-truth-proof-pack.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (offline proof-pack evidence-only diagnostics + deterministic regression tests + review doc)
title: Offline Feed/Candidate Truth Proof Pack
scope: add a deterministic offline proof pack that proves FeedTruth, execution truth, candidate classification, Phase2 evidence, and final emit remain coherent without changing live runtime behavior
requested_paths:
  - scripts/run_offline_feed_candidate_truth_proof_pack.py
  - tests/test_offline_feed_candidate_truth_proof_pack.py
  - docs/agent_reviews/offline-feed-candidate-truth-proof-pack.md
allowed_paths:
  - scripts/run_offline_feed_candidate_truth_proof_pack.py
  - tests/test_offline_feed_candidate_truth_proof_pack.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/engine_phase2_adapter.py
  - core/runtime_phase2_rejection_evidence.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
  - live websocket startup code
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_offline_feed_candidate_truth_proof_pack.py -vv
  - PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py tests/test_review_queue_decision_engine.py tests/test_phase2_rejection_evidence_artifact.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr496_changed_paths_pr_only.txt
acceptance_proof:
  - healthy executable scenarios pass
  - feed dead and WS1006 terminal scenarios fail closed
  - stale option LTP blocks final emit
  - missing context scenarios stay blocked
  - advisory or fallback rows stay non-executable
  - Phase2 no input remains distinct from input dropped and accepted
  - snapshot mirror scenarios stay coherent
  - the pack writes only explicit output files and no runtime artifacts
```

## Scope Guard

- This PR is offline and evidence-only.
- It must not alter runtime websocket behavior, broker calls, order behavior, strategy logic, ranking, or Phase2 decisions.
- It must fail closed and preserve current truth-contract behavior.

## Grill Me Review

- The proof pack must not create fake confidence by only testing shape.
- It must prove both pass and fail paths with deterministic truth builders.
- It must keep blocked states blocked and executable states executable.

## Hermes Review

- The script is the right boundary because it assembles existing truth builders into one deterministic offline proof pack.
- The new tests should verify the output contract, not live runtime behavior.
- The pack should stay isolated from broker, websocket, and strategy code paths.

## GSD Review

- Changes are limited to one offline script, one focused test file, and one review doc.
- The proof pack is deterministic and read-only.
- The output contract is explicit and auditable.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`
- No live orders.
- No websocket startup.
- No broker calls.

## Evidence

- The proof pack exercises healthy, blocked, advisory, no-input, input-dropped, accepted, and WS1006 terminal scenarios.
- The proof pack writes a JSON artifact and a Markdown summary to the explicit output directory only.
- The proof pack is deterministic and does not depend on live market data.

## Root Cause

- Prior evidence existed across several separate truth layers, but there was no single offline artifact tying FeedTruth, execution truth, candidate classification, Phase2 evidence, and final emit eligibility together.
- This proof pack closes that gap without altering runtime behavior.

## Fix

- Add a deterministic offline proof pack script.
- Add regression tests covering the proof scenarios and output contract.
- Add an evidence doc that clearly states the offline, read-only, fail-closed scope.

## Acceptance Proof

- Healthy executable scenarios pass.
- Feed dead and WS1006 terminal scenarios fail closed.
- Stale option LTP blocks final emit.
- Missing context remains blocked.
- Advisory and fallback rows remain non-executable.
- Phase2 no input, input dropped, and accepted remain distinguishable.
- Snapshot mirrors remain coherent.
- The proof pack emits only explicit output artifacts.

## Safety Constraints

- No broker/order changes.
- No live orders.
- No live mode.
- No websocket start.
- No strategy changes.
- No ranking or scoring formula changes.
- No Phase2 decision changes.
- No dashboard/UI changes.
- No stale-feed relaxation.
- No risk gate relaxation.
- No fallback promotion.
- No making blocked candidates executable.
- No broad refactor.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_offline_feed_candidate_truth_proof_pack.py -vv`
- `PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py tests/test_review_queue_decision_engine.py tests/test_phase2_rejection_evidence_artifact.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv`
- `PYTHONPATH=. python scripts/run_offline_feed_candidate_truth_proof_pack.py --out-dir /tmp/feedtruth_proof_pack`

## What Was Not Changed

- Feed runtime lifecycle behavior.
- Runtime websocket recovery behavior.
- Execution-truth decision rules.
- Phase2 filtering behavior.
- Strategy formulas.
- Ranking or scoring math.
- Broker/order logic.
- Dashboard/UI logic.

## Remaining Risks

- The proof pack is synthetic and offline; it proves contract coherence, not live market performance.
- Future schema changes in feed, execution, or candidate payloads may require updates to the proof pack.

## Next Market Validation Signals

- `RAW_CANDIDATE_COUNT`
- `POST_REAL_FILTER_COUNT`
- `POST_EXECUTABLE_FILTER_COUNT`
- `TB_RANKED_COUNT_EXECUTABLE`
- `TB_TOP_EXECUTABLE_CANDIDATE`
- `TB_TOP_BLOCKED_CANDIDATE`
- `FINAL_EMIT_ABORT`
- `FEED_WS_PROCESS_RESTART_REQUIRED`
- `RECOVERY_BLOCKED`
- `STALE_OPTION_LTP`
- `PHASE2: No input candidates`
- `PHASE2: No valid candidates after filtering`

## Runtime Proof Required After Merge

- Run the offline proof pack CLI against a temporary output directory.
- Confirm the JSON and Markdown summaries are written.
- Confirm the pass/fail summary is deterministic.
- Confirm no runtime artifacts are written outside the explicit output path.

## What This PR Does Not Prove

- It does not prove strategy edge or profitability.
- It does not prove live feed health.
- It does not prove broker readiness.
- It does not prove order execution safety beyond the read-only truth contract.

## Human Approval

Human approval is required before merge. Confirm the offline proof pack is deterministic and the validation suite is green.
