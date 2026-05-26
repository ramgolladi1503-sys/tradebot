# EDGE-77 Strategy-Specific Exit Models Agent Review

mode: REVIEW
candidate_id: edge_77_strategy_specific_exit_models
decision: review_ready
reason: pure_strategy_specific_exit_model_contract_tests_docs
timestamp: 2026-05-26T06:45:00Z
source: edge77_strategy_exit_model_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

EDGE-77 introduces a pure read-only strategy-specific exit model contract.

The implementation creates deterministic policy metadata for supported strategy families and blocks unsupported or unsafe candidate shapes with explicit blockers.

## Work contract

EDGE-77 introduces a pure read-only strategy-specific exit model contract.

The implementation creates deterministic policy metadata for supported strategy families and blocks unsupported or unsafe candidate shapes with explicit blockers.

## Scope guard

- No runtime wiring.
- No dashboard work.
- No ranking or scoring.
- No adapter calls.
- No lifecycle mutation behavior.
- No strategy module imports.
- No strategy callable execution.

## High-risk path review

The high-risk path is a candidate receiving an exit policy before it is structurally eligible or option-chain confirmed.

Controls:

- Pool-ineligible candidates are blocked.
- Non-entry candidates are blocked.
- Unsupported directions are blocked.
- Unsupported families are blocked.
- Option confirmation can be required and blocks absent confirmations.
- Supplied option confirmation blocks candidates not present in confirmed evidence.

## Grill Me review

Question: Can this PR cause a live execution side effect?

Answer: No. The contract only returns read-only dataclass payloads. Non-action fields are emitted in reports and model payloads.

Question: Does it weaken EDGE-76 option-chain confirmation?

Answer: No. EDGE-77 can consume confirmed candidate IDs and blocks candidates when supplied confirmation evidence does not include them.

Question: Does it rank or score candidates?

Answer: No. The report emits family policy metadata only and records no ranking and no scoring guarantees.

## Hermes review

The public contract is stable and explicit:

- `build_strategy_specific_exit_models(...)`
- `StrategyExitModelReport.to_payload()`
- `StrategyExitModel.to_payload()`

The schema exposes readiness, blockers, warnings, policy metadata, pool report, and non-action fields.

## GSD review

The PR keeps the work narrow:

- one core module
- one focused test file
- one implementation doc
- one agent-review evidence file
- TODO update that removes EDGE-77 from remaining work

## QA / safety review

Focused tests cover:

- all supported families become ready with strategy-specific defaults
- empty input fails closed
- pool-ineligible candidates remain blocked
- non-entry candidates remain blocked
- unsupported family remains blocked
- unsupported direction remains blocked
- required option confirmation blocks absent confirmation
- supplied confirmation blocks unconfirmed candidates
- supplied confirmation allows confirmed candidates

## Runtime Proof Required After Merge

After merge, runtime proof is still required before this model is wired anywhere.

The proof must show this contract remains read-only, does not change runtime state, and does not bypass EDGE-76 option-chain confirmation.

## What This PR Does Not Prove

This PR does not prove live profitability, live readiness, paper-truth expectancy, slippage truth, runtime integration, dashboard behavior, or final executable-trade quality.

Those belong to later roadmap items.

## Human Approval

Human review is required before any later PR wires this metadata into runtime, paper journal flows, dashboard surfaces, or execution-adapter boundaries.

## Acceptance proof

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_77_strategy_exit_models.py
```

Expected result:

- focused EDGE-77 tests pass
- no external adapter calls
- no runtime mutation
- no dashboard changes
