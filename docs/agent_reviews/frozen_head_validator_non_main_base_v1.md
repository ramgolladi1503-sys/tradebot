# Frozen-Head Validator Non-Main Base Repair V1

## Agent Work Contract

```text
source_agent=ChatGPT
action=GOVERNANCE_REPAIR
title=Honor explicit PR base SHA inside frozen-head bridge validator
scope=scripts/validate_frozen_head_bridge.py,tests/test_frozen_head_exact_sha_workflow.py,docs/agent_reviews/frozen_head_validator_non_main_base_v1.md
forbidden_paths=runtime,feed,broker,credentials,strategies,PR814 source
acceptance_proof=non-main PR base SHA is resolved and used directly by validator
```

## Scope Guard

This repair is limited to the frozen-head bridge validator, its static regression test, and this evidence document. It does not modify PR814 source, live runtime, broker execution, feed code, credentials, or strategy logic.

## Grill Me Review

Fresh PR814 certification proved the workflow correctly supplied base SHA `dff49dd5a9bd562659d4513f948605c941362da2`, but the validator then recomputed `origin/main` as `f02927badf8f79cef77d4b9edccef597a9c32862` and failed with `BASE_SHA_DRIFT`. That makes the validator incompatible with legitimate non-main pull-request bases.

## Hermes Review

The trusted workflow already obtains the immutable pull-request base SHA from GitHub event metadata (or explicit workflow-dispatch input). The validator must validate that exact supplied SHA resolves to a commit and use it for merge-base and changed-path computation. It must not replace that authority with `origin/main`.

## GSD Review

The repair changes the validator from `actual_base = git("rev-parse", "origin/main")` plus equality enforcement to `base = git("rev-parse", args.base_sha)` plus exact resolution validation. Merge-base computation and printed `PR_BASE_SHA` now use `base`. A regression test explicitly rejects restoration of the stale `origin/main` assumption.

## QA / Safety Review

The change does not execute candidate Python, does not alter candidate identity validation, and does not weaken high-risk-path or focused-test enforcement. Manifest lookup remains base-authoritative governance evidence on `origin/main`; only pull-request diff authority is corrected to the supplied exact base SHA.

## High-Risk Path Review

No TradeBot runtime, feed, execution, risk, broker, credential, or strategy path is modified. The governance change is covered by a focused static regression test.

## Acceptance Proof

```text
NON_MAIN_PR_BASE_VALIDATOR_SUPPORTED=true
EXPLICIT_BASE_SHA_AUTHORITY_PRESERVED=true
CANDIDATE_SHA_AUTHORITY_PRESERVED=true
CANDIDATE_EXECUTION_AUTHORITY=false
HIGH_RISK_SCOPE_GUARD_PRESERVED=true
```

## Runtime Proof Required After Merge

Re-run Frozen Candidate Exact-SHA Certification for PR814 at head `d8adee30f604cd8969a386afe3d74f6ace7016de` and base `dff49dd5a9bd562659d4513f948605c941362da2`. The `agent-review-base-authority` job must no longer emit `BASE_SHA_DRIFT` solely because current `main` differs from the PR base.

## What This PR Does Not Prove

It does not prove PR814 merge readiness, H1 prospective support, execution viability, live readiness, or structural edge.

## Human Approval

Normal branch protection and required checks remain mandatory before merge.
