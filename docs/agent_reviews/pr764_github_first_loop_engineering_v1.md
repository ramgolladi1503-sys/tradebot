# PR 764 — GitHub-First Loop Engineering V1

mode: OFFLINE_INFRASTRUCTURE
candidate_id: pr764-github-first-loop-engineering-v1
decision: REVIEW_ONLY
reason: add a GitHub-backed task contract, checkpoint, evidence, compact-context, and CI validation layer without changing TradeBot runtime behavior.
timestamp: 2026-07-31T08:10:00Z
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
  - python scripts/validate_agent_review_evidence.py
  - git diff --check
acceptance_proof:
  - GitHub is sufficient to reconstruct the task objective, state, proof, blocker, and next action
  - invalid transitions, scope violations, unsupported claims, hash mismatches, and replay-as-live proof fail closed
  - compact continuation context is bounded
  - checkpoint push is explicit and no merge action exists
  - CI runs with read-only repository permission
```

## Scope Guard

In scope:

- Machine-readable task contracts and state.
- Legal lifecycle transitions.
- Proof-linked claims and evidence manifests.
- Two-commit implementation/checkpoint protocol.
- Bounded redacted command evidence.
- Compact continuation context for Codex, ChatGPT, Antigravity, or a human.
- Read-only GitHub Actions validation.
- A non-runtime example task.

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
- bounded artifact retention.

The framework scripts are repository tooling and do not import TradeBot runtime modules.

## Grill Me Review

Verdict: PASS_AFTER_REPAIR

Main risks reviewed:

1. An agent could self-declare `DONE` without proof.
2. A local-only path could be presented as authoritative evidence.
3. Replay evidence could be used to support a live claim.
4. An old or unrelated code SHA could be attached to a checkpoint.
5. A task could silently expand beyond its allowed paths.
6. A compact context could omit the active blocker or next action.
7. Push or merge behavior could occur implicitly.

Observed controls:

- `DONE` requires all frozen gate IDs and no blockers or failed gates.
- `PROVEN` claims require existing proof IDs.
- evidence files require SHA-256 verification.
- absolute local paths and Tier C continuation-critical evidence are rejected.
- live claims require evidence class `live`.
- `code_sha` must be an ancestor of checkpoint HEAD.
- changed implementation paths are checked against allowed/forbidden scope.
- context includes objective, state, SHA, next action, paths, tests, blockers, and unresolved claims.
- `--push` requires explicit `--commit`; no merge implementation is present.

Defect found by independent CI:

- `init_task.py` initially assumed every task root was inside the repository and failed for an external pytest temporary directory.
- Repaired at commit `60b35afe024d10399b9c20ffb7e533f0996c4687` by safely displaying either a repository-relative or absolute task path.
- The Loop Handoff Gate subsequently passed.

## Hermes Review

Verdict: PASS

Architecture findings:

- V1 deliberately separates durable state from agent narrative.
- Contracts, state, claims, proof, and continuation instructions are independently readable.
- The two-commit protocol avoids circular self-SHA metadata.
- The implementation is standard-library only except for pytest in CI.
- Broad agent orchestration is deferred until the handoff protocol is proven.
- GitHub Actions is used as a remote execution oracle rather than pretending ChatGPT ran local commands.

The architecture is appropriate for a first loop-engineering layer because it adds continuity without coupling to trading runtime.

## GSD Review

Verdict: PASS

Delivery review:

- The branch is isolated as `infra/github-first-loop-engineering-v1`.
- The PR is draft and unmerged.
- The framework includes CLIs for initialization, command recording, checkpointing, validation, context generation, and deterministic next-action recommendation.
- Schemas, templates, policy files, tests, documentation, workflow validation, and a self-contained example are included.
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

Behavioural test coverage includes:

- valid task acceptance;
- empty allowed-path rejection;
- legal and illegal transitions;
- allowed, forbidden, and out-of-scope paths;
- claims without proof;
- missing proof IDs;
- missing/mismatched evidence hashes;
- absolute local evidence rejection;
- replay evidence rejected for live claims;
- blockers in success states;
- blocked state without blocker;
- cycle exhaustion;
- failed required test in success state;
- compact context size guard;
- credential-field redaction;
- deterministic repair routing;
- duplicate task rejection;
- explicit checkpoint push requirement;
- no merge or auto-merge invocation.

## Acceptance Proof

Observed GitHub evidence at reviewed head `60b35afe024d10399b9c20ffb7e533f0996c4687`:

- Loop Handoff Gate: PASS.
- Framework focused suite: `21 passed` after portability repair.
- Example task contract, state, handoff, claims, evidence hash, and continuation packet validated by the new gate.
- Portfolio CI: PASS at the same reviewed head.
- The changed-file inventory contains only the declared infrastructure, documentation, test, example, and workflow paths.

Required final-head confirmation remains GitHub Actions on the commit containing this review document.

## Runtime Proof Required After Merge

No trading-runtime proof is required because this PR does not alter runtime behavior.

Post-merge operational pilot required before treating the framework as established process:

1. Initialize one bounded continuation task for PR #750.
2. Have one worker checkpoint partial work.
3. Have ChatGPT reconstruct the task using GitHub only.
4. Confirm no continuation-critical evidence remains local-only.
5. Confirm CI rejects one intentionally malformed test task in a controlled test fixture.
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

- all final-head workflows pass;
- final changed paths remain inside the documented boundary;
- the PR body is updated with the final head and test conclusions;
- an independent human or agent reviews the final diff.

Do not merge PR #764 as part of this implementation task.
