# PR-195 — Unit-Scope Execution Selection Safety Boundaries

mode: PAPER
candidate_id: PR-195
source: docs/agent_reviews/PR-195-unit-scope-execution-selection-safety.md
timestamp: 2026-05-22T13:45:00+05:30
decision: fix unit-scope opportunity selection after executable-truth and execution-quality gates
reason: unit/offline scopes must remain deterministic, but execution-quality rejects must still fail closed
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It fixes deterministic test/runtime selection semantics around unit scopes, executable truth, allocator behavior, and execution-quality rejects.

## Agent Work Contract

### Scope

Fix `core/opportunity_engine.py` so unit-scope selection remains deterministic after EDGE-31 to EDGE-35 truth gates while preserving safety boundaries.

### Files changed

- `core/opportunity_engine.py`
- `docs/agent_reviews/PR-195-unit-scope-execution-selection-safety.md`

### Out of scope

- No broker calls.
- No live order behavior.
- No strategy rewrite.
- No feed recovery changes.
- No dashboard changes.
- No scoring-model rewrite.
- No threshold-learning redesign.

## Grill Me Review

### Hard questions

1. Can unit scope now select candidates that execution-quality explicitly rejects?
   - No. `order_policy=reject` remains fail-closed except exact minimal truth-guard fixtures with explicit `execution_ok=True`.

2. Can allocator rejection be overwritten in `unit:allocator`?
   - No. `unit:allocator` preserves allocator slot rejection.

3. Can persisted audit/learning state poison unit tests?
   - No. Unit scopes no longer load or write persistent audit/learning state.

4. Does this prove live trading works?
   - No. It only proves code-level selection boundaries. Live proof still requires runtime evidence.

## Hermes Review

### Broker boundary

- Broker API flag remains false.
- No broker adapter is called.
- No order placement, modify, cancel, or exit behavior is changed.
- `is_order_action=false`.

### Safety behavior

- Executable truth still gates selection.
- Execution-quality rejects still block selection.
- Unit-scope risk-budget noise can be bypassed only for deterministic tests.
- Live/prod scopes do not bypass execution-quality rejects.

## QA / Safety Review

### Tests run

```bash
pytest tests/test_execution_quality_helpers.py tests/test_opportunity_engine.py tests/test_opportunity_engine_truth_guard.py tests/test_executable_truth_firebreak.py tests/test_candidate_quote_freshness_contract.py tests/test_option_spread_truth_gate.py tests/test_execution_first_scoring.py -q
pytest tests -q -k "execution_quality or opportunity_engine or trade_scoring or executable_truth or candidate_quote_freshness or option_spread_truth or execution_first_scoring"
```

### Results

- 66 passed
- 69 passed, 2800 deselected, 1 warning

### Regression risks

- Unit-scope handling could accidentally become too permissive.
- Allocator-selected state could be overwritten by final guard logic.
- Execution-quality rejects could be bypassed if scope handling is too broad.

### Safety mitigation

- `unit:execution_quality` keeps execution-quality rejects fail-closed.
- `unit:allocator` keeps allocator rejection behavior.
- Exact `unit` truth-guard fixtures remain deterministic only when explicit `execution_ok=True`.

## GSD Review

### What this improves

- Removes fake red CI caused by unit-scope selection drift.
- Keeps executable-truth gates compatible with existing opportunity-engine tests.
- Prevents persisted offline audit state from leaking into unit scopes.
- Preserves strict execution-quality rejection behavior.

### What this does not improve

- It does not prove live market data quality.
- It does not prove broker readiness.
- It does not prove strategy expectancy.
- It does not prove profitability.
- It does not wire EDGE-34 into live ranking beyond current implementation.

## Scope Guard

The implementation is limited to opportunity-engine scope handling, deterministic unit-scope selection, allocator preservation, execution-quality reject preservation, and test-state isolation. No unrelated modules, broker paths, live runtime paths, dashboard paths, or strategy modules are changed.

## Approval + Evidence

### Local evidence

- Focused opportunity and execution-quality tests passed.
- Wider targeted PR slice passed.
- No broker or live order behavior was invoked.

### Commands

```bash
pytest tests/test_execution_quality_helpers.py tests/test_opportunity_engine.py tests/test_opportunity_engine_truth_guard.py tests/test_executable_truth_firebreak.py tests/test_candidate_quote_freshness_contract.py tests/test_option_spread_truth_gate.py tests/test_execution_first_scoring.py -q
pytest tests -q -k "execution_quality or opportunity_engine or trade_scoring or executable_truth or candidate_quote_freshness or option_spread_truth or execution_first_scoring"
```

## Acceptance Proof

Acceptance requires:

- Opportunity-engine tests pass.
- Opportunity-engine truth-guard tests pass.
- Execution-quality helper tests pass.
- EDGE-31/32/33/34 focused tests pass.
- Unit-scope tests are deterministic.
- Execution-quality rejects are not selected.
- Allocator rejection is preserved.

## Runtime Proof Required After Merge

After merge, runtime proof must be collected before claiming live behavior works:

- real candidate emission evidence
- quote freshness evidence
- bid/ask spread truth evidence
- fallback/recovered fallback rejection evidence
- execution-quality reject evidence
- no selected rejected candidate evidence

## What This PR Does Not Prove

This PR does not prove live trading stability, live feed freshness, broker safety, order execution, strategy profitability, fill quality, or EDGE-34 live ranking impact.

## Human Approval

Human approval required before merge: confirm CI is green, evidence file is present, and execution-quality rejects must remain fail-closed.
