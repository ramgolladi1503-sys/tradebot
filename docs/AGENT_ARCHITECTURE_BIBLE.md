# Tradebot Agent Architecture Bible

## Purpose

Tradebot can use external and local agents such as GSD, Hermes, Grill Me, Codex, ChatGPT, Claude, and Gemini only as controlled engineering assistants.

Agents are not trading actors.

The architecture exists to let agents propose, critique, design, test, and document work without giving them any path to place orders, bypass risk, or touch live trading behavior.

## Core Principle

```text
Agents may create work requests.
Agents may not create trades.
```

The correct flow is:

```text
GSD / Hermes / Grill Me / Codex / ChatGPT
        ↓
Agent Work Request
        ↓
Scope Guard
        ↓
Approval Decision
        ↓
Evidence Journal
        ↓
Human-reviewed PR
        ↓
CI + acceptance proof
```

The forbidden flow is:

```text
Agent
  → signal
  → broker adapter
  → order
```

That path must not exist.

## Agent Sources

### Grill Me

Grill Me is a critic. It is useful before and after a PR.

Allowed use:

1. Destroy weak scope.
2. Find fake progress.
3. Review PR risk.
4. Identify overengineering.
5. Challenge strategy or product assumptions.

Forbidden use:

1. Generate patches.
2. Touch runtime code.
3. Approve broker/live changes.
4. Tune trading thresholds.

### Hermes

Hermes is an architect. It converts messy intent into contracts, workflows, and acceptance gates.

Allowed use:

1. Design agent workflow.
2. Define payload contracts.
3. Define state machines.
4. Define acceptance tests.
5. Create docs and runbooks.

Forbidden use:

1. Broker calls.
2. Runtime execution wiring.
3. Live configuration changes.
4. Risk bypass.

### GSD

GSD is an execution helper. It gets tightly scoped implementation work after scope is approved.

Allowed use:

1. Add tests.
2. Implement one small PR.
3. Fix a specific CI failure.
4. Update docs.
5. Generate a small isolated patch.

Forbidden use:

1. Broad rewrites.
2. Unscoped refactors.
3. Live behavior changes.
4. Broker adapter edits without explicit approval.
5. Risk gate changes without explicit approval.

## Agent Work Request Contract

Every agent request must eventually be represented as a structured work item with:

```text
schema_version
source_agent
action
title
scope
requested_paths
allowed_paths
forbidden_paths
requires_human_approval
metadata
```

The request itself is not executable. It is input to a scope guard.

## Scope Guard Responsibility

The scope guard must fail closed.

It must block:

1. Order actions.
2. Broker actions.
3. LIVE enablement.
4. Credential changes.
5. Risk bypasses.
6. Kill-switch bypasses.
7. Feed freshness bypasses.
8. Unknown agent sources.
9. Unknown or forbidden actions.
10. Requested files outside allowed paths.
11. Explicitly forbidden paths.

It must classify work as:

```text
LOW     → docs/tests-only work that can be patch-approved
MEDIUM  → production code that needs human approval
HIGH    → runtime/risk/execution code that needs explicit human approval
BLOCKED → forbidden or malformed work
```

## Approval Responsibility

Approval must not mean runtime permission.

An approved agent task can only mean:

```text
allowed_for_patch=true
allowed_for_runtime_wiring=false
allowed_for_live_execution=false
is_order_action=false
broker_api_called=false
```

High-risk changes require human approval even if the scope guard accepts the request.

Blocked work cannot be approved.

## Evidence Responsibility

Every accepted or blocked agent request should be auditable.

Evidence should record:

```text
agent_work_id
source_agent
action
scope_decision
approval_decision
requested_paths
allowed_paths
forbidden_paths
blockers
warnings
reasons
read_only=true
is_order_action=false
broker_api_called=false
live_mode_touched=false
```

Evidence belongs under:

```text
runtime/agent_work/agent_work_latest.json
runtime/agent_work/agent_work_YYYY-MM-DD.jsonl
```

Evidence must not mutate trading state.

## Integration Boundaries

### Phase 1: Repo Rules

Docs only.

Files:

```text
AGENTS.md
docs/AGENT_ARCHITECTURE_BIBLE.md
docs/AGENT_WORKFLOW.md
```

### Phase 2: Local Contract

Pure Python contracts and tests only.

Files:

```text
core/agent_work_contract.py
core/agent_scope_guard.py
core/agent_approval.py
core/agent_evidence.py
tests/test_agent_*.py
```

### Phase 3: Local CLI

Submit local JSON work requests through a CLI.

Files:

```text
scripts/submit_agent_work.py
docs/samples/*agent-work*.json
```

### Phase 4: API/Webhook

Only after local contract is proven.

Allowed later:

```text
POST /agent/work
GET /agent/work/{id}
```

Still forbidden:

```text
agent → order
agent → broker
agent → LIVE enablement
```

### Phase 5: Dashboard or Mobile Approval

Only after the API/webhook layer is safe and tested.

No dashboard work belongs in Phase 1.

## Acceptance Gates

Agent architecture is acceptable only when tests prove:

1. Grill Me cannot generate patches.
2. Hermes cannot request broker/live actions.
3. GSD can generate tests inside allowed paths.
4. Order actions are blocked.
5. Credential paths are blocked.
6. High-risk runtime paths require human approval.
7. Approval never grants live execution.
8. Evidence always records `is_order_action=false`.
9. Evidence always records `broker_api_called=false`.
10. Blocked work cannot be approved.

## What This Architecture Does Not Do

It does not:

1. Make Tradebot profitable.
2. Improve strategy edge directly.
3. Place paper orders.
4. Place live orders.
5. Replace human review.
6. Replace CI.
7. Replace risk management.
8. Justify bigger PRs.

## Hard Truth

Agent architecture is useful only if it reduces chaos.

If it becomes another excuse for vague PRs, dashboard polish, or fake progress, it should be deleted or frozen.

The immediate goal is not automation. The immediate goal is controlled contribution.
