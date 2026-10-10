# Tradebot Agent Workflow

## Goal

This workflow explains how GSD, Hermes, Grill Me, and other agents should contribute to Tradebot safely.

The workflow is intentionally boring.

A trading system does not need agents with direct execution power. It needs agents that can produce reviewable, testable, auditable work without touching broker/live paths.

## Standard Flow

```text
1. Human defines project objective.
2. Grill Me critiques the objective or PR scope.
3. Hermes converts approved intent into architecture/contracts/gates.
4. GSD implements one narrow approved task.
5. Tests prove behavior.
6. Evidence records the safety decision.
7. Human reviews and merges.
```

## Agent Work Lifecycle

```text
SUBMITTED
  ↓
VALIDATED_BY_SCOPE_GUARD
  ↓
WAITING_HUMAN_APPROVAL or APPROVED_FOR_PATCH or BLOCKED
  ↓
APPROVED_FOR_PATCH or REJECTED
  ↓
PATCH_PROPOSED
  ↓
TESTED
  ↓
HUMAN_REVIEWED
  ↓
MERGED or REJECTED
```

## Decision Rules

### LOW Risk

Docs/tests-only work.

Examples:

```text
docs/AGENT_WORKFLOW.md
tests/test_agent_scope_guard.py
```

Decision:

```text
APPROVED_FOR_PATCH
```

### MEDIUM Risk

Production code that does not touch trading execution, broker, risk, feed, credentials, or live startup.

Examples:

```text
core/agent_work_contract.py
core/agent_evidence.py
```

Decision:

```text
BLOCKED_PENDING_AUTHENTICATED_APPROVAL
```

### HIGH Risk

Runtime, broker, risk, execution, feed, strategy, option resolver, or live startup code.

Examples:

```text
main.py
run_live.sh
core/risk/*
core/execution*
core/broker*
core/feed*
strategies/*
```

Decision:

```text
BLOCKED_PENDING_AUTHENTICATED_APPROVAL
```

Medium/high risk is blocked at the current local CLIs. Caller-provided
`--approve` and `--approved-by` values do not authenticate a human. A future
authenticated approval integration must be independently reviewed before this
work can be admitted.

### BLOCKED

Forbidden or malformed work.

Examples:

```text
p_lace_order
ENABLE_LIVE
DISABLE_RISK_GATE
CHANGE_BROKER_CONFIG
credentials.py
.env
```

Decision:

```text
BLOCKED
```

Blocked work cannot be approved.

## Required Prompt Template for Agents

Use this when asking an agent to help Tradebot:

```text
Project: Tradebot

Task type:
[CRITIQUE_SCOPE / DESIGN_ARCHITECTURE / GENERATE_TESTS / GENERATE_PATCH / REVIEW_PR]

Scope:
[one narrow task only]

Allowed files:
[list paths]

Forbidden files:
[list paths]

Hard rules:
- No broker calls
- No order placement
- No LIVE behavior
- No credentials changes
- No risk bypass
- No unrelated refactors
- No dashboard unless scoped
- No weak tests
- No silent fallback

Expected output:
1. Files changed
2. Design approach
3. Tests
4. Risks
5. What not touched
6. Acceptance proof
```

## GSD Workflow

Use GSD only after scope is clean.

Good GSD task:

```text
Implement Agent Work Contract only.
Files allowed:
- core/agent_work_contract.py
- tests/test_agent_work_contract.py
No runtime wiring. No broker imports. No dashboard.
```

Bad GSD task:

```text
Make Tradebot agentic and improve profitability.
```

GSD output must be rejected if it:

1. Touches unapproved files.
2. Changes runtime behavior outside scope.
3. Adds fake mocks.
4. Weakens tests.
5. Adds order/live/broker behavior.

## Hermes Workflow

Use Hermes for design before implementation.

Good Hermes task:

```text
Design the Agent Work Contract and Scope Guard for Tradebot.
No implementation. Define fields, states, blockers, tests, and acceptance gates.
```

Hermes output must be rejected if it:

1. Adds direct execution power to agents.
2. Skips evidence.
3. Skips human approval for high-risk code.
4. Blurs paper/live boundaries.

## Grill Me Workflow

Use Grill Me to find weaknesses.

Good Grill Me task:

```text
Review this proposed PR scope. Find fake progress, overengineering, weak tests, safety gaps, and live/paper boundary risks. Final decision: Approve / Rewrite / Reject.
```

Grill Me output must be rejected if it:

1. Gives vague motivation.
2. Does not make a decision.
3. Does not identify concrete risks.
4. Suggests broad unscoped rewrites.

## Local CLI admission requirement

The supported local entrypoints are `scripts/submit_agent_work.py` and the
state-mutating `preflight`, `claim`, `verify`, `review`, and `release` commands
in `scripts/agent_supervisor.py`. Before a mutating supervisor command proceeds,
the payload must reference a committed canonical item
under `governance/evidence/work_items/` and one exact task contract stored in
that item. Admission checks the tracked `HEAD` blob, the clean work-item path,
its SHA-256, full delivery schema, task contract ID, source/action/title/scope,
and exact requested/allowed/forbidden paths. A missing, dirty, stale, malformed,
or mismatched record blocks.

Supervisor admission is repeated for each mutation command. A successful
preflight or claim is not a reusable authorization token. `status` is a
read-only inspection command: it does not run admission and does not mean the
task is admitted or authorized. Admission proves repository binding only; it
does not provide authenticated human approval. Medium/high-risk work remains
blocked until an authenticated approval mechanism is independently implemented
and verified. Universal platform intake and branch-protection enforcement
remain `UNSATISFIED`.

To prepare a task, create or update its delivery item and task contract, pass
the ordinary delivery review gates, commit it, then place its path, ID, task
contract ID, and SHA-256 in `metadata.delivery_work_item`. The hash is of the
exact committed JSON bytes. If the task contract changes, recommit it and
update the reference. Do not create lifecycle evidence or move delivery states
to get admission.

The supported payload shape includes:

```json
{
  "source_agent": "gsd",
  "action": "GENERATE_TESTS",
  "title": "Add tests for Agent Scope Guard",
  "scope": "Add behavior tests proving forbidden paths and order actions are blocked.",
  "allowed_paths": ["tests/"],
  "requested_paths": ["tests/test_agent_scope_guard.py"],
  "forbidden_paths": ["credentials.py", ".env", "core/broker", "core/execution"],
  "requires_human_approval": false,
  "expected_tests": ["PYTHONPATH=. pytest -q tests/test_agent_scope_guard.py"],
  "acceptance_proof": ["Unsafe paths and actions are blocked."],
  "metadata": {
    "project": "tradebot",
    "delivery_work_item": {
      "work_item_id": "<committed-item-id>",
      "path": "governance/evidence/work_items/<item>.json",
      "sha256": "<sha256-of-committed-json-bytes>",
      "task_contract_id": "<task-contract-id-in-the-item>"
    }
  }
}
```

The delivery item must embed the matching task contract fields. The payload is
not admitted merely because its caller supplied plausible fields or a hash.
The hash binds bytes and identity; it does not authenticate who authored or
approved the record.

## Local CLI behavior

```bash
PYTHONPATH=. python scripts/submit_agent_work.py --payload docs/samples/gsd-agent-work.json
```

The CLI writes audit evidence for the submitted request and admission decision.
If evidence writing fails, the request is rejected. `--no-evidence` is a
diagnostic mode and cannot return accepted. The `--approve` and `--approved-by`
arguments are caller assertions, not authenticated identity. Medium/high-risk
patch work remains blocked until a real authenticated approval integration is
implemented and independently verified.

These local checks do not intercept direct Codex, ChatGPT, Claude, Gemini,
GitHub issue/comment, Actions, MCP, or other platform requests. The current
workflow inventory records each of the 17 active `workflow_dispatch` workflows
as `UNSATISFIED` for pre-work admission. Two retired triggers are recorded
separately: the PR818 test-repair workflow was retired after its change merged
in PR823, and the frozen-head certification workflow's caller-selectable manual
trigger was removed while its PR-time checks were retained. Universal intake
and branch-protection enforcement remain `UNSATISFIED`.

Accepted output continues to expose:

```text
scope_decision
approval_decision
admission_decision
evidence_result
read_only=true
is_order_action=false
broker_api_called=false
live_mode_touched=false
```

## What Must Stay Out of This Workflow For Now

Do not add yet:

1. Agent dashboard.
2. Mobile approval screen.
3. Public webhooks.
4. Auto-merge bot.
5. Agent-triggered paper orders.
6. Agent-triggered live config.
7. Agent access to broker credentials.
8. Agent access to runtime trading state mutation.

## Review Checklist

Before accepting an agent-generated PR, answer:

```text
Does it improve safety, stability, evidence, tests, paper/live readiness, or profitability validation?
Does it preserve SIM/PAPER/LIVE separation?
Does it avoid broker calls?
Does it avoid order actions?
Does it avoid hidden fallback behavior?
Does it include behavior-proving tests?
Does it avoid unrelated cleanup?
Does it include acceptance proof?
```

If any answer is no, reject or rewrite the PR.
