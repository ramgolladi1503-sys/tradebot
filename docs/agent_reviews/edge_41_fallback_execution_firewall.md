# Agent Review - EDGE-41 Fallback Execution Firewall

```yaml
mode: paper_review
timestamp: 2026-05-23T18:25:00Z
candidate_id: edge_41_fallback_execution_firewall
decision: approve_scoped_firewall
reason: fallback_and_degraded_quote_sources_fail_closed_before_execution_selection
is_order_action: false
broker_api_called: false
source: docs/EDGE_41_FALLBACK_EXECUTION_FIREWALL.md
```

## Agent Work Contract

Implement EDGE-41 only: harden the existing executable-truth firebreak so fallback, stale, subscription-failed, and price-mismatch quote sources cannot become execution-grade or top executable opportunities.

## Scope Guard

In scope:

- Extend `core/executable_truth.py` detection for fallback and degraded quote evidence.
- Add tests proving fallback/mismatch/stale/subscription-failed data cannot become executable.
- Add EDGE-41 documentation.

Out of scope:

- No websocket recovery changes.
- No strategy changes.
- No scoring model rewrite.
- No dashboard changes.
- No broker/order behavior changes.
- No live execution behavior changes.

## Grill Me Review

Question: Does this PR hide feed bugs by increasing thresholds?

Answer: No. It does not change thresholds. It fails closed on fallback/degraded quote markers.

Question: Does this duplicate observability tests?

Answer: No. Existing observability tests prove fallback events are non-executable. This PR extends the protection into executable-truth and opportunity selection behavior.

Question: Can fallback-estimated RR still rank as executable?

Answer: No. `fallback_estimated` RR becomes `fallback_driven_data`, which blocks execution quality.

## Hermes Review

The patch uses the existing `classify_executable_truth()` boundary already called by `evaluate_pretrade_execution_quality()`.

This avoids creating unrelated architecture and keeps the fix narrow.

## GSD Review

The implementation maps directly to the runtime diagnosis:

- `rest_fallback` is blocked.
- `fallback_estimated` RR is blocked.
- `PRICE_MISMATCH` is blocked.
- `STALE_OPTION_LTP` is blocked.
- `subscription_failed` is blocked.

The selector proof ensures a fallback candidate cannot appear as a top executable opportunity.

## QA / Safety Review

No broker calls are introduced.
No order actions are introduced.
No runtime startup changes are introduced.
No strategy generation changes are introduced.
No stale/fallback threshold is loosened.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge41_fallback_execution_firewall.py
PYTHONPATH=. python -m pytest tests/observability/test_fallback_execution_block.py
PYTHONPATH=. python -m pytest tests/test_opportunity_engine.py
```

## Runtime Proof Required After Merge

Next runtime evidence pack should show fallback/degraded quote candidates as advisory/non-executable and selector should not select them as top executable opportunities.

## What This PR Does Not Prove

- Does not prove feed recovery works.
- Does not prove quote truth is unified.
- Does not prove strategy profitability.
- Does not prove paper/live readiness.

## Human Approval

Human approval required before merge.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
