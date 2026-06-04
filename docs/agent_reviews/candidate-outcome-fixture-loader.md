# Agent Review Evidence — Candidate Outcome Fixture Loader

## Agent Work Contract

- **Goal**: add a deterministic offline fixture loader for the existing Candidate Outcome Truth contract.
- **Scope**: committed JSON fixtures only; no runtime wiring.
- **Changed files**:
  - `core/candidate_outcome_fixture_loader.py`
  - `tests/test_candidate_outcome_fixture_loader.py`
  - `tests/fixtures/candidate_outcomes/*.json`
  - `docs/candidate_outcome_fixture_loader.md`
  - `docs/agent_reviews/candidate-outcome-fixture-loader.md`

## Scope Guard

- Closed/off-market environment only.
- No broker, order, Kite, websocket, or runtime access.
- No strategy, ranking, Phase2, or dashboard changes.
- No FeedTruth contract changes.
- No live session writes.

## Grill Me Review

- Fixture loading can become fake progress if it silently accepts malformed JSON or non-deterministic ordering.
- The loader must fail closed on malformed fixtures and preserve deterministic load order.
- The loader must not prove edge; it only prepares offline inputs for future evaluation.

## Hermes Review

- The loader is a pure adapter from committed JSON to existing `CandidateOutcomeInput` and `PriceObservation` objects.
- It is read-only and has no runtime wiring.
- It explicitly depends on the existing Candidate Outcome Truth contract instead of duplicating evaluation logic.

## GSD Review

- Minimal surface area: one new loader module, one focused test file, committed fixtures, and docs.
- Deterministic directory loading ensures future reports and fixtures remain reproducible.

## QA / Safety Review

- Tests prove target/stop/timeout/no-observation/ambiguous/out-of-window cases load and evaluate correctly.
- Tests prove malformed fixtures fail closed.
- Tests prove the loader and evaluated truth remain read-only and non-action.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. pytest -q tests/test_candidate_outcome_fixture_loader.py -vv
PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
```

Expected:

- fixtures load deterministically
- malformed fixtures fail closed
- evaluated truth matches committed expected statuses
- read-only flags remain intact

## Runtime Proof Required After Merge

Future consumer PRs may use these committed fixtures to generate offline reports, but this PR does not wire any runtime behavior.

## What This PR Does Not Prove

- It does not prove trading edge.
- It does not wire into runtime.
- It does not call broker or Kite APIs.
- It does not change strategy, ranking, or execution behavior.

## Human Approval

Proceed only if the branch stays offline-only, the loader remains deterministic, and the evidence gate passes without touching forbidden runtime files.
