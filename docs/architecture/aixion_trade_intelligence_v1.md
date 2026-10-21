# Aixion Trade Intelligence V1 Architecture

## Decision

Implement the first production-capable intelligence lane inside the TradeBot repository as an isolated, read-only Python package. This keeps source contracts and CI close to the authoritative runtime while preserving a hard boundary from strategy, risk, broker, and order code.

A later repository extraction is possible after the event contract and live canary stabilize. V1 does not justify a second deployment stack.

## Scope

V1 implements the evidence kernel:

```text
candidate and market evidence
→ canonical events
→ append-only JSONL
→ deterministic replay
→ data-quality manifest
→ candidate lineage
→ causal outcomes
→ fail-closed certification
→ evidence report
```

The package does not claim to implement the full long-term analytics catalogue. Market Event Graph, portfolio allocation, PBO/Deflated Sharpe, drift/OOD, agent orchestration, and live dashboards remain separate gated phases.

## Existing TradeBot authority reused

- `core/candidate_lineage_ledger.py` remains the candidate-funnel authority.
- `core/feed_truth_contract.py` and execution-truth owners remain safety authorities.
- existing Upstox Parquet captures remain market-source evidence.
- `core/tradebot_rag.py` remains repository evidence retrieval; this change does not add another RAG stack.
- existing broker, risk, ranking, and strategy modules are untouched.

## Components

### Canonical event contract

Every event contains identity, schema version, producer sequence, payload hash, causal timestamps, source authority, and immutable payload.

Required temporal relationship:

```text
source_time <= receive_time <= available_time <= persist_time
receive_time <= parse_time <= persist_time
event_time <= available_time
```

For strategy features:

```text
feature_available_time <= decision_event_time
```

### Append-only evidence

`FilePublisher` and batch append use OS append mode, process-local locking, cross-process file locking where available, bounded writes, and optional `fsync`.

JSONL is authoritative. Parquet export is derived and optional.

### Deterministic replay

Replay:

- deduplicates byte-identical event IDs;
- rejects conflicting duplicate IDs;
- orders by availability, producer, sequence, and event ID;
- verifies the same hash under reversed input iteration.

### Session quality

The manifest validates:

- one start and one end event;
- single session identity;
- exact producer reconciliation;
- sequence gaps and regressions;
- expected instrument and event coverage when declared;
- look-ahead violations;
- timestamp ordering;
- declared time coverage;
- source and persistence latency distributions.

No universal trading thresholds are embedded. Coverage requirements come from the session contract.

### Candidate lineage

Lineage joins strategy, signal, candidate, approval, order, fill, position, and risk events by immutable candidate identity. Conflicting strategy identities or versions fail analysis.

### Causal outcomes

Every candidate must provide its own outcome contract:

```json
{
  "horizons_seconds": [60, 300],
  "entry_delay_seconds": [0, 30],
  "underlying_instrument": "exact instrument key",
  "selected_option_instrument": "exact instrument key"
}
```

The engine uses:

- first source quote available at or after the decision;
- option ask for executable entry;
- option bid for executable exit;
- mid/LTP only as a diagnostic path;
- no invented bid, ask, strike, expiry, or price;
- label availability no earlier than the registered horizon.

### Certification

Certification fails closed on:

- invalid session manifest;
- replay conflict;
- lineage conflict;
- malformed outcome contract;
- look-ahead;
- missing contract coverage;
- incomplete causal outcome evidence;
- label-time violation.

A successful verdict is deliberately named `PIPELINE_OFFLINE_CERTIFIED`. The result always carries `strategy_edge_certified=false`.

## Live lifecycle

```text
observer starts
→ candidate ledger tailed with checkpoint
→ observer stops with finalization deferred
→ exact candidate instruments derived
→ quote evidence appended
→ finalizer appends one reconciled SESSION_ENDED
→ report and certification generated
```

The finalizer is idempotent after `SESSION_ENDED`; report generation can be retried without creating a second terminal event.

## Failure isolation

- analytics cannot call broker methods;
- output defaults under `.runtime`;
- observer refuses to append a new session into non-empty evidence;
- invalid source JSONL creates an incident and exits nonzero;
- quote importer requires an exact derived or explicit instrument set unless `--all-instruments` is consciously supplied;
- analytics failure does not change TradeBot state.
