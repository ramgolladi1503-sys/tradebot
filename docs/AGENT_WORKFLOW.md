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
WAITING_HUMAN_APPROVAL
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
WAITING_HUMAN_APPROVAL
```

High risk does not mean forbidden. It means narrow scope, explicit human approval, and strong tests are mandatory.

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

## Local JSON Work Request Shape

Future local CLI/API work should accept payloads shaped like:

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
  "metadata": {
    "project": "tradebot"
  }
}
```

## Local CLI Acceptance Target

A later PR may add:

```bash
PYTHONPATH=. python scripts/submit_agent_work.py --payload docs/samples/gsd-agent-work.json
```

Expected output must include:

```text
scope_decision
approval_decision
evidence
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
