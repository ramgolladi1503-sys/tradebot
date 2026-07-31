# PR 764 — GitHub-First Loop Engineering V1

mode: OFFLINE_INFRASTRUCTURE
candidate_id: pr764-github-first-loop-engineering-v1
decision: REVIEW_ONLY
reason: add a GitHub-backed task contract, checkpoint, evidence, compact-context, and CI validation layer without changing TradeBot runtime behavior.
timestamp: 2026-07-31T08:40:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr764_github_first_loop_engineering_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT (GPT-5.6 Thinking)
action: GENERATE_PATCH
title: Add GitHub-first loop engineering handoff framework
scope: implement repository-only contracts, lifecycle validation, proof-linked claims, interrupt-safe checkpoints, compact agent context, focused tests, documentation, and a read-only GitHub Actions gate; do not modify trading runtime or automate merge/live actions
requested_paths:
  - .loop/**
  - scripts/loop/**
  - tests/loop/**
  - loop_tasks/**
  - docs/engineering/github_first_loop_engineering_v1.md
  - docs/agent_reviews/pr764_github_first_loop_engineering_v1.md
  - .github/workflows/loop-handoff-gate.yml
allowed_paths:
  - .loop/**
  - scripts/loop/**
  - tests/loop/**
  - loop_tasks/**
  - docs/engineering/**
  - docs/agent_reviews/**
  - .github/workflows/loop-handoff-gate.yml
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
  - python -m compileall -q scripts/loop tests/loop
  - pytest -q tests/loop
  - python3 scripts/loop/validate_task.py loop_tasks/examples/LOOP-EXAMPLE
  - python3 scripts/loop/validate_task.py loop_tasks/LOOP-20260731-001
  - python scripts/validate_agent_review_evidence.py
  - git diff --check
acceptance_proof:
  - GitHub is sufficient to reconstruct the task objective, state, proof, blocker, and next action
  - invalid transitions, scope violations, unsupported claims, hash mismatches, and replay-as-live proof fail closed
  - compact continuation context is bounded
  - checkpoint push is explicit and no merge action exists
  - CI runs with read-only repository permission
  - the generated validation/context artifact is actually uploaded and retrievable
```

## Scope Guard

In scope:

- Machine-readable task contracts and lifecycle state.
- Legal transition validation and cycle budgets.
- Proof-linked claims and evidence manifests.
- Two-commit implementation/checkpoint protocol.
- Bounded redacted command evidence.
- Compact continuation context for Codex, ChatGPT, Antigravity, or a human.
- Deterministic next-action recommendation.
- Read-only GitHub Actions validation and evidence upload.
- A non-runtime example task and a real checkpoint task for this PR.

Out of scope:

- No feed code.
- No broker integration.
- No order, execution, or risk code.
- No strategy or threshold changes.
- No credentials.
- No agent daemon or API dispatcher.
- No Aixion integration.
- No live process start.
- No automatic PR approval or merge.

Boundary verification:

- [x] No `core/**` file changed.
- [x] No `config/**` file changed.
- [x] No `strategies/**` file changed.
- [x] No broker/order/execution/risk file changed.
- [x] No credential or environment file changed.
- [x] PR #748 and PR #750 runtime branches were not modified.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

The only operationally sensitive path added is a new GitHub Actions workflow. It has:

- `contents: read` only;
- no pull-request write permission;
- no secrets use;
- no branch mutation;
- no commit, push, approval, merge, deploy, broker, or live command;
- bounded 30-day artifact retention;
- `if-no-files-found: error` so missing handoff artifacts fail closed;
- explicit hidden-file upload support for `.loop-ci/**`.

The framework scripts are repository tooling and do not import TradeBot runtime modules.

## Grill Me Review

Verdict: PASS_AFTER_REPAIRS

Primary risks reviewed:

1. An agent could self-declare `DONE` without proof.
2. A local-only path could be presented as authoritative evidence.
3. Replay evidence could be used to support a live claim.
4. An old or unrelated code SHA could be attached to a checkpoint.
5. A task could silently expand beyond its allowed paths.
6. A compact context could omit the active blocker or next action.
7. Push or merge behavior could occur implicitly.
8. Dot-prefixed repository paths could evade or falsely fail scope enforcement.
9. A generated validation artifact could be silently omitted.
10. Shallow source-shape tests could create fake confidence.

Observed controls:

- `DONE` requires all frozen gate IDs and no blockers or failed gates.
- `PROVEN` claims require existing proof IDs.
- immutable file evidence requires SHA-256 verification.
- absolute local paths and Tier C continuation-critical evidence are rejected.
- live claims require evidence class `live`.
- `code_sha` must be an ancestor of checkpoint HEAD.
- changed implementation paths are checked against allowed/forbidden scope.
- high-risk path changes require an explicit human gate.
- context includes objective, state, SHA, next action, paths, tests, blockers, and unresolved claims.
- `--push` requires explicit `--commit`; no merge implementation is present.
- the CI artifact step fails if the validation packet is missing.

## Defects Found by Independent Gates

### 1. External task-root portability

Initial defect:

- `init_task.py` assumed every task root was inside the repository and called `relative_to(repo_root)` unconditionally.
- Pytest temporary directories therefore failed despite being valid test roots.

Repair:

- Added safe display-path handling that returns a repository-relative path when possible and an absolute path otherwise.
- Duplicate-task behavior remains fail-closed.

### 2. Dot-prefixed scope normalization

Initial defect:

- Scope pattern normalization used `lstrip("./")`.
- This removed the leading dot from `.loop/**`, `.github/**`, and `.env`, producing incorrect scope decisions.

Repair:

- Only an exact leading `./` is removed.
- Leading dots remain part of repository paths.
- Added behavioral tests for `.loop/**`, `.github/workflows/**`, and `.env` forbiddance.

### 3. Minerva fake-confidence finding

Initial defect:

- The first test suite included an `assert len(...)` source-shape pattern.
- The repository Minerva gate classified it as `fake_confidence_test_not_valid_proof`.

Repair:

- Replaced the suite with behavioral tests that compute and verify the actual bounded context result.
- Did not suppress or weaken Minerva.
- Code Excellence subsequently passed.

### 4. Hidden artifact omission

Initial defect:

- The workflow generated `.loop-ci/validation.txt` and compact contexts successfully.
- `actions/upload-artifact` ignored the hidden `.loop-ci` directory by default and emitted only a warning.

Repair:

- Added `include-hidden-files: true`.
- Changed `if-no-files-found` from `warn` to `error`.
- Confirmed a retrievable artifact was created with a GitHub SHA-256 digest and expiry metadata.

## Hermes Review

Verdict: PASS

Architecture findings:

- V1 separates durable state from agent narrative.
- Contracts, state, claims, proof, and continuation instructions are independently readable.
- The two-commit protocol avoids circular self-SHA metadata.
- The implementation is standard-library only except for pytest in CI.
- Broad agent orchestration is deferred until the handoff protocol is proven.
- GitHub Actions is used as a remote execution oracle rather than pretending ChatGPT ran local commands.
- Local/live-only gates remain explicit `WAITING_FOR_HUMAN` or `BLOCKED` states.

The architecture is appropriate for a first loop-engineering layer because it adds continuity without coupling to trading runtime.

## GSD Review

Verdict: PASS

Delivery review:

- The branch is isolated as `infra/github-first-loop-engineering-v1`.
- PR #764 is draft and unmerged.
- CLIs exist for initialization, command recording, checkpointing, validation, context generation, and deterministic next-action recommendation.
- Schemas, templates, policies, tests, documentation, workflow validation, an example task, and a real PR checkpoint task are included.
- The implementation remains bounded to infrastructure paths.

## QA / Safety Review

Verdict: PASS

Safety properties:

- `is_order_action=false`
- `broker_api_called=false`
- no trading runtime import or modification
- no feed/risk/execution/strategy gate weakening
- no credentials or environment mutation
- no live process start
- no merge automation
- GitHub workflow permission is read-only

Behavioral coverage includes:

- valid task acceptance;
- empty allowed-path rejection;
- legal and illegal transitions;
- allowed, forbidden, dot-prefixed, and out-of-scope paths;
- claims without proof;
- missing proof IDs;
- missing or mismatched evidence hashes;
- absolute local evidence rejection;
- replay evidence rejected for live claims;
- blockers in success states;
- blocked state without blocker;
- cycle exhaustion;
- failed required test in a success state;
- compact context size and truncation behavior;
- credential-field redaction;
- deterministic repair routing;
- duplicate task rejection;
- explicit checkpoint push requirement;
- no merge or auto-merge invocation.

## Acceptance Proof

The framework has already demonstrated:

- focused loop tests passing in GitHub Actions;
- both committed loop tasks validating with no errors;
- compact context packets generated remotely;
- Agent Review Evidence Gate passing;
- Code Excellence, including Minerva, passing after the behavioral test repair;
- Repo Forensics, Portfolio CI, Strategy Registry, secret scanning, and CodeQL passing on reviewed implementation heads;
- a retrievable bounded validation artifact with GitHub digest and retention metadata.

The final task checkpoint and PR body must reference the exact final implementation head and its final-head workflow run IDs. This review document does not substitute for that machine-readable checkpoint.

## Runtime Proof Required After Merge

No trading-runtime proof is required because this PR does not alter runtime behavior.

Post-merge operational pilot required before treating the framework as established process:

1. Initialize one bounded continuation task for PR #750.
2. Have one worker checkpoint partial or blocked work.
3. Have ChatGPT reconstruct the task using GitHub only.
4. Confirm no continuation-critical evidence remains local-only.
5. Confirm the Loop Handoff Gate validates the task and uploads its context packet.
6. Keep live-market and broker-authenticated actions as human gates.

## What This PR Does Not Prove

This PR does not prove:

- autonomous agent dispatch works;
- Codex or Antigravity APIs are integrated;
- Aixion approvals are operational;
- ChatGPT can run local Mac commands;
- ChatGPT can access unpushed work;
- broker-authenticated or live-market tasks can run remotely;
- GitHub artifact retention is permanent;
- the framework improves strategy profitability;
- PR #748 or PR #750 is ready to merge;
- every future task contract will be well designed.

It provides durable continuity and validation primitives, not autonomous engineering completion.

## Human Approval

Human approval is required before merge.

Keep PR #764 draft until:

- every workflow on the final checkpoint head passes;
- final changed paths remain inside the documented boundary;
- the PR body records the final head and conclusions;
- an independent human reviews the final diff.

Do not merge PR #764 as part of this implementation task.
