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

## Problem

Prior patches made the feed runtime snapshot, execution-truth normalization, stale-option mutation guard, and Phase2 evidence more explicit. What was still missing was a deterministic offline proof that ties those layers together without live connectivity.

## Evidence

- The proof pack is read-only and fixture-free.
- It uses pure truth builders and deterministic synthetic scenarios.
- It does not call broker APIs, start websocket sessions, or mutate runtime state.
- It preserves the current behavior of healthy executable candidates and keeps blocked or advisory rows non-executable.

## Proof Scenarios

1. Healthy executable candidate.
2. FeedTruth DEAD / RECOVERY_BLOCKED.
3. STALE_OPTION_LTP.
4. Missing live timing, spread, liquidity, and unknown quote source context.
5. Advisory / queue-only / synthetic / fallback rows.
6. Phase2 no input.
7. Phase2 input dropped.
8. Phase2 accepted path.
9. Snapshot mirror truth consistency.
10. WS1006 terminal state.

Each scenario records:

- scenario name
- input truth state
- expected result
- actual result
- executable allowed
- reportable executable
- Phase2 input state
- Phase2 drop counts
- final emit allowed
- blockers
- pass/fail

## Safety Constraints

- No broker/order changes.
- No live orders.
- No live mode.
- No websocket start.
- No strategy changes.
- No ranking or scoring formula changes.
- No Phase2 decision behavior changes.
- No dashboard/UI changes.
- No stale-feed relaxation.
- No risk gate relaxation.
- No fallback promotion.
- No making blocked candidates executable.
- Evidence failures do not crash runtime.
- The pack stays read-only with `append=false`.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_offline_feed_candidate_truth_proof_pack.py -vv`
- `PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py tests/test_review_queue_decision_engine.py tests/test_phase2_rejection_evidence_artifact.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv`

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
- Future schema changes in candidate or feed-truth payloads may require proof-pack updates.

## Next Market Validation Signals

After merge and the next open market session, verify:

- FEED_REBALANCE_SKIPPED
- mutation_skipped_symbols
- mutation_skip_reason_by_symbol
- WS1006 / RECOVERY_BLOCKED
- forbidden retry behavior
- RAW_CANDIDATE_COUNT
- POST_REAL_FILTER_COUNT
- POST_EXECUTABLE_FILTER_COUNT
- Phase2 input states
- Phase2 drop categories
- TB_RANKED_COUNT_EXECUTABLE
- FINAL_EMIT_ABORT / final emit eligibility
- recovered_fallback / stale_option_ltp / missing context blockers

## Runtime Proof Required After Merge

- Run the offline proof pack CLI against a tmp output directory.
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
