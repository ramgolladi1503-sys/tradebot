# Strategy Truth Phase 0 — Inventory and Quarantine Evidence

## Agent work contract

```text
source_agent: Codex
action: GENERATE_PATCH
title: Add truthful strategy inventory and quarantine metadata
scope: Phase 0 metadata and validation only
requested_paths: config/strategy_inventory.yml, tests/test_strategy_inventory.py, docs/agent_reviews/strategy_truth_phase0_inventory.md
allowed_paths: config/strategy_inventory.yml, tests/test_strategy_inventory.py, docs/agent_reviews/strategy_truth_phase0_inventory.md
forbidden_paths: main.py, run_live.sh, credentials.py, .env, *.env, runtime/live*, logs/broker*, secrets*, core/execution*, core/broker*, core/order*, core/risk*, core/feed*, strategies/*, dashboard/*
expected_tests: python -m pytest -q tests/test_strategy_inventory.py
acceptance_proof: Inventory has ten candidate generators, one option-confirmation layer, one safety layer, three explicit quarantines, no promoted status, and execution_eligible=false for every item.
```

## What changed

- Added a dependency-free, JSON-compatible YAML inventory of strategy roles, claims, validation status, and quarantine reasons.
- Classified ten candidate-generator families separately from option confirmation and no-trade suppression.
- Quarantined Trend Pullback, Opening Range Retest, and Exhaustion Reversal.
- Renamed the inventory claims for event volatility and option pressure without changing their runtime identifiers or behavior.
- Added deterministic validation for schema completeness, unique identifiers, explicit aliases, role counts, truthful claims, and fail-closed execution eligibility.

## Why this moves safety and readiness forward

The repository can no longer use this inventory to imply that a registered component is a proven strategy or executable opportunity. The artifact records epistemic status explicitly and makes every current item ineligible for execution. It is metadata only; it does not prove pattern conformance, predictive edge, option translation, profitability, paper readiness, or live readiness.

## Risks

- The inventory can drift from the Python registry until a later, separately reviewed registry-integrity PR creates a validated relationship.
- Human readers may mistake `PARTIAL_DETECTOR` for evidence of predictive value. It only describes implementation maturity.
- Quarantine is declarative in this PR. It does not alter runtime generator activation because runtime wiring is explicitly out of scope.

## What did not change

- No strategy implementation or threshold.
- No runtime activation, registry loading, profile resolution, candidate generation, ranking, or Phase-2 behavior.
- No feed, broker, order, execution, risk, credential, dashboard, paper, or live behavior.
- No API or network call.

## Safety evidence

```text
mode: OFFLINE
candidate_id: STRATEGY_TRUTH_PHASE0_INVENTORY
message_decision: READ_ONLY_INVENTORY_CREATED
decision: READ_ONLY_INVENTORY_CREATED
reason: The change records truthful strategy maturity and quarantine metadata without runtime wiring or execution authority.
timestamp: 2026-07-14T00:00:00+05:30
source: docs/agent_reviews/strategy_truth_phase0_inventory.md
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
```

## Tests

Run:

```bash
python -m pytest -q tests/test_strategy_inventory.py
```

The tests prove inventory structure and fail-closed metadata. They do not execute strategies and do not prove trading edge.

### Full-suite baseline comparison

Classification: `PRE_EXISTING_REPRODUCED`

Patched-worktree command:

```bash
python -m pytest -q tests/test_orchestrator_reports_finally.py
```

Patched-worktree outcome: `1 failed`. The assertion expected
`forced_cycle_error`, but `engine_cycle_status["last_error"]` contained
`RuntimeError:[AUTH] missing_kite_access_token`.

Untouched-baseline setup and command:

```bash
git worktree add --detach <temporary-worktree> 691b8a75
cd <temporary-worktree>
python -m pytest -q tests/test_orchestrator_reports_finally.py
```

Untouched-baseline outcome: `1 failed in 10.57s` at the same assertion with the
same missing-token error class and message. The decisive traceback path in both
runs was:

```text
Orchestrator._legacy_live_monitoring
-> fetch_live_market_data
-> get_ltp
-> kite_client.ensure
-> get_kite_credentials
-> resolve_access_token
-> RuntimeError: [AUTH] missing_kite_access_token
```

In both cases, credential resolution failed before the monkeypatched
`_evaluate_suggestions` method could raise `forced_cycle_error`. No credential
was added and no broker call or broker success is claimed. The disposable
baseline worktree was removed after the test.

## Rollout and migration

1. Review the role and claim for every item against the current implementation.
2. Merge this metadata-only baseline without runtime consumption.
3. In the registry-integrity PR, validate explicit registry references against this inventory while preserving `execution_eligible=false`.
4. Add startup enforcement only in a separately approved PR with compatibility and rollback tests.
5. Promote an item only through conformance, out-of-sample research, option validation, and live-shadow evidence.

New config key: `strategy_inventory.yml` is a new read-only artifact; it introduces no environment variable or runtime setting.

Rollback: revert this isolated metadata PR. No runtime migration or data repair is required.

## What could still fail

- Existing runtime strategy names and callable construction remain untouched and may still be incorrect.
- Parameter profiles and provenance remain unverified.
- Runtime context may still contain semantic substitutions.
- Quarantined generators may still run because enforcement is intentionally deferred.
- No detector has conformance, predictive, translation, execution, or operational proof from this change.
