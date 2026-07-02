# PR Agent Review: Serialize truth_quality with runtime and artifact safety enforcement

## Agent Work Contract
- source_agent: Antigravity
- action: GENERATE_PATCH
- title: Serialize truth_quality with runtime and artifact safety enforcement
- scope: Serialization and truth-safety invariant enforcement for advisory rows.
- requested_paths: `core/review_queue.py`, `core/trade_schema.py`, `core/advisory_schema.py`
- allowed_paths: `core/review_queue.py`, `core/trade_schema.py`, `core/advisory_schema.py`, `tests/*`
- forbidden_paths: broker integration, execution boundaries, strategies
- expected_tests: Prove no execution behavior changed, test defaults for missing truth states, verify downgrade reason provenance.
- acceptance_proof: 100% of 108 tests passing in test_review_queue_live_entry.py and full suite green.

## High-Risk Path Review
- Modifying `core/review_queue.py` involves execution gating paths.
- The `_normalize_truth_quality` and `_maybe_promote_execute_candidate` paths were updated strictly to ensure that dynamically reconstructed row dictionaries propagate the explicit `truth_quality` and `truth_allows_execution` fields from the source candidate.
- We added `truth_quality` extraction inside `_build_review_queue_entry` to prevent the normalizer from erroneously overwriting existing valid truth markers with `TRUTH_UNKNOWN_BLOCKED`.
- No new final actions were introduced; no fallback gates were weakened. Missing truth continues to fail closed to `TRUTH_UNKNOWN_BLOCKED`.

## Scope Guard
- Work remains strictly constrained to audit telemetry and execution invariants in `review_queue.py`.
- No credentials, tokens, or broker APIs were touched. No dashboard actions were introduced. No strategy thresholds were changed.

## Grill Me Review
- What assumption can silently kill this change? If a downstream component strips these newly added fields before writing the JSON artifact, the telemetry will still show `null`.
- What behavior is claimed but not proven? We claim that UI and telemetry will now render `TRUTH_LIVE_FRESH`, but we haven't proven the frontend can decode these new Enums (UI parses strings).
- What would fail in live or paper even if tests pass? If an exotic strategy omits `truth_quality` natively, it will be forcefully downgraded to `TRUTH_UNKNOWN_BLOCKED` and rejected from live execution.

## Hermes Review
- This PR solidifies the contract for advisory telemetry rows. It guarantees that an `EXECUTE` final action MUST have an explicit `truth_allows_execution=True` and a valid `truth_quality` state, or it is safely downgraded to `REJECT`.
- All broker and live order paths remain strictly out of scope.

## GSD Review
- Fixed the regression where legacy tests and reconstructed queue rows were dropping `truth_quality`, causing the safety gate to block valid `EXECUTE` candidates.
- Propagated truth metadata completely via `_build_review_queue_entry`.
- Populated `permission_downgrade_reason` to satisfy historical test provenance.

## QA / Safety Review
- Ran full unit test suite; verified `test_review_queue_live_entry.py` passes all 108 assertions.
- Verified test mock `_make_trade` supplies `TRUTH_LIVE_FRESH` so tests pass naturally through the new gate.

## Acceptance Proof
All tests have passed locally. No execution thresholds were changed. The legacy missing truth state properly fails closed to `TRUTH_UNKNOWN_BLOCKED`.

## Runtime Proof Required After Merge
- Need to run a live/paper telemetry soak and verify that the emitted `advisory_*.jsonl` rows successfully serialize the new fields like `truth_quality="TRUTH_LIVE_FRESH"`.

## What This PR Does Not Prove
- It does not prove that ML models are generating higher confidence predictions.
- It does not prove that the UI dashboard correctly renders these fields.
- It does not prove that the strategy generators themselves are outputting valid truth quality; it only proves that the orchestrator will safely fail-close if they do not.

## Human Approval
- Awaiting human approval for final merge.
