# Continue LOOP-20260731-001

Read root `AGENTS.md` first. GitHub is authoritative; local-only work is not proof.

## Objective
Certify GitHub-First Loop Engineering V1 without modifying TradeBot runtime, feeds, risk, execution, broker, or strategy behavior.

## State
- State: `REVIEWING`
- Code SHA: `7bf82dd6555b99eeae2df4fa4fa42eb3bebc2225`
- Branch: `infra/github-first-loop-engineering-v1`
- PR: `#764`
- Cycle: `2`

## Completed proof
- Loop Handoff Gate passed at the code checkpoint.
- `21` focused loop tests passed.
- The committed example task validated.
- Agent Review Evidence Gate passed.

## Next action
Verify every workflow on the checkpoint head. Inspect any exact failing job and repair only defects inside the contract scope. Then perform the final changed-path and PR-diff scope review.

## Allowed paths
- `.loop/**`
- `scripts/loop/**`
- `tests/loop/**`
- `loop_tasks/README.md`
- `loop_tasks/examples/**`
- `.github/workflows/loop-handoff-gate.yml`
- `docs/engineering/github_first_loop_engineering_v1.md`
- `docs/agent_reviews/pr764_github_first_loop_engineering_v1.md`

The current task directory itself may be updated as checkpoint metadata.

## Forbidden paths
- `main.py`
- `run_live.sh`
- `config/**`
- `core/**`
- `strategies/**`
- credentials and environment files
- PR #748 and PR #750 runtime implementations

## Remaining gates
- all final-head workflows pass;
- final diff scope review passes.

## Safety
Keep PR #764 draft and unmerged. Do not deploy, start live trading, call brokers, use credentials, approve, or merge.
