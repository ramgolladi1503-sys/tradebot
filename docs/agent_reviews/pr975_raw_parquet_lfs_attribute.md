# PR #975 — Raw Parquet LFS Attribute Correction

## Evidence Contract Fields

- mode: CI_CHECKOUT_INTEGRITY_REPAIR
- candidate_id: pr975-raw-parquet-lfs-attribute
- decision: REVIEW_ONLY
- reason: Align the path-specific Git attributes with the raw Parquet blob stored in the protected base.
- source_agent: codex
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #975
- Branch: `ram/raw-parquet-attribute-bootstrap`
- Title: Correct LFS attributes for raw tracked Parquet.
- Scope: Add a path-specific attribute override for `runtime/strategy_validation/resolved_option_ticks_20260702.parquet` and test its filter attributes and dirty-status behavior.
- Requested paths:
  - `.gitattributes`
  - `tests/governance/test_parquet_lfs_attributes.py`
  - `docs/agent_reviews/pr975_raw_parquet_lfs_attribute.md`
- Allowed paths: the three requested paths above only.
- Forbidden paths/behaviors: broker, order, strategy, feed runtime, credentials, secrets, live configuration, LFS data migration, candidate execution, verifier bypass, or changes outside the allowed paths.
- Expected tests: verify the exact path has no LFS filter/diff/merge/text attributes and that ordinary Git status reports actual byte changes.
- Acceptance proof: focused tests and `git diff --check`; exact-head trusted-base rerun after this attribute reaches `main`.

## Scope Guard

Verdict: PASS

- The existing `*.parquet` LFS attributes remain in force for all other paths.
- Only the exact raw-stored Parquet path receives `-filter -diff -merge -text`.
- The trusted-base cleanliness check remains enabled and continues to reject real modifications.
- No artifact bytes, LFS objects, runtime code, broker code, strategies, or live settings are changed.

## High-Risk Path Review

Verdict: PASS

This patch changes repository attributes for one tracked data file and adds a test. It does not change trading execution, feed handling, strategy behavior, credentials, or production configuration. The raw file's contents and Git object identity are preserved.

## Grill Me Review

Verdict: PASS

Run 38317484735, after the protected checkout and exact-base validation, refused to continue because Git reported only ` M runtime/strategy_validation/resolved_option_ticks_20260702.parquet`. The exact base stores this 95,829,241-byte file as a raw Parquet Git blob while the wildcard attributes apply LFS filters. A path-specific exception aligns those representations without suppressing status checks. Tests retain visibility of actual data edits.

## Hermes Review

Verdict: PASS

The invariant is that repository attributes match the storage representation of each path. This one file is a raw Git blob, not an LFS pointer; applying the LFS clean filter can make a pristine checkout appear modified. Disable the LFS filters for this path only, preserve the wildcard for other files, and keep the fail-closed status check unchanged.

## GSD Review

Verdict: PASS

Implementation is limited to one `.gitattributes` rule and a focused regression test. No live path, runtime wiring, broker API, order, risk, strategy threshold, or configuration behavior is modified.

## QA / Safety Review

Verdict: PASS

- Test the path's `filter`, `diff`, `merge`, and `text` attributes as unset.
- Create a temporary repository with the same attributes and confirm an actual file edit appears in `git status`.
- No broker, order, live runtime, or external LFS operation is performed.
- The base check remains fail-closed; this change corrects the base metadata rather than suppressing a dirty result.

## Acceptance Proof

Local validation:

```bash
pytest -q tests/governance/test_parquet_lfs_attributes.py
git check-attr filter diff merge text -- runtime/strategy_validation/resolved_option_ticks_20260702.parquet
git diff --check
```

Expected results: 2 tests pass; all four attributes report `unset`; diff check passes. The PR's own protected-base check may still report this path dirty because it runs the current base's attributes. That result is UNVERIFIED for the candidate correction and is not represented as passing.

## Runtime Proof Required After Merge

After this attribute reaches `main`, rerun trusted-base evidence coverage for PR #971 at its exact current head. Confirm the protected-base `git status` is clean, candidate preparation uses the already-merged LFS skip-smudge behavior, no bulk LFS downloads occur, and the trusted verifier completes normally. Any remaining dirty path or verifier failure stays blocking.

## What This PR Does Not Prove

1. It does not prove trusted-base success until a run executes with this rule in the protected base.
2. It does not validate the Parquet dataset's research suitability or contents beyond its tracked raw-blob representation.
3. It does not certify feed recovery, strategy behavior, live readiness, profitability, or broker/order behavior.
4. It does not waive PR #971's trusted-base check.

## Human Approval

The trusted-base check on this bootstrap PR may report the known dirty marker because its job checks out the current protected base, which does not yet contain this rule. The user's authorization to merge PR #972 and PR #974 with bootstrap trusted-base results UNVERIFIED is noted as precedent, but this PR's own merge decision remains subject to the user's approval. If its check remains UNVERIFIED, do not report it as a pass.
