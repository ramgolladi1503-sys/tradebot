# Agent Review Evidence — PR #795 Trusted Smoke Gate

## Traceability Record

mode: CI_ONLY
candidate_id: PR795_AUTHENTICATED_SMOKE_GATE
decision: RUN_MAIN_ONLY_TRUSTED_BOUNDED_SMOKE
reason: PR #795 requires an authenticated five-file Upstox smoke before tooling closure, while repository secrets must never be exposed to pull-request code.
timestamp: 2026-08-06T05:05:00+05:30
is_order_action: false
broker_api_called: false
source: USER_APPROVED_PR_CLOSURE_ORDER_AND_PR795_GATE_CONTRACT

## Agent Work Contract

Add a temporary trusted smoke mechanism to `main` that runs only after the repository `tests` workflow succeeds for the exact internal PR #795 branch.

The secret-bearing job must:

- checkout `main` only;
- execute only a standalone runner reviewed and merged through this PR;
- treat PR #795's tested head SHA as metadata, never executable code;
- use `UPSTOX_ACCESS_TOKEN` without printing or persisting it;
- make a fixed read-only sequence of Upstox requests;
- create exactly one future, two CE, and two PE Parquet files;
- retain only sanitized verdict fields;
- update one sanitized result comment on PR #795;
- fail unless the exact smoke contract passes;
- be removed after PR #795 closes.

## Scope Guard

Allowed files:

```text
.github/workflows/psilor_pr795_trusted_smoke.yml
scripts/ci/psilor_pr795_trusted_smoke.py
tests/ci/test_psilor_pr795_trusted_smoke.py
docs/agent_reviews/pr795_trusted_smoke_gate.md
```

Excluded:

- checkout or execution of PR #795 code in a secret-bearing job;
- strategy code or registration;
- ranking, candidate-pool, TradeBuilder, or risk behavior;
- broker, order, execution, or live-feed behavior;
- market data mutation;
- data-admission or edge claims;
- persistence of credentials, authorization headers, raw tokens, or raw provider error bodies.

## Grill Me Review

The first workflow design checked out `github.event.workflow_run.head_sha` and then executed PR code while the repository secret was available. GitHub Advanced Security correctly raised **CodeQL: checkout of untrusted code in a privileged workflow**. That design is rejected.

The repaired design separates trust boundaries:

1. PR #795 code is tested by ordinary unprivileged PR workflows.
2. The privileged `workflow_run` job checks out `main` only.
3. A self-contained trusted runner on `main` performs a fixed, bounded provider smoke.
4. The triggering PR head SHA is recorded only as the source identity whose normal tests passed.

The trusted runner rejects absolute/dynamic endpoints, hardcodes the Upstox host and endpoint families, bounds retries, validates provider schemas, validates candle values, requires two common sessions, rewrites exactly five files, and verifies read-back hashes.

## Hermes Review

The workflow runs only when all conditions are true:

```text
UPSTREAM_WORKFLOW=tests
UPSTREAM_CONCLUSION=success
UPSTREAM_EVENT=pull_request
UPSTREAM_HEAD_BRANCH=data/psilor-v1-upstox-fetch-v2
UPSTREAM_HEAD_REPOSITORY=current repository
TRUSTED_CHECKOUT=main
```

The secret-bearing process executes only:

```text
scripts/ci/psilor_pr795_trusted_smoke.py
```

from `main`. It does not import or execute `scripts/fetch_psilor_v1_data.py`, `scripts/smoke_test_psilor_v1.py`, or any other PR-head file.

The result comment is an allow-list containing only:

- source head SHA;
- smoke verdict;
- selected expiry;
- future/CE/PE counts;
- Parquet file count;
- exact common sessions;
- SHA-256 reconciliation;
- current-run and unexpected-file flags;
- formal-extraction flag;
- artifact labels, row counts, sessions, and hashes.

## GSD Review

Execution sequence:

1. Validate and merge this temporary four-file CI PR.
2. Complete or retrigger PR #795's normal `tests` workflow.
3. Let the trusted workflow run from `main` after that exact head passes.
4. Read the sanitized PR #795 comment.
5. Repair only a confirmed provider or bounded-runner defect if identified.
6. Complete PR #795's final-head checks and merge it into its research base.
7. Remove the temporary trusted workflow and runner through a protected cleanup PR.

## QA / Safety Review

Focused tests prove:

1. middle-contract selection is deterministic;
2. conflicting duplicate candles fail closed;
3. the trusted smoke produces exactly five Parquet files and two common sessions;
4. an empty token returns `BLOCKED_AUTHENTICATION`;
5. an absolute/external endpoint is rejected before any request.

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
NO_PR_CODE_CHECKOUT_IN_PRIVILEGED_JOB
NO_PR_CODE_EXECUTION_IN_PRIVILEGED_JOB
TRUSTED_CHECKOUT=main
```

## Acceptance Proof

Required before merge:

- changed-file scope is exactly the four listed files;
- five focused trusted-runner tests pass;
- repository `ci` and `tests` pass;
- agent-review, Code Excellence, Repo Forensics, CodeQL, registry, portfolio, and RAG gates pass;
- the original CodeQL review thread is outdated or resolved after the trusted-main repair;
- PR is mergeable against current `main`;
- no unresolved actionable review thread remains.

Required after merge:

- a sanitized `PSILOR_AUTHENTICATED_SMOKE_RESULT` comment appears on PR #795;
- the result references the exact successful PR #795 tests head SHA;
- no credential material appears in comments or artifacts.

## Runtime Proof Required After Merge

No TradeBot process is started. The only runtime proof is isolated, read-only, GitHub-hosted market-data retrieval:

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

- that the repository secret exists or remains valid;
- that Upstox Plus permission is available;
- that provider historical endpoints are currently healthy;
- that the smoke will pass;
- that PR #795's implementation is executed with the token;
- that the Drive corpus is admitted;
- that 30 overlapping sessions exist;
- that DORL or PSILOR has structural edge;
- that any live or paper execution should be enabled.

A blocked or failed smoke remains a valid fail-closed outcome and must be reported precisely.

## Human Approval

The user explicitly instructed the assistant to complete and close PR #796 first, then work on PR #795 until closure in that order. PR #796 is merged. This temporary protected mechanism is necessary to satisfy PR #795's authenticated-smoke gate without requesting the user to paste credentials or weakening branch protection.

## Final Review Verdict

```text
TEMPORARY_TRUSTED_WORKFLOW_REQUIRED=YES
SCOPE_FILES=4
FOCUSED_TESTS=5
SECRET_EXPOSURE_ALLOWED=NO
PR_CODE_EXECUTED_WITH_SECRET=NO
TRUSTED_CODE_SOURCE=main
PR_COMMENT_SANITIZED=YES
STRATEGY_OR_RUNTIME_CHANGE=NO
DATA_ADMISSION_CHANGE=NO
MERGE_ALLOWED=ONLY_AFTER_ALL_REQUIRED_CHECKS_PASS
REMOVE_AFTER_PR795_CLOSE=YES
```
