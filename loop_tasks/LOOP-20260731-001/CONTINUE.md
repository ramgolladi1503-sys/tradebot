# Continue LOOP-20260731-001

Read root `AGENTS.md` first. GitHub is authoritative; local-only work is not proof.

## Objective
Implement and certify GitHub-First Loop Engineering V1 without modifying TradeBot runtime, feeds, broker, risk, execution, strategies, credentials, PR #748, or PR #750 runtime code.

## Current state
- State: `BLOCKED`
- Code SHA: `cf9276c75e1f53617723c8d598c428c04652adca`
- Branch: `infra/github-first-loop-engineering-v1`
- PR: `#764`
- Cycle: `3`
- Human decision required: `true`

## Completed proof
- Loop Handoff Gate passed.
- `15` focused loop tests passed.
- Both committed loop tasks validated.
- The bounded validation/context artifact was uploaded and is referenced in `evidence/manifest.json`.
- Agent Review Evidence Gate passed.
- Code Excellence and Minerva passed.
- Repo Forensics passed.
- Strategy Registry verification passed.
- CodeQL passed.
- Portfolio CI passed.
- The independent repository `tests` workflow, including its health gate, passed.
- Final changed-file inventory is confined to the declared infrastructure-only scope.

## External blocker
The duplicate repository workflow `.github/workflows/ci.yml` sets `timeout-minutes: 15` for its `unit_tests` job. Run `30617389326` was cancelled at 69% with no reported assertion failure because it exceeded that fixed timeout. The independent `tests` workflow `30617389255` completed successfully.

Fixing the repository-wide `ci` timeout is outside this task's frozen allowed paths.

## Next action
Choose one:

1. Create a separate bounded CI-maintenance loop task to increase or restructure the 15-minute `ci` workflow, then rerun PR #764; or
2. Make an explicit human policy decision that the successful `tests` workflow is the authoritative full-suite oracle for this infrastructure PR despite the duplicate timed-out workflow.

Until that decision, keep PR #764 draft and unmerged.

## Safety boundary
Do not modify or run TradeBot live runtime, brokers, orders, execution, risk, feeds, strategies, credentials, PR #748, or PR #750 as part of this task. Do not approve, deploy, auto-merge, or merge PR #764.
