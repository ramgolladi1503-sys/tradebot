# CI LFS Exact Candidate Checkout Repair

## Agent Work Contract

This PR repairs only the trusted CI workflow used to materialize the exact candidate tree for Code Excellence. No runtime or trading behavior is in scope.

## Scope Guard

Changed file: `.github/workflows/frozen-head-exact-sha-certification.yml`. No application, broker, risk, feed, credential, live-runtime, or strategy files are changed.

## Grill Me Review

The change must not skip exact-SHA identity, changed-path collection, or CE execution. It only prevents Git LFS smudge during detached worktree creation so unrelated blobs cannot exhaust the runner or repository LFS budget.

## Hermes Review

The trusted base workflow remains authoritative. The candidate tree is still created at the exact verified `HEAD_SHA`; `GIT_LFS_SKIP_SMUDGE=1` changes checkout materialization, not commit identity or policy evaluation.

## GSD Review

The implementation is one workflow-line change with no runtime wiring and no behavior migration.

## QA / Safety Review

No broker API, order action, live mode, risk gate, kill switch, feed freshness gate, credential, or evidence contract behavior is changed.

## Acceptance Proof

`git diff --check` passes. CI must show exact-SHA identity, scope checks, and the Code Excellence gate executing against the candidate tree without an LFS smudge failure.

## Runtime Proof Required After Merge

None for this CI-only repair. The existing engineering PRs retain their own runtime and live-readiness contracts.

## What This PR Does Not Prove

This PR does not prove live readiness, observer certification, execution authority, broker connectivity, or strategy performance.

## Human Approval

Human review is required before merging this workflow change into `main`.
