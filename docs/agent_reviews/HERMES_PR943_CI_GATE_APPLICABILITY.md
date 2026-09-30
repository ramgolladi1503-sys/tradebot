# Hermes Design: PR943 CI Gate Applicability

**source_agent:** `hermes`
**action:** `DEFINE_CONTRACT`, `MAP_WORKFLOW`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**scope:** Correct CI inputs and applicability without weakening required gates or changing runtime behavior.

## Contracts

- Code Excellence remains a trusted `pull_request_target` workflow. It runs gate scripts and config from the base checkout and reads the exact candidate commit from a detached worktree as inert data only.
- Candidate worktree creation sets `GIT_LFS_SKIP_SMUDGE=1`: CE source analysis does not require unrelated LFS payloads. Exact candidate source remains checked out; pointer files do not replace the changed source files being analyzed.
- PR782 compares against the event PR base, never an unrelated historical stacked-PR branch. Its focused test commands remain unconditional once triggered. Protected-scope validation applies when PR782-owned runtime or evidence artifacts change.
- MEG certification uses a dedicated applicability job. Workflow-only and shared-test-only changes do not claim an out-of-scope certification; owned certification inputs run the full certification and forbidden-scope check.
- No check, assertion, token permission, certification rule, or safety boundary is disabled or weakened. Frozen-flow and Netlify checks are the only user-authorized exceptions for PR943.

## Acceptance

1. Trusted CE scripts analyze exact-head candidate contents and report zero blocks.
2. The three workflow files parse and pass whitespace validation.
3. PR782 focused tests execute and pass; unrelated shared test changes do not hit its stale-base scope assertion.
4. MEG only certifies owned inputs and reports non-applicability for unrelated shared tests.
5. Exact-SHA required CI passes before PR943 is merged.

## LFS quota handling

The workflow must not spend the repository's LFS download budget just to materialize candidate source. The skip-smudge setting is local to the temporary CE worktree creation; normal repository LFS behavior and all unrelated CI jobs stay unchanged. Acceptance requires the exact-head CE check to complete successfully without attempting an LFS object download.

No runtime code, broker calls, order actions, risk changes, strategy changes, credentials, live data, or branch-protection settings are in scope.

## Agent Work Contract

- `source_agent`: `hermes_then_gsd`
- `action`: `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `GENERATE_PATCH`, `GENERATE_TESTS`, `UPDATE_DOCS`
- `title`: PR943 CI gate applicability correction
- `scope`: CI workflow input provenance and trigger applicability
- `requested_paths`: the three workflows and this evidence document
- `allowed_paths`: those listed paths only
- `forbidden_paths`: runtime, order, broker, risk, strategy, credential, and live-data paths
- `expected_tests`: workflow parsing, CE gates, focused PR782 tests, and exact-SHA hosted checks
- `acceptance_proof`: exact candidate content is analyzed without executing candidate scripts; applicable tests and required checks pass.

## Scope Guard

No trading runtime or authority paths change. Required checks remain configured as before. Non-applicable certification is distinguished from a passing certification and emits an explicit skipped status.

## Grill Me Review

The principal risk is confusing a skipped out-of-scope certification with a positive certification. The applicability job emits a boolean based on changed owned inputs; only `true` runs the certification job. No success certificate is created for a skipped job.

## Hermes Review

The exact-head content is isolated as analysis data. The trusted CE scripts and config remain from the base checkout. PR782 keeps its focused tests, and scope is checked against the actual PR base only when owned artifacts change.

## GSD Review

The implementation changes only workflow YAML and review documentation. Local YAML parsing, `git diff --check`, focused PR782 tests, and unified CE validation are required; hosted exact-SHA results are authoritative.

## QA / Safety Review

No live process, broker API, order action, risk threshold, strategy, secret, credential, or live runtime data was accessed or changed.

## Acceptance Proof

Local validation: workflow YAML parsed; `git diff --check` passed; focused PR782 suite passed 25 tests; local unified CE reported zero blocking findings. Hosted exact-head checks must pass before PR943 merge. The two explicitly user-authorized PR943 exceptions remain the frozen-flow and Netlify checks.

## Runtime Proof Required After Merge

No runtime proof is required or claimed for CI workflow changes. These changes grant no paper or live execution authority.

## What This PR Does Not Prove

It does not prove live readiness, broker behavior, execution correctness, or market-data quality. It does not waive the full PR943 CI requirement apart from the two explicit exceptions.

## Human Approval

The user directed that PR943 be merged to `main` after fixes and green CI and explicitly allowed the frozen-flow and Netlify checks to be ignored. This supporting PR exists only to correct the trusted CI workflow required for that goal.
