# Tradebot Agent Worktree Supervisor

## Purpose

The supervisor turns an already-approved Tradebot engineering task into a local,
auditable workflow:

```text
preflight -> claim -> implement -> verify -> independent review -> release
```

It is deliberately not an agent launcher. It does not call Codex, Antigravity,
Claude, or any other model. It does not merge branches, call brokers, place
orders, enable LIVE mode, change credentials, or mutate trading runtime state.

The supervisor exists to stop four recurring failure modes:

1. Two agents editing overlapping files in different worktrees.
2. An agent claiming completion with a dirty or mismatched branch.
3. Acceptance evidence that cannot be reproduced or tied to a commit.
4. The implementation agent approving its own work.

## What it enforces

### Worktree identity

A task contract names an absolute worktree path, isolated branch, and base ref.
Preflight fails when the path is not the repository root, the branch differs,
the worktree is dirty, or the task targets `main`/`master` directly.

### Exclusive ownership

Claims are stored under the repository's shared Git common directory:

```text
<git-common-dir>/agent-supervisor/claims.json
```

All worktrees for the same repository see the same registry. A second task is
blocked when its `ownership_paths` overlap any unreleased claim.

### Frozen contracts

`frozen_paths` are hashed when the task is claimed. Verification compares the
current hashes with the claim-time hashes. A changed frozen path fails closed,
even when the path was changed in a committed patch.

### Safe acceptance commands

Commands are arrays of arguments, never shell strings. The supervisor allows a
small verification-oriented executable set and blocks known live/order scripts,
inline Python, mutating Git commands, and explicit trading actions. Broker,
Telegram, SMTP, and access-token environment variables are removed before each
command. Safe offline values are injected.

This is a guardrail, not a sandbox. The task author must still keep acceptance
commands narrow and reviewable.

### Evidence manifests

Verification writes:

```text
.runtime/agent_supervisor/evidence/<task-id>/implementation_manifest.json
```

The manifest records base/head commits, changed paths, command argv, exit codes,
timeouts, output hashes/tails, frozen-path hashes, artifact hashes, blockers, and
a deterministic manifest SHA-256.

Independent review writes:

```text
.runtime/agent_supervisor/evidence/<task-id>/review_manifest.json
```

Review approval is blocked unless the reviewer identity differs from the
implementer, commit identities match, the implementation manifest hash is
valid, and reproduction evidence reports successful exit codes.

## Task contract

The supervisor extends the existing Agent Work Request JSON instead of replacing
it. The existing fields still go through `agent_work_contract`,
`agent_scope_guard`, and `agent_approval`.

```json
{
  "schema_version": 1,
  "source_agent": "codex",
  "action": "GENERATE_PATCH",
  "title": "Harden reconnect resource verification",
  "scope": "Add one deterministic verifier without changing feed runtime behavior.",
  "requested_paths": [
    "scripts/verify_feed_reconnect_resources.py",
    "tests/test_feed_reconnect_resource_verifier.py"
  ],
  "allowed_paths": ["scripts/", "tests/"],
  "forbidden_paths": [
    ".env",
    "credentials.py",
    "main.py",
    "core/broker",
    "core/execution",
    "core/risk",
    "strategies/"
  ],
  "requires_human_approval": true,
  "metadata": {"project": "tradebot"},
  "supervisor": {
    "schema_version": 1,
    "task_id": "feed-reconnect-resource-verifier",
    "implementer": "codex",
    "reviewer": "antigravity",
    "worktree_path": "/absolute/path/to/tradebot-feed-reconnect-resource-verifier",
    "branch": "agent/feed-reconnect-resource-verifier",
    "base_ref": "main",
    "ownership_paths": [
      "scripts/verify_feed_reconnect_resources.py",
      "tests/test_feed_reconnect_resource_verifier.py"
    ],
    "frozen_paths": [
      "core/feed_manager.py",
      "core/risk_manager.py",
      "strategies/"
    ],
    "acceptance_commands": [
      {
        "name": "focused-tests",
        "argv": [
          "python",
          "-m",
          "pytest",
          "tests/test_feed_reconnect_resource_verifier.py",
          "-q"
        ],
        "timeout_seconds": 900
      }
    ],
    "required_artifacts": [
      "scripts/verify_feed_reconnect_resources.py",
      "tests/test_feed_reconnect_resource_verifier.py"
    ],
    "require_clean_worktree": true,
    "require_committed_head": true
  }
}
```

`ownership_paths` should be the smallest exact set an agent may own. Do not use
`core/`, `tests/`, or `scripts/` broadly unless the task truly owns the entire
directory; broad ownership destroys safe parallelism.

## Local workflow

### 1. Create an isolated worktree

```bash
git fetch origin
git worktree add \
  /absolute/path/to/tradebot-feed-reconnect-resource-verifier \
  -b agent/feed-reconnect-resource-verifier \
  origin/main
```

### 2. Preflight the contract

Docs/tests-only work may pass without explicit approval. Medium/high-risk patch
scope requires `--approve` and an approver identity.

```bash
PYTHONPATH=. python scripts/agent_supervisor.py preflight \
  --contract docs/samples/codex-supervisor-task.json \
  --approve \
  --approved-by ram
```

### 3. Claim file ownership

```bash
PYTHONPATH=. python scripts/agent_supervisor.py claim \
  --contract docs/samples/codex-supervisor-task.json \
  --approve \
  --approved-by ram
```

Do not start the implementation agent unless the result is
`SUPERVISOR_CLAIMED` with `accepted=true`.

### 4. Implement and commit inside the named worktree

The supervisor does not launch the agent. Give Codex the approved contract and
make it work only in the claimed worktree. The final implementation must be
committed and the worktree must be clean.

### 5. Verify implementation evidence

```bash
PYTHONPATH=. python scripts/agent_supervisor.py verify \
  --contract docs/samples/codex-supervisor-task.json
```

Do not ask the reviewer to approve a failed implementation manifest.

### 6. Run a fresh-context independent review

The reviewer must inspect the exact `base_commit`, `head_commit`, and
`manifest_sha256` from `implementation_manifest.json`, rerun the required checks,
and write a review payload shaped like `docs/samples/antigravity-supervisor-review.json`.

```bash
PYTHONPATH=. python scripts/agent_supervisor.py review \
  --contract docs/samples/codex-supervisor-task.json \
  --review docs/samples/antigravity-supervisor-review.json
```

Only `SUPERVISOR_REVIEW_APPROVED` means the independent gate passed. `REWRITE`,
`REJECT`, and `NEEDS_HUMAN` remain fail-closed.

### 7. Release ownership

```bash
PYTHONPATH=. python scripts/agent_supervisor.py release \
  --contract docs/samples/codex-supervisor-task.json
```

Normal release requires approved independent review. `--force` exists only for
abandoned or broken tasks and is explicitly recorded as a forced release.

## Review payload

```json
{
  "schema_version": 1,
  "task_id": "feed-reconnect-resource-verifier",
  "reviewer": "antigravity",
  "decision": "APPROVE",
  "summary": "Reproduced the focused test and found no scope or frozen-contract violation.",
  "base_commit": "copy-from-implementation-manifest",
  "head_commit": "copy-from-implementation-manifest",
  "implementation_manifest_sha256": "copy-from-implementation-manifest",
  "reproduction_results": [
    {
      "name": "focused-tests",
      "exit_code": 0
    }
  ],
  "findings": [],
  "required_changes": []
}
```

The current implementation records reproduction evidence but cannot prove which
external model executed the commands. Treat reviewer identity as an auditable
assertion, not cryptographic authentication.

## States

```text
SUPERVISOR_PREFLIGHT_READY
SUPERVISOR_CLAIMED
SUPERVISOR_VERIFIED
SUPERVISOR_REVIEW_APPROVED
SUPERVISOR_RELEASED
```

Any blocked, failed, rewrite, rejected, or needs-human state stops progression.

## Explicit non-goals

This version does not provide:

1. Autonomous Codex/Antigravity process launching.
2. A retry loop that edits code automatically.
3. Git commit, push, PR creation, or merge automation.
4. A dashboard, phone approval, webhook, or remote terminal.
5. Runtime access, broker credentials, paper orders, or live orders.

Those features should not be added until this local supervisor survives real
Tradebot use without scope bypasses, stale claims, or unverifiable evidence.
