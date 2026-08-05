# Agent Review Evidence — PR #795 Trusted Smoke Gate

## Traceability Record

mode: CI_ONLY
candidate_id: PR795_AUTHENTICATED_SMOKE_GATE
decision: RUN_EXACT_BRANCH_RESTRICTED_AUTHENTICATED_SMOKE
reason: PR #795 requires an authenticated five-file Upstox smoke result before tooling closure, while repository secrets must remain on the protected default-branch workflow boundary.
timestamp: 2026-08-06T04:50:00+05:30
is_order_action: false
broker_api_called: false
source: USER_APPROVED_PR_CLOSURE_ORDER_AND_PR795_GATE_CONTRACT

## Agent Work Contract

Add one temporary GitHub Actions workflow on `main` that runs after the repository `tests` workflow succeeds for the exact internal branch `data/psilor-v1-upstox-fetch-v2`.

The workflow must:

- use the repository `UPSTOX_ACCESS_TOKEN` secret without printing or persisting it;
- checkout the exact tested PR #795 head SHA;
- execute `scripts/smoke_test_psilor_v1.py`;
- retain only sanitized verdict fields;
- post the sanitized result to PR #795;
- fail unless the exact five-file smoke contract passes;
- be removed after PR #795 closes.

## Scope Guard

Allowed files:

```text
.github/workflows/psilor_pr795_trusted_smoke.yml
docs/agent_reviews/pr795_trusted_smoke_gate.md
```

Excluded:

- strategy code or registration;
- ranking, candidate-pool, TradeBuilder, or risk behavior;
- broker, order, execution, or live-feed behavior;
- market data mutation;
- data-admission or edge claims;
- persistence of credentials, authorization headers, or raw tokens.

## Grill Me Review

The prior smoke workflows were located only on PR #795's research lineage. GitHub did not schedule them as a secret-capable trusted workflow, so the absence of a result could not be interpreted as either authentication failure or smoke success.

A direct write to `main` was rejected by branch protection, correctly requiring this change to pass through a pull request. The temporary workflow is therefore the narrowest auditable method to obtain the missing verdict without weakening branch rules or asking the user to expose a token.

## Hermes Review

The workflow uses `workflow_run` for the existing `tests` workflow and applies all of these conditions:

```text
UPSTREAM_CONCLUSION=success
UPSTREAM_EVENT=pull_request
UPSTREAM_HEAD_BRANCH=data/psilor-v1-upstox-fetch-v2
```

It checks out `github.event.workflow_run.head_sha`, not a mutable branch tip. The smoke result is reduced to an allow-list of counts, sessions, hashes, boolean verdicts, and workflow identity. The PR comment contains no credentials, headers, request payloads, or raw provider response bodies.

## GSD Review

Execution sequence:

1. Merge this temporary two-file CI PR after repository gates pass.
2. Complete or retrigger the normal `tests` workflow on PR #795.
3. Let the trusted `workflow_run` gate execute on the exact successful head.
4. Read the sanitized comment on PR #795.
5. Repair a confirmed smoke defect if the verdict identifies one.
6. Merge and close PR #795 only after its merge boundary is satisfied.
7. Remove the temporary workflow through a separate protected PR.

## QA / Safety Review

Safety assertions:

```text
NO_ORDER_ACTIONS
NO_EXECUTION_AUTHORITY
NO_BROKER_API_CALLS
NO_STRATEGY_CHANGES
NO_RISK_CHANGES
NO_LIVE_RUNTIME_CHANGES
NO_CREDENTIAL_PERSISTENCE
NO_TOKEN_IN_PR_COMMENT
EXACT_HEAD_SHA_CHECKOUT
```

The result allow-list is restricted to:

- smoke verdict;
- future/CE/PE contract counts;
- Parquet file count;
- exact common sessions;
- hash reconciliation;
- unexpected-file and current-run provenance flags;
- formal-extraction flag;
- workflow run identity and tested SHA.

## Acceptance Proof

Required before merge:

- changed-file scope is exactly the workflow and this review document;
- repository `ci` and `tests` pass;
- agent-review, Code Excellence, Repo Forensics, CodeQL, registry, and portfolio gates pass;
- PR is mergeable against current `main`;
- no unresolved review thread remains.

Required after merge:

- a sanitized `PSILOR_AUTHENTICATED_SMOKE_RESULT` comment appears on PR #795;
- the result references the exact tested PR #795 head SHA;
- no credential material appears in the comment or artifacts.

## Runtime Proof Required After Merge

No TradeBot runtime is started. The only post-merge runtime proof is the isolated GitHub-hosted offline smoke:

```text
1 expired future
2 CE contracts
2 PE contracts
5 Parquet files
2 exact completed sessions
SHA-256 reconciliation PASS
no unexpected files
created by current run
```

## What This PR Does Not Prove

This PR does not prove:

- that the repository secret exists or is valid;
- that Upstox historical endpoints are currently available;
- that the smoke will pass;
- that the Drive corpus is admitted;
- that 30 overlapping sessions exist;
- that DORL or PSILOR has an edge;
- that any live or paper execution should be enabled.

A blocked or failed smoke remains a valid fail-closed outcome and must be reported precisely.

## Human Approval

The user explicitly instructed the assistant to complete and close PR #796 first, then work on PR #795 until closure in that order. PR #796 is already merged. This temporary workflow is necessary to satisfy PR #795's previously stated authenticated-smoke gate without requesting the user to paste credentials or bypassing branch protection.

## Final Review Verdict

```text
TEMPORARY_WORKFLOW_REQUIRED=YES
SCOPE_FILES=2
SECRET_EXPOSURE_ALLOWED=NO
PR_COMMENT_SANITIZED=YES
STRATEGY_OR_RUNTIME_CHANGE=NO
DATA_ADMISSION_CHANGE=NO
MERGE_ALLOWED=ONLY_AFTER_ALL_REQUIRED_CHECKS_PASS
REMOVE_AFTER_PR795_CLOSE=YES
```
