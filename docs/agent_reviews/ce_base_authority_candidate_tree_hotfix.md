# CE Base-Authority Candidate-Tree Hotfix Review

## Agent Work Contract

- source_agent: ChatGPT/GitHub connector
- action: narrow governance workflow repair
- scope: make the trusted-base Code Excellence job statically inspect the exact candidate tree while continuing to execute trusted base CE code and configuration
- requested_paths: `.github/workflows/frozen-head-exact-sha-certification.yml`, this review document
- forbidden_paths: execution, broker, feed/WebSocket, strategy, risk, credentials, live runtime, CE acceptance criteria

## Scope Guard

This change does not alter any Minerva, Cerberus, or Evidence rule. It changes only which exact filesystem tree those trusted rules inspect in the base-authority job.

## Grill Me Review

The previous job fetched the exact candidate and calculated its changed-path list, but invoked the static gates with `--repo .` while the checkout remained `main`. Existing changed files were therefore scanned from the base tree, and candidate-only files were absent. The repair creates a detached worktree at the already verified `HEAD_SHA` and passes that path as `--repo`.

## Hermes Review

Candidate Python is not executed. The invoked runner path, `PYTHONPATH`, imported CE modules, and `.gsd-forensics.yaml` all remain anchored to the trusted base checkout. Only static file reads use the detached exact candidate tree.

## GSD Review

The exact candidate identity is checked before and after materialization. The changed-path scope remains the explicit merge-base-to-head diff. No synthetic merge ref becomes authority.

## QA / Safety Review

The repaired job preserves fail-closed behavior. A candidate that violates Minerva, Cerberus, or Evidence rules will still block; the change prevents findings from being attributed to stale base content rather than the candidate being certified.

## Acceptance Proof

Acceptance requires the base-authority job to use trusted base gate code and configuration while scanning an exact detached worktree whose `HEAD` equals the PR candidate SHA.

## Runtime Proof Required After Merge

After merge, rerun PR827's exact-SHA certification and inspect the new Code Excellence result against its exact candidate tree. This governance fix itself provides no live runtime evidence.

## What This PR Does Not Prove

This change does not prove PR827 passes Code Excellence. It only makes that verdict candidate-correct. It does not prove live readiness, feed health, broker connectivity, trading edge, or runtime safety beyond separate evidence.

## Human Approval

Normal branch protection and required checks remain mandatory. No direct update to main and no check bypass is authorized.
