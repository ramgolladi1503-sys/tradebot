# PR 766 — CI Unit-Test Timeout Increase

mode: OFFLINE_CI_MAINTENANCE
candidate_id: pr766-ci-timeout-30m
decision: REVIEW_ONLY
reason: allow the unchanged deterministic repository test suite to complete instead of being cancelled by the existing 15-minute job timeout.
timestamp: 2026-07-31T11:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr766_ci_timeout_30m.md

## Agent Work Contract

```text
source_agent: ChatGPT (GPT-5.6 Thinking)
action: GENERATE_PATCH
title: Increase deterministic CI unit-test timeout to 30 minutes
scope: change only the ci unit_tests job timeout from 15 to 30 minutes and add mandatory PR review evidence
requested_paths:
  - .github/workflows/ci.yml
  - docs/agent_reviews/pr766_ci_timeout_30m.md
allowed_paths:
  - .github/workflows/ci.yml
  - docs/agent_reviews/pr766_ci_timeout_30m.md
forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - core/**
  - strategies/**
  - credentials.py
  - .env
  - runtime/live/**
expected_tests:
  - GitHub Actions ci workflow completes without timeout cancellation
  - GitHub Actions tests workflow passes
  - python scripts/validate_agent_review_evidence.py
acceptance_proof:
  - unit_tests timeout-minutes equals 30
  - test command and marker selection are unchanged
  - health_gate timeout and command are unchanged
  - no runtime or trading path changes
```

## Scope Guard

In scope:

- Change `.github/workflows/ci.yml` `jobs.unit_tests.timeout-minutes` from `15` to `30`.
- Add this mandatory review-evidence file.

Out of scope:

- No test-command or marker changes.
- No dependency changes.
- No health-gate changes.
- No runtime, feed, broker, order, execution, risk, strategy, credential, or live-session changes.
- No merge.

Boundary verification:

- [x] Runtime paths unchanged.
- [x] Trading behavior unchanged.
- [x] Only the timeout value and mandatory review evidence are added.

## Grill Me Review

Verdict: PASS

Risks reviewed:

1. Increasing the timeout could hide a hung test suite.
2. The change could accidentally weaken test selection.
3. The health gate could be altered unintentionally.
4. A broad workflow rewrite could introduce unrelated behavior.

Controls:

- The increase is bounded to 30 minutes rather than unlimited.
- The pytest command and marker expression are byte-for-byte unchanged.
- The health-gate job remains at 10 minutes and its command remains unchanged.
- The semantic workflow diff is one timeout value.

## Hermes Review

Verdict: PASS

This is the minimum architectural correction for the observed failure mode. The prior run was terminated by the job's fixed 15-minute limit at 69% without an assertion failure, while the parallel repository `tests` workflow completed successfully. No test tiering or workflow restructuring is introduced.

## GSD Review

Verdict: PASS

Delivery is isolated on branch `agent/ci-timeout-30m-pr764` in draft PR #766 targeting `infra/github-first-loop-engineering-v1`. The implementation commit changes the timeout only. The PR remains unmerged.

## QA / Safety Review

Verdict: PASS_PENDING_FINAL_CI

Safety properties:

- `is_order_action=false`
- `broker_api_called=false`
- no live process start
- no runtime imports or modifications
- no strategy/risk/execution/feed changes
- no credentials or secrets
- no test suppression or skipped markers added

Required proof is the final-head completion of both deterministic workflows, especially `ci` beyond the former 15-minute boundary.

## Acceptance Proof

Acceptance requires:

- `.github/workflows/ci.yml` shows `unit_tests.timeout-minutes: 30`;
- the exact test command and exclusions remain unchanged;
- the `ci` unit-test job completes rather than being cancelled by the former 15-minute timeout;
- its dependent health gate completes;
- the independent `tests` workflow passes;
- Agent Review Evidence Gate passes;
- final changed paths remain confined to the two declared files.

## Runtime Proof Required After Merge

No TradeBot runtime proof is required because no runtime behavior changes.

After this maintenance PR is merged into PR #764's branch, rerun PR #764 final-head workflows and confirm the previously blocked `ci` workflow completes under the 30-minute limit.

## What This PR Does Not Prove

This PR does not prove:

- the full suite will always finish within 30 minutes;
- the suite cannot contain slow tests;
- PR #764 is ready to merge before its own final-head rerun;
- any trading strategy, feed, broker, risk, or execution behavior;
- production or live readiness.

## Human Approval

Human approval is required before merge.

Keep PR #766 draft and unmerged until final-head `ci`, `tests`, and Agent Review Evidence Gate results are inspected. After approval, merge PR #766 into `infra/github-first-loop-engineering-v1`, then rerun and reassess PR #764. Do not merge PR #764 as part of this maintenance task.
