# Agent Review — Code Excellence Merge-base Preservation

mode: PAPER
candidate_id: PR793_CODE_EXCELLENCE_MERGE_BASE
is_order_action: false
broker_api_called: false

## Agent Work Contract

Repair only the Code Excellence workflow's changed-path collection step so it retains enough `main` history for the existing three-dot comparison after the base branch advances.

## Scope Guard

In scope:

- `.github/workflows/code-excellence-gates.yml`;
- this mandatory review record.

Out of scope:

- TradeBot runtime, feeds, strategies, ranking, risk, broker, orders, execution, credentials, tests, assertions, or gate thresholds;
- bypassing or suppressing any required check.

## Grill Me Review

The old command fetched `main` with `--depth=1`, replacing the full-history remote-tracking ref with a shallow tip. A PR created from an older `main` could then fail `git diff origin/main...HEAD` because Git had no merge base. The repair removes the shallow depth restriction while retaining the same three-dot diff and all downstream gates.

## Hermes Review

Scope result: PASS_PENDING_REQUIRED_CI.

The patch changes one workflow command and adds this evidence file. It preserves the existing checkout depth, changed-path comparison, unified CE execution, report generation, and artifact upload.

## GSD Review

Delivery verdict: PASS_PENDING_REQUIRED_CI.

The implementation is complete when a PR whose base advanced can collect changed paths successfully and the existing Code Excellence gate runs without weakening any assertion.

## QA / Safety Review

Required checks:

- workflow YAML remains valid;
- `git fetch origin main --no-tags` preserves ancestry;
- `git diff --name-only origin/main...HEAD` remains unchanged;
- no test, runtime, broker, strategy, ranking, risk, or execution setting changes;
- no required workflow is skipped.

Safety state:

- read_only: true
- is_order_action: false
- broker_api_called: false
- paper/live execution changed: false

## Acceptance Proof

1. The changed-path collection step no longer uses `--depth=1`.
2. The existing three-dot diff is unchanged.
3. Agent Review Evidence Gate passes.
4. Code Excellence Gates passes on the updated stacked head.
5. Required repository CI completes without a branch-protection bypass.

## Runtime Proof Required After Merge

No live-market or broker runtime proof is required because this is a CI-only ancestry-fetch repair. The authoritative proof is a successful Code Excellence workflow on a PR whose target branch advanced after the feature branch was created.

## What This PR Does Not Prove

- It does not certify TradeBot runtime behavior.
- It does not prove strategy edge or profitability.
- It does not change or weaken code-excellence assertions.
- It does not authorize paper or live execution.

## Human Approval

Human approval is required before merge. Confirm that the patch is limited to preserving Git ancestry for the existing changed-path comparison and that no required gate is bypassed.
