# Tradebot Agent Worktree Supervisor Review

## Agent Work Contract

**Objective:** Extend the existing local agent work controls with deterministic worktree identity, exclusive file ownership, frozen-contract integrity, acceptance-command evidence, independent review, and release gates.

**Implementation branch:** `agent/tradebot-worktree-supervisor`

**Base:** `main` at `f9a8ad7d8032254b7869bc115d92cbda53d36a00`

**Allowed scope:**

- `core/agent_supervisor*.py`
- `scripts/agent_supervisor.py`
- `tests/test_agent_supervisor.py`
- `docs/AGENT_SUPERVISOR.md`
- `docs/samples/*supervisor*.json`
- this review record

**Forbidden scope:** strategy logic, market feed, broker integration, execution, risk, credentials, live startup, workflow mutation, and automatic merge behavior.

## Scope Guard

The branch adds only the local engineering supervisor, focused tests, documentation, samples, and this evidence record. It does not edit existing trading runtime modules or replace the existing `agent_work_contract`, `agent_scope_guard`, or `agent_approval` policies.

The supervisor itself fails closed on malformed contracts, direct `main`/`master` work, dirty or mismatched worktrees, overlapping ownership, prohibited paths, frozen-path mutations, unsafe acceptance commands, missing artifacts, invalid manifests, non-independent review, and release without review approval.

## Grill Me Review

The design was challenged for fake parallelism, self-certification, broad ownership, unverifiable command claims, manifest tampering, and accidental live access.

Concrete controls added:

1. Ownership claims live under the shared Git common directory, so separate worktrees cannot silently claim overlapping files.
2. The implementation manifest is re-hashed during review; the reviewer cannot approve a modified manifest merely by echoing its stored hash.
3. Implementer and reviewer identities must differ.
4. Acceptance commands are argument arrays with an allowlist; known live/order scripts, inline Python, mutating Git operations, and explicit trading actions are blocked.
5. Claims remain held through verified and reviewed states until explicit release.

Decision: **APPROVE FOR DRAFT PR REVIEW ONLY**.

## Hermes Review

The implementation extends the repository’s existing agent-control layers instead of creating a competing architecture.

Lifecycle:

```text
PREFLIGHT_READY
  -> CLAIMED
  -> VERIFIED
  -> REVIEW_APPROVED
  -> RELEASED
```

Blocked, verification-failed, rewrite, rejected, and needs-human states stop normal progression. Approval grants engineering-patch progression only; it never grants runtime wiring or live execution.

Decision: **ARCHITECTURE CONSISTENT WITH EXISTING SAFETY BOUNDARIES**.

## GSD Review

Implementation is split into narrow responsibilities:

- public facade and types
- contract normalization and preflight
- Git, hashing, safe command execution, and evidence helpers
- shared worktree claim registry
- implementation and review evidence gates
- local CLI
- focused behavior tests

The implementation does not launch external agents. Codex remains the primary implementation agent by workflow convention, while Antigravity may act as an independent reviewer only from a separate worktree/context.

Decision: **IMPLEMENTATION SCOPE ACCEPTABLE FOR CI AND HUMAN REVIEW**.

## QA / Safety Review

Focused tests prove:

1. same implementer/reviewer is rejected;
2. known live-script acceptance commands are blocked;
3. preflight requires a clean, matching isolated branch;
4. repeat claims are idempotent for the same identity;
5. overlapping ownership is blocked across real Git worktrees;
6. successful verification records commit, command, artifact, and hash evidence;
7. failing acceptance commands fail verification;
8. frozen-path changes fail verification;
9. independent review requires matching commit/manifest identity and reproduction evidence;
10. release requires approved review unless forced release is explicitly recorded;
11. result objects are JSON serializable;
12. tampered implementation manifests are rejected;
13. JSON contract loading is covered.

Safety assertions remain explicit in every result:

- `is_order_action=false`
- `broker_api_called=false`
- `live_mode_touched=false`
- `allowed_for_runtime_wiring=false`
- `allowed_for_live_execution=false`
- `auto_merge_enabled=false`

Decision: **QA EVIDENCE SUFFICIENT FOR DRAFT PR; FULL REPOSITORY CI REMAINS AUTHORITATIVE**.

## Acceptance Proof

Executed against the isolated implementation package before publication:

```text
PYTHONPATH=. pytest -q
13 passed
```

Additional checks:

```text
python -m py_compile core/agent_supervisor*.py scripts/agent_supervisor.py
python -m json.tool docs/samples/codex-supervisor-task.json
python -m json.tool docs/samples/antigravity-supervisor-review.json
```

All completed successfully.

GitHub comparison before this evidence update showed the branch ahead of `main` with only new supervisor, test, documentation, and sample files. No strategy, feed, broker, execution, risk, credential, live-startup, or workflow file was changed.

## Runtime Proof Required After Merge

No trading-runtime proof is required because this change is not wired into Tradebot runtime. Post-merge operational proof should instead use one real, low-risk docs/tests task in two isolated worktrees to demonstrate:

1. the first task acquires ownership;
2. a deliberately overlapping second task is blocked;
3. implementation verification binds evidence to the committed head;
4. a fresh reviewer reproduces the acceptance command;
5. ownership is released only after review approval.

This proof must remain offline and must not use broker credentials or live market processes.

## What This PR Does Not Prove

This PR does not prove autonomous agent execution, cryptographic reviewer identity, automatic retry/fix loops, safe remote webhooks, mobile approvals, PR creation/merge automation, trading profitability, paper-order safety, or live-order safety.

The command policy is a guardrail, not an operating-system sandbox. Task authors must still use narrow commands and exact ownership paths.

## Human Approval

Ram explicitly requested that this local supervisor be built for Tradebot. That request authorizes implementation and creation of a **draft** pull request only.

No approval has been granted to mark the PR ready, merge it, connect external agents automatically, add webhooks/dashboard/mobile controls, or touch paper/live trading behavior. Those remain separate human decisions after CI and review evidence are complete.
