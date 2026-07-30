# Runtime Authority Hardening V1

## Objective

Reduce TradeBuilder and Orchestrator change risk without modifying the working
market-data, WebSocket, feed-recovery, subscription-registry, or freshness paths.

Base commit:

`17262b4b6a42eb09d4d508bfdf6fe0d649ee32af`

## Non-negotiable boundary

This campaign does not change:

- `core/market_data.py`
- `core/kite_depth_ws.py`
- `core/feed_runtime.py`
- `core/feed_health_truth.py`
- `core/feed_hold_gate.py`
- `core/recovery_state_machine.py`
- `core/kite_ws_subprocess.py`
- runtime feed configuration

The guard in `core.runtime_authority_contract` fails when any protected path is
included in the campaign diff.

## Completed stages

### A. Feed freeze

A deterministic changed-path guard protects feed and configuration files. The
hardening modules consume feed-derived inputs only; they do not change feed state.

### B. Runtime authority map

`core.runtime_authority_contract` records the known production stages and
separates execution, execution-guard, candidate-construction, UI-only, research,
and pending-proof authority.

Exactly one mapped stage may call the broker:

`core.execution_router.ExecutionRouter`

This is an architectural contract, not a claim that every legacy call path has
already been removed.

### C. Characterization

`core.trade_builder_characterization` normalizes legacy builder outputs, removes
volatile timestamps/latencies, and produces deterministic SHA-256 hashes. Raised
exceptions are also characterized instead of disappearing from evidence.

### D. Shadowing control

`core.orchestrator_shadowing_audit` performs an AST-only audit of helpers imported
from `core.orchestrator_truth` and then redefined in `core.orchestrator`.

Existing shadowing is frozen as explicit technical debt. Any newly shadowed
authority helper fails the audit. Existing implementations are not deleted until
behavioral parity is proven.

### E. Canonical execution decision

`core.canonical_execution_decision` wraps the existing executable-truth classifier
and combines fragmented legacy fields into one immutable, fail-closed decision:

- `EXECUTABLE`
- `ADVISORY_ONLY`
- `BLOCKED`

Contradictory legacy fields block execution. The module is read-only and performs
no broker action.

### F. TradeBuilder facade characterization

The existing TradeBuilder API remains untouched. Its output can now be captured
twice against frozen snapshots and compared by stable hash before any extraction
is attempted.

### G. Extracted orchestration-stage semantics

`core.orchestration_stage_pipeline` provides:

- immutable cycle input;
- ordered stages;
- critical failure halting;
- noncritical evidence degradation;
- one broker-action stage maximum;
- rejection of order actions from non-broker stages.

It is a shadow kernel and does not replace the production Orchestrator in this PR.

### H. Ranking authority separation

`core.ranking_authority` records that:

- `core.ranking_orchestrator` is UI-only;
- `core.runtime_snapshot_producer` is UI-only;
- the legacy opportunity engine remains `UNKNOWN_PENDING_PROOF`.

Unknown authority fails closed. No ranking engine is promoted to execution
authority based only on imports or dashboard output.

### I. Fault tests

Tests cover:

- critical-stage exceptions;
- noncritical evidence-write failures;
- unauthorized order-action output;
- contradictory execution fields;
- fallback/stale truth blocking;
- missing execution entries;
- non-repeatable characterization;
- protected feed-path changes;
- multiple execution-ranking authorities.

## Promotion boundary

The campaign verdict is:

`PASS_SHADOW_HARDENING`

It deliberately remains:

- `allowed_for_live_execution=false`
- `is_order_action=false`
- `broker_api_called=false`

Runtime promotion requires real call-path evidence and supervised characterization.
This PR improves safety and testability without pretending an additive shadow
contract has already replaced the legacy runtime.
