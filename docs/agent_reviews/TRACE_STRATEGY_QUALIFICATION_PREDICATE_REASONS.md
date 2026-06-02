# Trace Strategy Qualification Predicate Reasons

mode: PAPER
candidate_id: TRACE-STRATEGY-QUALIFICATION-PREDICATE-REASONS
source: docs/agent_reviews/TRACE_STRATEGY_QUALIFICATION_PREDICATE_REASONS.md
timestamp: 2026-06-02T14:14:47+05:30
decision: evidence-only predicate tracing for NO_STRATEGY_QUALIFIED
reason: live state shows feed, indicators, and regime ready while raw_candidate_count stays 0; we need the real predicate failure path without changing strategy behavior
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

### Scope

Implement and test read-only evidence that explains where `NO_STRATEGY_QUALIFIED` is created and which predicate facts were available at that point.

### Files changed

- `core/strategy_gatekeeper.py`
- `core/decision_dag.py`
- `core/orchestrator.py`
- `core/runtime_strategy_no_qualified_reasons.py`
- `tests/test_decision_dag.py`
- `tests/test_orchestrator_strategy_gate_once.py`
- `tests/test_strategy_no_qualified_reasons_evidence.py`
- `docs/agent_reviews/TRACE_STRATEGY_QUALIFICATION_PREDICATE_REASONS.md`

### Out of scope

- No strategy formula changes.
- No threshold tuning.
- No gate decision changes.
- No ranking or Phase2 changes.
- No broker/order changes.
- No feed logic changes.
- No strike-window changes.

## Grill Me Review

- Does this create fake candidate evidence? No.
- Does this override strategy decisions? No.
- Does this widen runtime behavior? No.
- Does this hide absent facts? No. Empty predicate facts now become an explicit no-candidate sentinel instead of vague unknown.

## Hermes Review

- `GateResult` carries optional facts so existing decision telemetry can flow into the evidence writer.
- `decision_dag` retains the predicate node, trade-builder reachability, candidate family considered, and no-candidate marker.
- `runtime_strategy_no_qualified_reasons` classifies latency guard cooldown separately and preserves fail-closed behavior.
- The writer still fans out to `logs/`, `.runtime/`, and `.runtime/logs/`.

## GSD Review

### Tests added

- Decision DAG predicate-fact propagation when no candidate is constructed.
- Orchestrator gate-result propagation of predicate facts.
- Explicit no-candidate sentinel when no predicate facts exist.
- Latency guard cooldown classification as `latency_guard`.
- Existing safety flags and writer fanout remain intact.

### Acceptance proof

- `NO_STRATEGY_QUALIFIED` evidence now explains whether trade-builder was reached and whether a candidate was ever constructed.
- Useful predicate facts are preserved when available.
- Absent facts are reported explicitly as `no_strategy_candidate_constructed_before_gate`.
- Candidate counts and strategy decisions remain unchanged.

## Scope Guard

This PR is evidence-only. It does not alter live strategy selection, feed recovery, broker behavior, or execution safety.

## High-Risk Path Review

The changed high-risk paths are limited to evidence propagation and classification:

- `core/orchestrator.py` now preserves predicate facts in `GateResult` for evidence only.
- `core/decision_dag.py` now retains bounded predicate-fact telemetry for the strategy-selection nodes.
- `core/runtime_strategy_no_qualified_reasons.py` now classifies the failure path more precisely without changing any decision outcome.

What did not change:

- No broker or order APIs.
- No strategy formulas or thresholds.
- No ranking or Phase2 behavior.
- No feed freshness logic.
- No strike-window logic.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`

### Validation commands

```bash
PYTHONPATH=. python -m pytest -q tests/test_strategy_no_qualified_reasons_evidence.py
PYTHONPATH=. python -m pytest -q tests/test_orchestrator_strategy_gate_once.py
PYTHONPATH=. python -m pytest -q tests/test_decision_dag.py
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Acceptance Proof

Acceptance requires:

- Predicate facts from `decision_dag` are visible in strategy-no-qualified evidence when available.
- Empty predicate facts produce an explicit no-candidate sentinel.
- Latency guard cooldown is classified separately.
- Read-only safety flags remain unchanged.
- Artifact fanout still writes all three locations.

## Runtime Proof Required After Merge

After merge, live validation should show the evidence artifact explaining the actual `NO_STRATEGY_QUALIFIED` predicate path rather than only the final gate label.

## What This PR Does Not Prove

This PR does not prove profitability, strategy quality, market edge, broker correctness, or that raw candidates should exist. It only makes the existing predicate failure observable.

## Human Approval

Human approval required before merge: confirm CI is green, the evidence doc is accepted, and the runtime proof still shows fail-closed behavior.
