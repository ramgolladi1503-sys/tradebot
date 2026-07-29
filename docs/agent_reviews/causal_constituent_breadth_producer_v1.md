# Causal Constituent Breadth Producer V1 Review

mode: PAPER
candidate_id: CAUSAL-CONSTITUENT-BREADTH-PRODUCER-V1
decision: ADVISORY_ONLY
reason: Completed synchronized constituent and index bars are transformed into fail-closed breadth event snapshots for the merged shadow strategy.
timestamp: 2026-07-29T19:00:00+05:30
is_order_action: false
broker_api_called: false
source: FEATURE_CAUSAL_CONSTITUENT_BREADTH_PRODUCER_V1

## Purpose

Connect the merged market-event graph strategy to a causal producer that can consume completed NIFTY constituent and index bars in both replay and runtime payloads.

## Scope

- Add a read-only producer for completed synchronized bars.
- Require immutable externally supplied discovery thresholds.
- Enforce completed-bar, timestamp, freshness, and minimum-coverage rules.
- Attach labelled snapshots only on the candidate-pool dictionary input path.
- Preserve shadow-only and no-execution behavior.

## Files Changed

- `core/causal_constituent_breadth_producer.py`
- `core/candidate_pool_orchestrator.py`
- `tests/test_causal_constituent_breadth_producer.py`
- this evidence file

## Safety Boundary

The producer does not subscribe to data, fetch instruments, call brokers, place orders, select contracts, alter risk limits, infer missing thresholds, or use incomplete bars. Missing thresholds, missing bars, stale timestamps, and low constituent coverage fail closed.

## Input Contract

`StrategyContext` dictionary metadata may contain:

- `completed_constituent_bars`
- `completed_index_bars`
- `market_event_graph_frozen_thresholds`

Each bar must identify its symbol, completed timestamp, close, previous close, and explicit completed state. The threshold object must include a version and the three frozen event boundaries.

## Evidence

Focused tests prove:

- synchronized completed bars produce the frozen HIGH → divergence LOW → breadth LOW sequence;
- missing thresholds cannot emit an event;
- incomplete and sub-40 constituent coverage cannot emit an event;
- metadata enrichment is non-mutating;
- the candidate-pool dictionary path automatically produces one shadow market-event graph candidate;
- output explicitly remains non-actionable and broker-free.

## Risks

- Exact discovery thresholds still need to be recovered from the original research artifact and supplied immutably.
- Runtime feed code must supply completed constituent and index bars; this PR does not create subscriptions.
- Historical replay requires point-in-time constituent membership and aligned bars.
- This implementation does not validate option profitability.

## Next PR

Add the runtime/replay bar source adapter and immutable threshold artifact after recovering and independently checking the original discovery thresholds.

## Delivery Verdict

`IMPLEMENTED_FAIL_CLOSED_PRODUCER_AWAITING_REAL_THRESHOLD_AND_BAR_SOURCE`
