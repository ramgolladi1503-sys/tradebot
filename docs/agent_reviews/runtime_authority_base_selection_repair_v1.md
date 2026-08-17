# Runtime-Authority Base Selection Repair V1

## Agent Work Contract

```text
source_agent=Codex
action=GOVERNANCE_REPAIR
title=Use exact GitHub pull-request base SHA in frozen-head authority jobs
scope=.github/workflows/frozen-head-exact-sha-certification.yml and its static regression test
requested_paths=.github/workflows/frozen-head-exact-sha-certification.yml,tests/test_frozen_head_exact_sha_workflow.py,docs/agent_reviews/runtime_authority_base_selection_repair_v1.md
allowed_paths=governance workflow, governance tests, governance review evidence
forbidden_paths=TradeBot runtime, feed, broker, credentials, strategies, PR814 exporter
expected_tests=focused governance tests, workflow parse, git diff --check
acceptance_proof=actual PR base SHA is used for all three base-authority jobs
```

## Scope Guard

The repair changes only the frozen-head governance workflow, its static test,
and this review evidence. It does not clean unrelated whitespace or modify
PR814 exporter files.

## Grill Me Review

The defect was deriving `BASE_SHA` from `origin/main` for every pull request.
That makes a non-main PR inherit unrelated historical divergence. The repair
uses the immutable pull-request base SHA and fails closed when it is absent or
cannot be resolved.

## Hermes Design

For pull-request events, the source of truth is
`github.event.pull_request.base.sha`; manual dispatch requires an explicit
`base_sha` input. The candidate head remains the exact GitHub head SHA. Each
authority job verifies both objects and computes changed paths directly from
`BASE_SHA` to `HEAD_SHA`. Candidate Python is not executed by the governance
jobs.

## GSD Implementation

Updated `exact-sha-identity`, `agent-review-base-authority`,
`runtime-authority-base-authority`, and `code-excellence-base-authority` to use
the exact base SHA. Added static tests preventing regression to `origin/main`.

## QA / Safety

The PR814 reproduction produced 1,147 files and unrelated whitespace failures
under the old main comparison, versus 28 files and a passing `git diff --check`
under its actual base SHA. Focused governance tests passed locally. No broker,
order, feed, credential, or live-runtime path was touched.

## Acceptance Proof

```text
NON_MAIN_PR_BASE_SELECTION_VALID=true
MAIN_PR_BEHAVIOR_PRESERVED=true
EXACT_SHA_AUTHORITY_PRESERVED=true
CANDIDATE_EXECUTION_AUTHORITY=false
```

## Runtime Proof Required After Merge

Re-run the frozen-head exact-SHA certification against PR814 head
`d8adee30f604cd8969a386afe3d74f6ace7016de` and base
`dff49dd5a9bd562659d4513f948605c941362da2`. Do not treat local tests as a
replacement for GitHub branch-protection checks.

## What This PR Does Not Prove

It does not prove PR814 is merge-ready, H1 prospective support, execution
viability, structural edge, paper authorization, or live readiness.

## Human Approval

Required before merging. This PR must pass normal branch protection and must
not be merged together with PR814.
