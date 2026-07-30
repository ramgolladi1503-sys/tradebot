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

## Implemented proof surfaces

### Golden-master comparison

`core.architecture_golden_master` canonicalizes JSON or JSONL snapshots, removes only explicitly declared volatile fields, and produces deterministic SHA-256 semantic hashes. Any entry, stop, target, candidate ordering, permission, selected trade or execution-state change remains visible to the comparison.

### Helper parity

`core.helper_parity_proof` preserves independent legacy reference implementations for the three shadowed helper families and compares them against `core.orchestrator_truth` on candidate corpora. Duplicate helper removal is forbidden while any mismatch remains.

### Complete-cycle shadow comparison

`core.execution_shadow_cycle` compares the existing reportable-executable decision with the immutable shadow `ExecutionDecision` for every candidate in a cycle. It reports counts, parity rate, state distribution, mismatch reasons and row-level evidence. The harness accepts recorded LIVE/PAPER cycle candidates but does not initiate broker or feed activity.

### Extraction seams

`core.trade_builder_stage_pipeline` and `core.orchestrator_stage_pipeline` provide behavior-neutral stage seams. Both default to passthrough. Production responsibilities can only be registered one at a time after a golden-master test proves parity through the existing public facade.

### Ranking-authority proof

`core.execution_ranking_authority` uses AST evidence and deliberately distinguishes reporting calls from execution authority. Ranking is marked authoritative only when a value assigned from a ranking call is consumed by an execution call in the inspected module. A UI/reporting-only call is not sufficient evidence.

## Implementation stages

### Stage A — authority audit

`core.runtime_authority_audit` statically inspects runtime modules without importing or executing them. It records file size, classes and functions, imported symbols, imported names redefined locally, broker-action references and file-write references.

### Stage B — canonical shadow decision

`core.execution_decision_contract` derives one immutable decision: `EXECUTABLE`, `ADVISORY_ONLY` or `BLOCKED`. It is shadow-only in V1 and cannot route orders. Fallback, synthetic, stale, untrusted, unresolved or contradictory candidates cannot become executable.

### Stage C — characterization gate

Tests prove deterministic output, non-executability of fallback/stale candidates, surfacing of contradictory legacy fields, blocker precedence and input purity.

### Stage D — helper-authority repair

No duplicate helper is removed until corpus-level parity proves that local and shared implementations agree. The executable parity harness is now present; actual removal remains gated on a representative frozen corpus.

### Stage E — shadow comparison

The complete-cycle comparator is implemented. It must run against frozen replay and supervised PAPER payloads before the shadow result may control execution.

### Stage F — incremental extraction

Behavior-neutral TradeBuilder and Orchestrator stage seams are implemented behind separate modules. No production stage has been moved yet; each move requires facade-level golden-master parity.

### Stage G — ranking authority

The proof tool is implemented. Execution ranking, UI ranking and research ranking remain separate until repository/runtime evidence identifies the actual selection path.

### Stage H — fault tests

Downstream tests must cover stale option data, duplicate candidates, disk failures, ranking exceptions, broker timeouts, restart idempotency and contradictory state using fixed/fake inputs without changing feed code.

## Promotion rule

This branch remains draft and unmerged until focused CI passes. Runtime behavior changes require replay and supervised PAPER evidence; passing static and unit tests alone is not live certification.
