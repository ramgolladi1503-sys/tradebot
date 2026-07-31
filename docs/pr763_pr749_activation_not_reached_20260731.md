# PR #763 PR #749 Activation Not Reached - 2026-07-31

## Scope

This document records the timing-sufficient live defect and the narrow repair
that decouples PR #749 constituent-source activation from candidate generation.
It preserves the sealed evidence root unchanged.

## Sealed Run

- Run ID: `unified-pr748-756-20260731-a2b340a41c53-live-d37a9445`
- Starting campaign SHA: `464404cc175de4d6aeef5fdcb519e1ca537c0a34`
- Composition SHA: `a2b340a41c53e2e620046ccd4ea5179258ae7dc0b054fbf756a568a734aff417`
- Artifact manifest SHA: `84cfc51945b91c770d936ccf4918b9ca2bc0969d7317c7d6b3c084f4b3600eea`
- Evidence root: `runtime/diagnostics/unified_live_validation_pr748_756_v1/unified-pr748-756-20260731-a2b340a41c53-live-d37a9445`
- Runtime: `780.1 seconds`
- Eligible completed boundaries: `13`
- Canonical tick writer rows: `2153`
- Reader-visible rows: `2153`
- Reader-visible distinct tokens: `289`
- Accepted FULL identities: `51`
- Safety scan: passed

## Observed Failure

- PR #749 state file: absent
- `live/constituent_source_refresh.jsonl`: absent
- `live/constituent_source_states.jsonl`: absent
- `live/constituent_completed_bars.jsonl`: absent
- `live/market_event_graph_intervals.jsonl`: `78` rows
- First MEG status: `MISSING_SOURCE_BARS`
- Latest MEG status: `MISSING_SOURCE_BARS`
- Latest MEG reason: `completed_constituent_bars_missing`
- Latest producer status: `NOT_EVALUATED`

Classification:

```text
PR749_SOURCE_ACTIVATION_NOT_REACHED
COMPLETED_ROWS_NOT_OBSERVED_DESPITE_ELIGIBLE_BOUNDARIES
UNIFIED_LIVE_EVIDENCE_PARTIAL_NOT_FORMAL_ACCEPTANCE
```

## Call-Site Trace

### `attach_market_event_graph_constituent_source(...)`

- Production call site before repair: `core/candidate_pool_orchestrator.py`
- Calling function: `build_candidate_pool_report(...)`
- Runtime frequency: only when candidate-pool report construction runs
- Conditional: yes, it is downstream of candidate-pool construction
- Executes without candidates: not guaranteed
- Executes for NIFTY: yes, when the report path is entered for NIFTY
- Timing-sufficient run evidence: not executed as a PR #749 source activation;
  no constituent-source state, refresh, or completed-bar rows were emitted

### `persist_market_event_graph_constituent_state(...)`

- Production call site before repair: `core/candidate_pool_orchestrator.py`
- Calling function: `build_candidate_pool_report(...)`
- Runtime frequency: only after candidate generator processing in candidate-pool reporting
- Conditional: yes, it depends on the candidate-pool path having run first
- Executes without candidates: only if candidate-pool report construction itself runs
- Executes for NIFTY: yes, when managed PR #749 metadata exists
- Timing-sufficient run evidence: not reached for PR #749 activation; state file absent

## Candidate-Pool Invocation Evidence

The sealed run contains `live/regime_outputs.jsonl` rows sourced from
`core.candidate_pool_orchestrator.build_candidate_pool_report`, so candidate-pool
reporting occurred. However, no source-refresh/state/completed-bar evidence files
exist, and every MEG interval row remained `producer_status=NOT_EVALUATED`.

This proves that the old candidate-pool-owned activation path was not a reliable
live-cycle activation owner for PR #749. It could emit regime/MEG observations
while still leaving the constituent source unevaluated.

## Authoritative Live Cycle Chosen

- Module: `core/orchestrator_parts/cycle.py`
- Function: `run_live_monitoring(...)`
- Call frequency: feed-aware fast monitoring cycle, not raw WebSocket tick callback
- Thread/process: existing orchestrator live-monitoring process
- NIFTY context timestamp: current `feed_epoch` when available, otherwise current wall clock
- Runs without trade candidates: yes, it executes before `FastExecutionEngine.evaluate()`
- WebSocket ownership: none; it does not create or own a WebSocket
- Broker/order authority: none; the refresh is read-only and emits `is_order_action=false`,
  `broker_api_called=false`, `allowed_for_live_execution=false`

## Repair

New shared activation owner:

```text
core.market_event_graph_constituent_refresh.refresh_market_event_graph_constituent_source
```

The coordinator:

- receives NIFTY context timestamp from the live-monitoring cycle
- invokes PR #749 constituent-source refresh
- persists the PR #749 state through one shared owner
- reports explicit refresh, source-state, subscription, and completed-bar evidence
- fails closed as `PR749_SOURCE_REFRESH_FAILED` on exception
- keeps caller-supplied completed bars authoritative

Refresh cadence:

```text
one refresh per completed minute boundary per symbol/session/reconnect generation
```

Subscription ownership:

```text
existing PR #763 observation union and ensure_subscribed_tokens path remains authoritative
```

Subscription semantics:

- first refresh per `(symbol, session_date, reconnect_generation)` may ensure subscriptions
- repeated refreshes for the same boundary do not re-subscribe
- a reconnect generation change permits one new subscription ensure
- no second WebSocket or broker client is created

Counters emitted:

```text
refresh_invocation_count
subscription_ensure_count
subscription_mutation_count
state_create_count
state_persist_count
```

## Acceptance Boundary

This repair proves offline activation only. It does not validate PR #749 live and
does not validate PR #748 consumption. Next regular-session governed validation
must prove:

```text
source refresh invocation count > 0
producer_status != NOT_EVALUATED
state file created
state persisted
target boundaries > 0
completed constituent-return rows > 0
minimum-40 coverage evaluated
MEG advances beyond MISSING_SOURCE_BARS
```
