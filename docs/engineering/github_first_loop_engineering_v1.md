# GitHub-First Loop Engineering V1

## Purpose

TradeBot development currently moves between humans, ChatGPT, Codex, Antigravity, local worktrees, pull requests, and GitHub Actions. The engineering loop must survive agent-token exhaustion, chat loss, local machine unavailability, and reviewer handoffs without inventing progress.

V1 makes GitHub the durable source of truth for bounded engineering tasks. It does not add autonomous agent dispatch, a daemon, Aixion integration, broker access, live trading, deployment, or automatic merge behavior.

## Authority model

The authority order is:

1. committed task contract and checkpoint;
2. exact branch and commit history;
3. pull-request diff and metadata;
4. GitHub Actions and committed evidence manifests;
5. local-only material, which is non-authoritative until published.

An agent response is a convenience summary, not proof.

## Repository layout

```text
.loop/
  README.md
  policies/
  schemas/
  templates/

loop_tasks/<TASK_ID>/
  contract.json
  state.json
  handoff.json
  claims.json
  CONTINUE.md
  evidence/
    manifest.json

scripts/loop/
  init_task.py
  record_command.py
  checkpoint.py
  validate_task.py
  build_context.py
  next_action.py
```

## One task, one objective

A task contract must define one concrete objective. It freezes:

- allowed and forbidden paths;
- acceptance gates;
- required tests;
- human approvals;
- implementation and review cycle budgets;
- stop conditions.

Optional improvements discovered during implementation go to backlog. They do not silently expand the active task. A new correctness or safety defect may block the task, but it must be recorded as a finding with evidence.

## Lifecycle states

Supported states are:

```text
NEW
IMPLEMENTING
TESTING
REVIEWING
REPAIRING
OFFLINE_CERTIFIED
WAITING_FOR_HUMAN
LIVE_VALIDATING
EVIDENCE_AUDIT
READY_FOR_CONFIRMATION
READY_FOR_MERGE_RECOMMENDATION
BLOCKED
FAILED
DONE
CANCELLED
```

Legal transitions are defined in `.loop/policies/transitions.json`. `READY_FOR_MERGE_RECOMMENDATION` is not merged. No framework command merges a pull request.

## Two-commit checkpoint protocol

A durable cycle uses two commits:

1. Commit the implementation.
2. Capture that commit as `code_sha`.
3. Generate `state.json`, `handoff.json`, evidence references, and `CONTINUE.md` against `code_sha`.
4. Commit the checkpoint separately.
5. Push the branch.
6. Let the Loop Handoff Gate verify ancestry, scope, claims, hashes, tests, and context generation.

This avoids a circular requirement to embed the checkpoint commit SHA inside the checkpoint before that commit exists.

A local uncommitted worktree is not a checkpoint. Codex must checkpoint before stopping because of token exhaustion, workspace permissions, test failure, market closure, human approval, or any other blocker.

## Create a task

```bash
python3 scripts/loop/init_task.py \
  --task-id LOOP-20260731-001 \
  --title "Repair one bounded defect" \
  --objective "Correct and prove one behavior without expanding scope" \
  --work-branch fix/example \
  --allowed-path 'core/example.py' \
  --allowed-path 'tests/test_example.py' \
  --forbidden-path '.env' \
  --forbidden-path 'credentials.py' \
  --acceptance-gate behavior_proven \
  --required-test 'pytest -q tests/test_example.py' \
  --human-gate push_persistent_branch \
  --human-gate merge_pull_request \
  --stop-condition retry_budget_exhausted
```

Commit the initialized task before implementation.

## Record a command

```bash
python3 scripts/loop/record_command.py \
  --task-dir loop_tasks/LOOP-20260731-001 \
  --command-id TEST-001 \
  --required \
  --save-full-output \
  -- pytest -q tests/test_example.py
```

The recorder:

- executes without a shell;
- stores bounded summaries;
- redacts common credential fields;
- records exit code, duration, timestamp, and code SHA;
- optionally stores a redacted output file with SHA-256.

Large output should use a GitHub-hosted evidence bundle. Do not commit huge raw market captures to normal Git history.

## Create a checkpoint

After committing implementation changes and returning the worktree to clean state:

```bash
python3 scripts/loop/checkpoint.py \
  loop_tasks/LOOP-20260731-001 \
  --state TESTING \
  --worker codex \
  --next-action "Run the focused required tests and record proof." \
  --test-results-file loop_tasks/LOOP-20260731-001/evidence/commands.json \
  --commit --push
```

`--push` is rejected unless `--commit` is explicitly supplied. The script never merges.

Blocked work is also checkpointed:

```bash
python3 scripts/loop/checkpoint.py \
  loop_tasks/LOOP-20260731-001 \
  --state BLOCKED \
  --worker codex \
  --blocker "Workspace root is not writable" \
  --next-action "Grant write access and resume from the recorded code SHA." \
  --next-worker human \
  --commit --push
```

## Validate a task

```bash
python3 scripts/loop/validate_task.py loop_tasks/LOOP-20260731-001
```

Validation rejects:

- malformed contracts;
- empty allowed-path scope;
- illegal lifecycle transitions;
- exhausted cycle budgets;
- forbidden or out-of-scope code paths;
- high-risk path changes without a human gate;
- `PROVEN` claims without proof;
- missing proof IDs;
- evidence hash mismatches;
- absolute local paths as authoritative proof;
- Tier C evidence satisfying a gate;
- replay evidence proving a live claim;
- failed required commands in a success state;
- success states with blockers;
- `DONE` with missing frozen gates;
- a `code_sha` that is not an ancestor of checkpoint HEAD.

## Build compact context

```bash
python3 scripts/loop/build_context.py \
  --task-dir loop_tasks/LOOP-20260731-001 \
  --output /tmp/loop_context.md \
  --max-bytes 8192
```

The generated packet contains only:

- objective;
- current state and code SHA;
- next action;
- allowed and forbidden paths;
- changed paths;
- required tests;
- blockers;
- unresolved claims and findings.

It intentionally omits full logs, broad repository history, and old chat transcripts.

## Token-efficient Codex invocation

A normal Codex cycle should be invoked with:

```text
Read AGENTS.md.
Read loop_tasks/<TASK_ID>/CONTINUE.md and the referenced JSON files.
Perform only state.next_action within contract.allowed_paths.
Run focused tests only.
Commit implementation changes.
Create and push the checkpoint before stopping.
Do not merge.
Return task ID, state, code SHA, checkpoint SHA, tests, blockers, next action, and GitHub paths only.
```

Efficiency rules:

1. One cycle, one objective.
2. Read the compact context first.
3. Search only relevant allowed paths.
4. Do not resend project history.
5. Do not rerun the full suite after every edit.
6. Use focused tests locally and broad gates in CI.
7. Do not reopen frozen acceptance criteria.
8. Put optional improvements in backlog.
9. Stop after achieving one state transition.
10. Checkpoint before token exhaustion.

## ChatGPT takeover

When Codex is unavailable, the user can ask:

```text
Continue task LOOP-20260731-001 from GitHub.
```

A GitHub-connected ChatGPT session reconstructs the task from:

1. root `AGENTS.md`;
2. task `contract.json`;
3. `state.json`;
4. `handoff.json`;
5. `claims.json`;
6. `evidence/manifest.json`;
7. `CONTINUE.md`;
8. branch and PR metadata;
9. current diff;
10. GitHub Actions status and referenced artifacts.

ChatGPT may inspect and modify GitHub-backed code, add tests, review claims, update task files through normal commits, and use GitHub Actions as the execution oracle when connector permissions permit.

ChatGPT must not claim it ran:

- local Mac-only commands;
- broker-authenticated processes;
- live NSE sessions;
- unpushed worktree changes;
- local proprietary data.

Those gates remain `WAITING_FOR_HUMAN` or `BLOCKED`, with an exact local command and an explicit list of what remains unproven.

## Antigravity review handoff

Antigravity receives the same compact context and reviews only frozen acceptance gates. Findings should be structured with:

- finding ID;
- severity;
- affected path;
- claim;
- evidence;
- required proof.

Optional improvements are backlog. The reviewer may block only for correctness, safety, a violated contract, reproducible regression, or invalid evidence.

## Evidence tiers

### Tier A — committed

Use for continuation-critical small artifacts:

- contracts and state;
- handoffs;
- claims;
- test summaries;
- review findings;
- hashes;
- audit tables;
- CI references;
- next action.

### Tier B — GitHub-hosted bundle

Use for large logs and generated bundles. The committed Tier A manifest must record a durable GitHub reference, artifact name, SHA-256, code SHA, evidence class, and retention warning. A temporary artifact cannot be the only long-term proof of a critical conclusion.

### Tier C — local only

Tier C is non-authoritative. It cannot satisfy a frozen gate. The handoff must list it explicitly.

## Human gates

Explicit human approval remains required for:

- live market process start;
- broker credential use;
- persistent branch push when contract requires it;
- high-risk runtime changes;
- PR body mutation when contract requires it;
- deployment;
- merge;
- any order action.

V1 does not execute those actions automatically.

## Stop conditions

A task stops when:

- all frozen gates pass;
- retry budget is exhausted;
- a recorded external blocker prevents progress;
- a human decision is required;
- a safety violation is unresolved;
- the task is cancelled.

The loop must not create an endless audit cycle. New optional improvements become separate tasks.

## GitHub Actions

`.github/workflows/loop-handoff-gate.yml` uses read-only repository permissions. It:

- checks out full history;
- compiles the framework;
- runs focused loop tests;
- validates every committed task;
- verifies ancestry, scope, claims, and hashes;
- builds compact context packets;
- uploads a bounded validation artifact.

It does not write, approve, merge, deploy, call brokers, or start a live process.

## First production pilot

After this framework is independently reviewed, pilot it on PR #750 feed-recovery continuation as a separate loop task. Then create a second loop task for combined PR #750 and PR #748 certification.

This infrastructure PR must not modify either PR's runtime implementation. The pilot must preserve their current draft and unmerged states.