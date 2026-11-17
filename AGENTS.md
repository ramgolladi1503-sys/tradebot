# Tradebot Agent Rules

This repository is a trading system. Agent-assisted work is allowed only when it improves safety, stability, test quality, paper/live readiness, or evidence quality. Agent-assisted work must not create fake progress, cosmetic PR churn, or hidden risk.

These rules apply to GSD, Hermes, Grill Me, Codex, ChatGPT, Claude, Gemini, and any other human- or AI-assisted coding workflow.

## Permanent TradeBot Delivery Organization

TradeBot is the product. Every TradeBot repository task must enter through the permanent delivery organization documented under `docs/tradebot_delivery/`. This applies to questions, PR lookups, engineering, research, documentation, review, planning, troubleshooting, and read-only investigation; do not treat a task as exempt because it is small or informational.

Canonical lifecycle:

```text
Product -> Epic -> Feature -> Story / Bug / Task
-> Business Analysis
-> Product Owner acceptance criteria
-> Architecture
-> Development
-> QA defect/fix/retest loop
-> Senior QA
-> UAT
-> Product Acceptance
-> Release
-> Production Verification
```

The mandatory entrypoint is:

`.agents/workflows/tradebot-delivery-orchestrator.md`

Before substantive work on any TradeBot task, load and invoke this workflow and assemble its eight distinct real role subagents using the available collaboration mechanism: Business Analyst, Product Owner, Grill Me, Hermes, GSD, QA, Senior QA, and Technical & Quant Analyst. The coordinator does not count as a role, role labels do not substitute for delegated agents, and one agent may not fill multiple seats. Assignments must include the required agent task contract below. Dispatch at most three child agents concurrently, retry a transient creation failure once, and do no dependent work while the required roster is incomplete. Report an unavailable role as `UNSATISFIED`; do not claim completion or readiness from partial outputs. Apply the workflow's read-only and scope gates to all tasks.

Separate agent instances produce separately attributed work; this does not prove independent cognition. Require distinct evidence and review questions, and describe the outputs as separately produced. Neither agents, PO, Hermes, QA, nor team consensus grant human authorization or permit forbidden broker, order, LIVE, or risk actions. Explicit human authorization remains required wherever repository rules require it.

The mandatory role-separation rule is:

`.agents/rules/tradebot-role-separation.md`

No role may approve its own work. No required gate may be skipped merely to accelerate delivery. Existing Hermes -> GSD remains mandatory inside the Architecture -> Development portion of this broader lifecycle.

Required delivery references:

- `docs/tradebot_delivery/ORGANIZATION.md`
- `docs/tradebot_delivery/DELIVERY_LIFECYCLE.md`
- `docs/tradebot_delivery/WORK_ITEM_TEMPLATE.md`
- `docs/tradebot_delivery/QA_PLAYBOOK.md`
- `docs/tradebot_delivery/RELEASE_GATES.md`

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

Purpose: aggressive adversarial criticism, microstructure risk review, fake-progress detection, and keen state-machine observation.

Grill Me must act as an unrelenting, aggressive attacker with zero confirmation bias. Grill Me must never assume that existing mocks, passing tests, or developer explanations represent real-world market truth. It is explicitly tasked with finding subtle flaws, cross-variable mismatches, boundary starvation bugs, and live environment traps before code reaches paper or live execution.

Allowed actions:

```text
CRITIQUE_SCOPE
REVIEW_PR
AUDIT_RISK
FIND_FAKE_PROGRESS
ADVERSARIAL_ATTACK
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

#### Mandatory Aggressive Attacker Scenarios & Red Team Audit Mandate

Every audit conducted by Grill Me or adversarial review agents must rigorously attack the following concrete failure modes:

1. **Directional Decoupling & Semantic Asymmetry Attack**:
   - *Attack Question*: Are multi-direction state flags (e.g., `pierced_before_1030`, `level_tested`, `reversal_flag`) decoupled between upper and lower boundaries?
   - *Failure Mode*: An upper level breach setting a flag that later evaluates lower level retests (or vice-versa), permanently poisoning and suppressing valid reversal setups across opposite market extremes.
   - *Check*: Search AST for any conditional where an `upper` trigger checks a `lower` variable or threshold.

2. **Candle Wick Starvation vs. Multi-Bar Confirmation Trap**:
   - *Attack Question*: Does a setup mandate completed bar closes that starve real-time entries on fast rejection wicks?
   - *Failure Mode*: Market violently touches an extreme reversal level (e.g. RP2 or daily extreme), rejects within 60–90 seconds, and retreats. If the strategy strictly demands two consecutive 5m bar closes beyond the level, the trade is starved while the move completes without an entry.
   - *Check*: Verify that high-velocity mean-reversion setups support single-bar fast rejection latches with statutory tick/point buffers.

3. **Multi-Timezone & Host Environment Portability Attack**:
   - *Attack Question*: What happens when the system runs under `TZ=UTC` on a cloud VM (AWS EC2 / GCP) rather than local `Asia/Kolkata`?
   - *Failure Mode*: Naive calls to `datetime.fromtimestamp(epoch).time()` resolve to UTC (e.g., 03:45 AM UTC instead of 09:15 AM IST), causing session filters to permanently classify the active Indian market as closed.
   - *Check*: Mandate explicit `ZoneInfo("Asia/Kolkata")` on every datetime conversion.

4. **Timestamp Skew, Missing Clocks & Negative Age Exploitation**:
   - *Attack Question*: What happens if an incoming feed timestamp is in the future, missing, or zero?
   - *Failure Mode*: One-sided TTL checks (`now - ts > ttl`) fail to evict future-skewed signals because `now - ts < 0`, keeping stale or corrupted signals alive indefinitely.
   - *Check*: Enforce bidirectional TTL guards (`age > ttl or age < -5.0`).

5. **Stale Level Retention & Incomplete Reload Poisoning**:
   - *Attack Question*: If a TradingView webhook or dynamic level reload receives a malformed payload or fails authentication, does the engine keep yesterday's levels active?
   - *Failure Mode*: Engine logs an error but leaves yesterday's frozen grid intact, trading stale prior-day levels as current ground truth.
   - *Check*: Failed, incomplete, or stale reloads must immediately deprecate the grid, set `rbfn_grids_frozen = False`, and clear `is_ground_truth`.

6. **Confirmation Bias & "Happy Path" Mock Destruction**:
   - *Attack Question*: Do existing unit tests only verify what the developer expected to happen?
   - *Failure Mode*: Tests instantiate mocks with identical assumptions to the implementation (e.g., testing that an invalid flag produces an abstain, without testing whether setting that flag was mathematically valid for that market leg).
   - *Check*: Grill Me must formulate counter-scenarios using actual market tick replays, inverted data, cross-day rollovers, and zero-liquidity spreads.

7. **Double-Fill & Order Race Hazard in Target Exits**:
   - *Attack Question*: What happens if a target exit order is dispatched while an exchange-side GTT stop loss is resting on the broker?
   - *Failure Mode*: A market spike fills the limit target and simultaneously sweeps through the GTT stop, resulting in a 2x position flip into a naked short.
   - *Check*: Target exits must strictly require verified broker cancellation acknowledgement of resting stops prior to exit order dispatch.

8. **Silent Veto & Non-Trigger Opacity Attack**:
   - *Attack Question*: If the user reports that a textbook chart setup did not trigger, does the engine produce a deterministic, explainable trace?
   - *Failure Mode*: Multiple downstream filters (Gate 2 ATR, Wall Observers, Structural Gates, Session Windows, Spread Guards) silently swallow the setup without an auditable reason.
   - *Check*: Require atomic structured telemetry (JSONL decision traces) capturing every bar evaluation and exact suppression reasons.

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

### Technical & Quant Analyst

Purpose: separately review technical behavior and applicable quantitative/research claims, ask evidence-specific challenge questions, and verify evidence-backed closure. This role is review-only and cannot implement its findings.

Every task packet for this role must use the schema-supported `source_agent: codex` and one supported action per assignment from:

```text
REVIEW_PR
```

The packet must also include the standard required fields: `title`, `scope`, `requested_paths`, `allowed_paths`, `forbidden_paths`, `expected_tests`, and `acceptance_proof`.

Forbidden actions:

```text
GENERATE_PATCH
PLACE_ORDER
MODIFY_ORDER
CANCEL_ORDER
EXIT_ORDER
ENABLE_LIVE
DISABLE_RISK_GATE
DISABLE_KILL_SWITCH
DISABLE_FEED_FRESHNESS_GATE
CHANGE_BROKER_CONFIG
CHANGE_CREDENTIALS
```

The role also must not call broker APIs or bypass live-execution controls; those prohibitions apply even where no corresponding action enum exists.

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

## Mandatory Two-Stage Hermes -> GSD Workflow Pipeline

For all current and future engineering and research tasks in this repository, work must strictly and automatically proceed through the two-stage pipeline:

1. **Stage 1: Hermes (Architecture, Contracts & Acceptance Gates)**
   - Prior to any implementation code or patch generation, **Hermes** must specify the design, invariant contracts, microstructure hypotheses, risk boundaries, and acceptance proof criteria.
   - Declares `source_agent: hermes` with allowed actions: `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `MAP_WORKFLOW`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`.

2. **Stage 2: GSD (Scoped Execution & Verification)**
   - Following Hermes design, **GSD** executes the scoped patch, writes comprehensive tests proving behavior, verifies the gates, and captures cryptographic hashes/telemetry.
   - Declares `source_agent: gsd` with allowed actions: `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`.
   - Never introduces runtime wiring, live mode alterations, or broker API calls without explicit approval.

No direct, unstructured patch generation is permitted without this explicit Hermes architecture + GSD execution pairing.

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
