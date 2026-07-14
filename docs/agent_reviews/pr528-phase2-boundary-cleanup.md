# PR #528 — Phase-2 Boundary Cleanup

mode: PAPER
candidate_id: pr528-phase2-boundary-cleanup
signal_id: pr528-phase2-boundary-cleanup
strategy_id: phase2_boundary_contract
decision: REVIEW_ONLY
reason: read_only_phase2_boundary_contract_guard_added
timestamp: 2026-06-08T15:30:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr528-phase2-boundary-cleanup.md

## Agent Work Contract

This PR adds an opt-in Phase-2 ownership boundary guard to the movement candidate contract.

The work is intentionally limited to contract validation and focused tests. It does not wire the guard into live runtime, broker paths, strategy execution, dashboard behavior, scoring behavior, ranking behavior, feed behavior, or order behavior.

## Scope Guard

In scope:

- Define strategy-owned score fields.
- Define Phase-2-owned score fields.
- Define Phase-2 truth evidence keys.
- Add `phase2_boundary_violations(...)`.
- Add `assert_phase2_boundary(...)`.
- Add `StrategyCandidate.phase2_boundary_violations(...)` convenience method.
- Add `StrategyCandidate.assert_phase2_boundary(...)` convenience method.
- Add tests that prove strategy-owned thesis is allowed and Phase-2-owned tradability truth is rejected when claimed by strategy producers.

Out of scope:

- No broker calls.
- No order actions.
- No live execution behavior.
- No strategy generation behavior changes.
- No feed or depth subscription changes.
- No scoring formula changes.
- No ranking behavior changes.
- No dashboard/UI changes.
- No runtime wiring of the new guard.

## Grill Me Review

The main risk is over-enforcing the boundary too early and breaking existing runtime paths. This PR avoids that by making the boundary guard opt-in only.

The second risk is pretending this cleans all Phase-2 behavior. It does not. It only creates a deterministic contract guard that later PRs can wire into specific producers.

The third risk is allowing strategy modules to continue claiming option freshness, liquidity, or resolved instrument truth. The tests prove those claims are detected when a candidate is reviewed as strategy-produced.

## Hermes Review

Task boundary stayed narrow.

Changed files:

- `core/movement_contract.py`
- `tests/test_movement_contract.py`
- `docs/agent_reviews/pr528-phase2-boundary-cleanup.md`

The PR is contract-only. It does not touch runtime startup, broker adapters, feed/WebSocket code, dashboard code, strategy modules, execution engine, risk engine, or order paths.

## GSD Review

This PR improves candidate truth by making ownership explicit:

- Strategy owns thesis, trigger, invalidation, movement type, direction, and price-structure evidence.
- Phase-2 owns resolved tradable instrument truth, option confirmation, liquidity, freshness, and execution eligibility evidence.

The implementation is a small, testable contract step. It prepares the repo for later boundary enforcement without changing current runtime behavior.

## QA / Safety Review

Safety properties covered:

- Boundary guard is opt-in only.
- Strategy-produced candidate claiming `option_confirmation_score` away from neutral is reported.
- Strategy-produced candidate claiming `liquidity_score` away from neutral is reported.
- Strategy-produced candidate claiming `freshness_score` away from neutral is reported.
- Strategy-produced candidate claiming `quote_source` evidence is reported.
- Strategy-produced candidate claiming `resolved_contract` evidence is reported.
- Strategy-owned thesis evidence remains allowed.
- Phase-2-produced candidate can carry resolved truth.

No high-risk path review is required because this PR does not change config, auth, feed/WebSocket, orchestrator, execution, risk, or strategies.

## Acceptance Proof

Focused command:

```bash
PYTHONPATH=. pytest tests/test_movement_contract.py
```

Expected proof:

- Existing movement candidate contract tests remain green.
- Strategy producer claiming Phase-2 execution truth is rejected by the opt-in boundary guard.
- Strategy producer with only strategy-owned thesis evidence passes the boundary guard.
- Phase-2 producer can attach Phase-2-owned truth without violation.

CI gates to satisfy:

- Agent Review Evidence Gate.
- Code Excellence Gates / Minerva / Evidence / Cerberus.
- Existing unit test workflows.

## Runtime Proof Required After Merge

No runtime proof is required to validate broker/feed behavior because this PR does not wire the new guard into runtime execution, broker calls, feed subscriptions, dashboard, or order paths.

Future runtime proof is required only when a later PR wires this guard into actual candidate producers or Phase-2 adapters.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove strategy quality.

It does not prove Phase-2 candidate generation correctness.

It does not prove ranking profitability.

It does not prove feed recovery.

It only proves the repository now has a deterministic opt-in contract for separating strategy-owned thesis from Phase-2-owned tradability truth.

## Human Approval

Human approval is required before merge.

Do not merge only because the PR is green. Review that the change remains opt-in, contract-only, and does not silently alter runtime or strategy behavior.


## High-Risk Path Review

N/A
