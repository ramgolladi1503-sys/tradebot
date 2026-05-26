# HOTFIX/EDGE-79A Live Indicator Readiness Diagnostics Agent Review

mode: REVIEW
candidate_id: hotfix_edge_79a_live_indicator_readiness_diagnostics
decision: review_ready
reason: live_indicator_readiness_contract_tests_docs
timestamp: 2026-05-26T10:40:00Z
source: hotfix_edge79a_indicator_readiness_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

HOTFIX/EDGE-79A adds a pure per-symbol indicator readiness diagnostics contract before EDGE-80.

The output is intended to become input evidence for NoTradeOracle, especially when live price exists but indicator readiness fails.

## Work contract

This PR covers diagnostics only.

It does not compute indicators, wire runtime, change dashboard, rank candidates, score edge, or add strategy behavior.

## Scope guard

- Per-symbol readiness fields are explicit.
- Warmup bars are checked.
- Indicator last update is checked.
- Indicator age is checked.
- Missing VWAP, RSI, EMA, and ATR are checked.
- Compute errors are preserved.
- Read-only report payloads remain explicit.

## High-risk path review

The high-risk path is a symbol with live price but missing indicator inputs being treated as ready.

Controls:

- Zero OHLC bars block readiness.
- Missing last update blocks readiness.
- Stale indicator update blocks readiness.
- Missing indicator values block readiness.
- Compute error blocks readiness.
- Decision reason exposes the first gate reason.

## Grill Me review

Question: Can this PR hide missing indicator inputs?

Answer: No. Missing inputs and missing indicator values are exposed separately.

Question: Can this PR compute new indicator values and mask a data issue?

Answer: No. It only reads supplied snapshots and reports readiness.

Question: Does this PR allow EDGE-80 to explain no-trade reasons better?

Answer: Yes. It exposes per-symbol facts needed for indicator-readiness no-trade evidence.

## Hermes review

The public contract is stable and explicit:

- `build_live_indicator_readiness_report(...)`
- `LiveIndicatorReadinessReport.to_payload()`
- `LiveIndicatorReadinessDecision.to_payload()`

The schema exposes all requested per-symbol fields plus blockers, warnings, and read-only metadata.

## GSD review

The PR keeps the work narrow:

- one core module
- one focused test file
- one implementation doc
- one agent-review evidence file
- TODO update that inserts 79A and 79B before EDGE-80

## QA / safety review

Focused tests cover:

- ready indicator snapshot
- zero OHLC bars and missing last update
- stale indicator update
- compute error preservation
- empty input fail-closed behavior
- multiple-symbol per-symbol diagnostics

## Runtime Proof Required After Merge

After merge, runtime proof is still required before this diagnostic report is connected to broader runtime or review flows.

EDGE-80 should consume this as evidence, not recompute or guess indicator readiness.

## What This PR Does Not Prove

This PR does not prove NoTradeOracle behavior, live readiness, live profitability, paper-truth expectancy, feed freshness, or final executable quality.

Those belong to later roadmap items.

## Human Approval

Human review is required before any later PR changes production indicator sources or runtime configuration surfaces.

## Acceptance proof

Command:

`PYTHONPATH=. python -m pytest tests/test_hotfix_edge_79a_live_indicator_readiness.py`

Expected result:

- focused HOTFIX/EDGE-79A tests pass
- missing indicator readiness facts produce explicit blockers
- ready symbols stay ready
- no runtime or dashboard change
