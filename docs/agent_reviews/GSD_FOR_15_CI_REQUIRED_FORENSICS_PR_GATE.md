# GSD-FOR-15 — CI Required Forensics PR Gate

## Agent Work Contract

### Scope

Add a GitHub Actions workflow that runs the baseline-aware repo-forensics PR gate on pull requests to `main`.

This turns the repo-forensics gate from chat/manual discipline into a visible repository check.

### Files Changed

- `.github/workflows/repo-forensics-pr-gate.yml`
- `docs/agent_reviews/GSD_FOR_15_CI_REQUIRED_FORENSICS_PR_GATE.md`

### Hard Boundaries

- No TradeBot runtime imports intentionally executed.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No merge automation.
- No baseline mutation.
- No test weakening.

## Workflow

```text
.github/workflows/repo-forensics-pr-gate.yml
```

Runs on:

- `pull_request` to `main`
- `workflow_dispatch`

Command:

```bash
python scripts/run_repo_forensics_pr_gate.py --repo . --config .gsd-forensics.yaml
```

Environment:

```text
PYTHONPATH=.
EXECUTION_MODE=PAPER
KITE_USE_API=false
```

## Gate Policy

The underlying PR gate policy remains:

| Condition | Verdict |
|---|---|
| New hard failures | FAIL |
| No new hard failures, but new unknowns | UNKNOWN |
| No new hard failures/unknowns, but new warnings | PASS_WITH_WARNINGS |
| Same or improved counts | PASS |

Current workflow blocks only when the script exits non-zero. The current script exits non-zero for `FAIL`.

## Why It Does Not Install `requirements.txt`

This gate is a static repo-forensics check. The config loader is dependency-free and the scanner should not need TensorFlow, Kite, Streamlit, or trading libraries.

Installing full requirements would make this check slower, noisier, and more fragile for no benefit.

## Grill Me Review

### Challenge

A CI gate can create friction if it blocks on old debt or heavy dependencies.

### Findings

- Good: the gate compares against committed baseline rather than blocking on existing debt.
- Good: the workflow does not install full requirements.
- Good: timeout is limited to 10 minutes.
- Good: report artifact is uploaded for review.
- Risk: branch protection still needs to mark this workflow as required in GitHub settings; this PR adds the workflow but cannot change repository branch protection through code.

### Verdict

PASS — valid for GSD-FOR-15 as repository-visible CI enforcement.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No scanner behavior changed.
- [x] No baseline mutation.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The workflow runs the existing static PR gate with `EXECUTION_MODE=PAPER` and `KITE_USE_API=false`. It does not run TradeBot live execution or broker actions.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] PR gate workflow added.
- [x] Runs on pull requests to `main`.
- [x] Runs on manual dispatch.
- [x] Uploads report artifact.
- [x] Avoids full dependency installation.
- [x] Evidence file added.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- GitHub Actions workflow for PR gate.
- Static forensics gate execution.
- Report artifact upload.
- Evidence documentation.

### Out of Scope

- Branch protection setting changes.
- Product code changes.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Auto-PR.
- Baseline debt cleanup.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime execution intended.
- [x] No scanner behavior changes.
- [x] No baseline mutation.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — CI workflow only.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR wires the existing gate into CI and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — workflow will run on this PR.

## Manual Verification

Local command:

```bash
PYTHONPATH=. python scripts/run_repo_forensics_pr_gate.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Required Repo Setting After Merge

In GitHub branch protection for `main`, mark this workflow/job as required:

```text
Repo Forensics PR Gate / repo-forensics-pr-gate
```

Without branch protection, the workflow is visible but not impossible to bypass.


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
