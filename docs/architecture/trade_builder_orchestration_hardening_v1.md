# TradeBuilder and Orchestration Hardening V1

## Frozen baseline

- Base branch: `main`
- Base commit: `17262b4b6a42eb09d4d508bfdf6fe0d649ee32af`
- Working branch: `hardening/trade-builder-orchestration-v1`

## Non-negotiable exclusion

This campaign must not modify feed behavior. The following areas are frozen:

- `core/market_data.py`
- `core/kite_depth_ws.py`
- `core/feed_runtime.py`
- feed recovery and freshness modules
- subscription-registry modules
- feed configuration and runtime thresholds

Recorded feed and candidate payloads may be used as test inputs. Feed implementation must not be changed.

## Source-proven findings

1. `core/orchestrator.py` is an oversized runtime authority surface and combines execution, risk, reconciliation, reporting, maintenance, position management and candidate handling.
2. `strategies/trade_builder.py` combines signal construction, quote handling, candidate scoring, rejection telemetry, contract selection and output side effects.
3. `core/orchestrator.py` imports canonical helpers from `core.orchestrator_truth` and locally redefines some imported names, making actual runtime authority ambiguous.
4. Candidate execution truth is represented by several independently mutable legacy fields.
5. Fallback rows are protected by existing execution firewalls; visible fallback rows alone do not prove fallback execution.
6. The canonical ranking orchestrator is currently documented and implemented as read-only reporting infrastructure. It must not be assumed to control broker execution until the action path is traced.

## Implementation stages

### Stage A — authority audit

`core.runtime_authority_audit` statically inspects runtime modules without importing or executing them. It records:

- file size;
- classes and functions;
- imported symbols;
- imported names redefined locally;
- broker-action references;
- file-write references.

### Stage B — canonical shadow decision

`core.execution_decision_contract` derives one immutable decision:

- `EXECUTABLE`
- `ADVISORY_ONLY`
- `BLOCKED`

It is shadow-only in V1 and cannot route orders. It is deliberately conservative: fallback, synthetic, stale, untrusted, unresolved or contradictory candidates cannot become executable.

### Stage C — characterization gate

Before changing runtime authority, tests must prove:

- deterministic output for repeated input;
- fallback and stale candidates remain non-executable;
- contradictory legacy execution fields are surfaced;
- hard blockers override positive execution fields;
- inference never mutates input candidates.

### Stage D — helper-authority repair

No duplicate helper is removed until corpus-level parity proves that the local and shared implementations agree. Where they disagree, the mismatch must be documented and resolved explicitly.

### Stage E — shadow comparison

The canonical shadow decision will later be emitted beside the legacy decision. It must not control execution until replay and supervised PAPER evidence show zero unexplained mismatches.

### Stage F — incremental extraction

Refactoring must preserve the public facades:

- `TradeBuilder.build(...)`
- `Orchestrator`

Responsibilities are extracted behind those facades one at a time, with normalized golden-master comparison after each extraction.

### Stage G — ranking authority

Execution ranking, UI ranking and research ranking must be separately identified. No score-weight changes are allowed until the selection function that creates the actual execution intent is proven.

### Stage H — fault tests

Downstream tests must cover stale option data, duplicate candidates, disk failures, ranking exceptions, broker timeouts, restart idempotency and contradictory state. These tests use fixed/fake inputs and do not alter feed code.

## Promotion rule

This branch remains draft and unmerged until focused CI passes. Runtime behavior changes require additional replay and supervised PAPER evidence; passing static and unit tests alone is not live certification.
