# Tradebot Agent Rules

This repository is a trading system. Agent-assisted work is allowed only when it improves safety, stability, test quality, paper/live readiness, or evidence quality. Agent-assisted work must not create fake progress, cosmetic PR churn, or hidden risk.

These rules apply to GSD, Hermes, Grill Me, Codex, ChatGPT, Claude, Gemini, and any other human- or AI-assisted coding workflow.

## Non-Negotiable Trading Safety Rules

Agents must never:

1. Place, modify, cancel, or exit orders.
2. Call broker APIs.
3. Change credentials, tokens, secrets, or environment files.
4. Disable or weaken risk gates.
5. Disable or weaken kill switches.
6. Disable or weaken feed freshness gates.
7. Add silent fallbacks that hide broken data.
8. Create fake happy-path-only mocks.
9. Weaken tests to make CI pass.
10. Touch unrelated files.
11. Add dashboard/UI work unless the PR explicitly requires it.
12. Change strategy thresholds unless the PR explicitly requires it and proves the behavior.
13. Introduce LIVE behavior in tests.
14. Blur SIM, PAPER, and LIVE boundaries.

Every safety-sensitive output must preserve or explicitly prove:

```text
read_only=true where applicable
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false unless explicitly scoped and human-approved
append=false where evidence/contracts are read-only
```

## Allowed Agent Roles

### Grill Me

Purpose: criticism, risk review, and fake-progress detection.

Allowed actions:

```text
CRITIQUE_SCOPE
REVIEW_PR
AUDIT_RISK
FIND_FAKE_PROGRESS
```

Forbidden actions:

```text
GENERATE_PATCH
PLACE_ORDER
MODIFY_ORDER
CANCEL_ORDER
ENABLE_LIVE
CHANGE_RISK
CHANGE_BROKER_CONFIG
```

### Hermes

Purpose: architecture, workflow, contract, and acceptance-gate design.

Allowed actions:

```text
DESIGN_ARCHITECTURE
DEFINE_CONTRACT
MAP_WORKFLOW
CREATE_ACCEPTANCE_GATES
UPDATE_DOCS
```

Forbidden actions:

```text
BROKER_CALL
LIVE_CONFIG_CHANGE
ORDER_ACTION
RISK_BYPASS
```

### GSD

Purpose: scoped execution after the work is approved.

Allowed actions:

```text
PLAN_PR
GENERATE_TESTS
GENERATE_PATCH
FIX_TEST_FAILURE
UPDATE_DOCS
```

Forbidden unless explicitly human-approved and scoped:

```text
RUNTIME_WIRING
STRATEGY_THRESHOLD_CHANGE
LIVE_MODE_CHANGE
BROKER_ADAPTER_CHANGE
```

Absolutely forbidden:

```text
PLACE_ORDER
MODIFY_ORDER
CANCEL_ORDER
DISABLE_RISK_GATE
DISABLE_KILL_SWITCH
DISABLE_FEED_FRESHNESS_GATE
```

## Required Agent Work Shape

Every agent task must declare:

```text
source_agent
action
title
scope
requested_paths
allowed_paths
forbidden_paths
expected_tests
acceptance_proof
```

A valid PR must include:

1. Files changed.
2. Design approach.
3. Risks.
4. Tests.
5. What was not touched.
6. Acceptance proof.
7. Final PR summary.

## PR Scope Discipline

Agents must prefer small, reviewable PRs.

Good:

```text
Add Agent Task Contract only.
Files: core/agent_work_contract.py, tests/test_agent_work_contract.py
No runtime wiring. No broker imports. No dashboard.
```

Bad:

```text
Make Tradebot agentic and improve profitability.
```

## Testing Rules

Tests must prove behavior, not only object shape.

Required examples:

1. Forbidden order actions are blocked.
2. Unsafe LIVE/risk/broker paths fail closed.
3. Docs/tests-only work can be accepted without runtime access.
4. High-risk runtime paths require human approval.
5. Evidence remains read-only and never claims broker calls.

Forbidden test behavior:

1. Skipping failing tests to pass CI.
2. Replacing behavior assertions with shallow snapshot checks only.
3. Mocking away the real safety decision.
4. Adding tests that prove only dataclass construction.

## Files Agents Must Treat as High Risk

Changes here require explicit human approval and narrow scope:

```text
main.py
run_live.sh
config/
credentials.py
core/execution*
core/broker*
core/order*
core/risk*
core/feed*
core/option_token_resolver.py
core/runtime_safety_boot_guard.py
strategies/
```

## Files Agents Must Not Touch Without Explicit Approval

```text
.env
*.env
credentials.py
runtime/live*
logs/broker*
secrets*
```

## Required Response Style for Agent Work

Agents must be direct. No generic encouragement. No vague roadmap dumping. No fake progress.

Every implementation response must answer:

```text
What changed?
Why does this move safety/stability/readiness forward?
What did not change?
What tests prove it?
What could still fail?
```

## Analytics Guardrails

1. Analytics code must never change live execution logic.
2. All analytics workflows must run offline and use `core.analytics.store` + `core.analytics.outcome_replay`.
3. Every new analytics module requires tests.
4. Always run `pytest -q` for analytics tests after changes.

## Daily Intelligence Report

```bash
# Default: yesterday (local timezone)
scripts/run_daily_intel.sh

# Explicit date
scripts/run_daily_intel.sh --date YYYY-MM-DD
```

## Running Live
Whenever the user asks to "run live" or start the live pipeline, you MUST execute `scripts/run_live_agentic.sh`. Do NOT use `run_live.sh` directly, as `run_live_agentic.sh` handles the required cleanup and environment variables to avoid lock deadlocks.
