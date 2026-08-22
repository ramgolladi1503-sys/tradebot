# External Artifact Contract

## Agent Work Contract

Add a backend-neutral, fail-closed contract for resolving large immutable data artifacts. This PR is foundation-only and does not wire data retrieval into runtime or research execution.

## Scope Guard

Changed paths are limited to `core/external_artifacts.py`, its focused tests, and the data contract documentation. No broker, order, risk, feed, credential, live-runtime, strategy, or Git history paths are changed.

## Grill Me Review

Missing or mismatched bytes must not become an empty dataset or successful result. The implementation verifies exact size and SHA256 and returns an explicit blocked status.

## Hermes Review

The manifest and resolver are backend-neutral. Google Drive is intentionally not invented or contacted without authoritative immutable IDs, hashes, and credentials.

## GSD Review

The implementation is isolated, composable, and not runtime-wired. Future external backends must provide verified bytes to the same contract.

## QA / Safety Review

Focused tests cover missing data, hash mismatch, verified source installation, and verified cache reuse. No live or broker behavior is introduced.

## Acceptance Proof

`python3 -m pytest -q tests/core/test_external_artifacts.py` passes with 4 tests. `git diff --check` passes.

## Runtime Proof Required After Merge

None for this foundation-only contract. Consumer migration and external retrieval require separate review and evidence.

## What This PR Does Not Prove

It does not prove Google Drive access, dataset availability, research completeness, live readiness, execution authority, or dataset migration completion.

## Human Approval

Human review is required before merging this data-authority foundation.
