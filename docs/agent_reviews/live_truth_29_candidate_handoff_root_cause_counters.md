# Agent Review Evidence — LIVE-TRUTH-29 Candidate Handoff Root-Cause Counters

## Agent Work Contract

### Goal

When Phase2 raw input count is zero (or unexpectedly low), publish a compact per-cycle counter snapshot that shows where candidates were blocked (feed, quote, indicators, latency, contract resolution, execution context) so candidates do not disappear silently between strategy generation and Phase2.

### Files changed

- `core/runtime_candidate_handoff_root_cause.py`
- `core/orchestrator.py`
- `tests/test_runtime_candidate_handoff_root_cause.py`
- `docs/agent_reviews/live_truth_29_candidate_handoff_root_cause_counters.md`

### Evidence Contract Fields

mode: LIVE
candidate_id: LIVE_TRUTH_29_CANDIDATE_HANDOFF_ROOT_CAUSE_COUNTERS
decision: CANDIDATE_HANDOFF_ROOT_CAUSE_COUNTERS
reason: Runtime now writes `candidate_handoff_latest.json` to both `logs/` and `.runtime/` with stage counters and top blocker codes, ensuring phase2_raw_count=0 is explainable.
timestamp: 2026-05-29T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live_truth_29_candidate_handoff_root_cause_counters.md

### Non-goals

- No broker calls.
- No order placement.
- No ranking weight changes.
- No UI/dashboard.

## Grill Me Review

### Pushback

If candidates disappear silently between strategy generation and Phase2, operators cannot distinguish real “no signal” from data/contract failures during market hours.

### Required proof

- Counters are written every cycle.
- Each candidate increments exactly one primary blocker bucket.
- Unknown reasons map to an explicit unknown bucket (no silent drop).

## Hermes Review

### Contract clarity

The snapshot is a read-only runtime contract. It is diagnostic-only and must not affect trading decisions.

### Safety boundary

No external calls are made. The writer uses atomic JSON writes only.

## GSD Review

### Minimality

- Adds a small pure classifier + writer module.
- Wires writer at the orchestrator cycle boundary after top-opportunities/Phase2 result is computed.
- Adds deterministic unit tests.

## QA / Safety Review

Tests assert:

- 10 generated with 8 feed blocked and 2 indicator missing results in an 8/2 split and phase2_raw_count=10.
- Phase2 raw vs ranked counts are recorded deterministically.
- Unknown blocker codes map to `unknown_drop_reason_count`.

## High-Risk Path Review

High-risk module touched: `core/orchestrator.py` (runtime cycle boundary).

Safety review notes:

- Only adds a diagnostic JSON write; does not change candidate selection, ranking weights, broker calls, or order execution.
- Payload is explicitly non-action (`is_order_action=false`, `broker_api_called=false`).

## Scope Guard

Confirmed not touched:

- Strategy generation logic.
- Phase2 scoring weights.
- Broker/execution adapters.
- UI/dashboard.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest -q tests/test_runtime_candidate_handoff_root_cause.py
PYTHONPATH=. python -m pytest -q tests/test_engine_phase2_adapter.py
```

Expected:

- Root-cause counter tests pass.
- Existing Phase2 adapter tests remain green.

## Runtime Proof Required After Merge

During a live observation window:

- Confirm both files update each cycle:
  - `logs/candidate_handoff_latest.json`
  - `.runtime/candidate_handoff_latest.json`
- When phase2_raw_count is zero, counters and `top_drop_reasons` clearly indicate where candidates were blocked.

## What This PR Does Not Prove

- It does not prove feed correctness or indicator correctness; it only makes drop reasons visible.
- It does not prove profitability or strategy quality.

## Human Approval

Merge only if CI is green and reviewers confirm the change is instrumentation-only (no behavioral changes to execution).
