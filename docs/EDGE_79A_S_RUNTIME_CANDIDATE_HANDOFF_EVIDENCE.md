# EDGE-79A-S — Runtime Candidate Handoff Evidence

## Purpose

EDGE-79A-S adds a read-only runtime evidence contract for candidate handoff diagnostics.

The live run on `2026-05-27` proved that trade-builder can produce reportable executable SENSEX candidates while Phase 2 and `top_opportunities_latest.json` can still report zero candidates. This PR makes that mismatch explicit and machine-readable.

Expected latest artifact:

```text
.runtime/runtime_candidate_handoff_latest.json
```

## Scope

In scope:

- Build a read-only candidate handoff evidence payload.
- Detect mismatch when trade-builder has reportable executable candidates but Phase 2 / top opportunities receive zero candidates.
- Preserve candidate-count boundaries:
  - raw trade-builder candidates
  - post scan survivors
  - post soft reject count
  - post real filter count
  - post executable filter count
  - ranked total count
  - ranked executable count
  - Phase 2 input count
  - top opportunities source candidate count
  - top opportunities executable count
- Preserve a top reportable executable trade identifier when available.
- Keep evidence non-actionable and broker-safe.

Out of scope:

- Broker calls.
- Live order placement.
- Gate loosening.
- Candidate bypass.
- Strategy changes.
- Phase 2 selection changes.
- Top opportunities behavior changes.
- Dashboard behavior changes.

## Evidence contract

Example mismatch payload:

```json
{
  "schema_version": 1,
  "source": "runtime_candidate_handoff_evidence_v1",
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false,
  "symbol": "SENSEX",
  "trade_builder_raw_count": 18,
  "post_scan_survivor_count": 9,
  "post_soft_reject_count": 9,
  "post_real_filter_count": 9,
  "post_executable_filter_count": 8,
  "ranked_total_count": 9,
  "ranked_executable_count": 8,
  "top_reportable_executable_trade_id": "SENSEX-2026-05-27-76100-CE-breakout-1779869031",
  "top_reportable_executable": true,
  "phase2_input_count": 0,
  "top_opportunities_source_candidate_count": 0,
  "top_opportunities_executable_count": 0,
  "handoff_mismatch": true,
  "mismatch_reason": "trade_builder_reportable_executable_candidates_not_visible_to_phase2_or_top_opportunities"
}
```

## Implementation contract

Module:

```text
core/runtime_candidate_handoff.py
```

Functions:

- `runtime_candidate_handoff_path(...)`
- `build_runtime_candidate_handoff_payload(...)`
- `write_runtime_candidate_handoff_evidence(...)`

The module is pure evidence serialization plus atomic JSON writing. It does not run Phase 2 or mutate candidates.

## Runtime wiring target

The orchestrator should call the writer around the runtime candidate-boundary area after it knows:

- `raw_candidate_count`
- `post_scan_survivor_count`
- `post_soft_reject_count`
- `post_real_filter_count`
- `post_executable_filter_count`
- `len(real_candidates)`
- `len(ranked_executable_candidates)`
- top reportable executable candidate payload
- cycle ranked candidate counts before/after append

A later final artifact-level call may enrich the payload with:

- Phase 2 input count
- top opportunities source candidate count
- top opportunities executable count
- selector outcome
- phase2 state

## Safety guard

This PR is observability/evidence only. It does not:

- change candidate state
- change gate decisions
- loosen filters
- add execution paths
- call adapters
- place or modify orders
- compute indicators
- alter strategy output

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge_79a_s_runtime_candidate_handoff_evidence.py
```

Covered behavior:

- detects executable candidate lost before Phase 2 / top opportunities
- preserves read-only and non-action flags
- reports no mismatch when handoff counts align
- writes latest JSON evidence atomically
