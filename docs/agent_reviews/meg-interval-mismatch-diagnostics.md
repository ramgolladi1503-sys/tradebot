# MEG Interval and Source-Tick Freshness Review

## Agent Work Contract

```text
source_agent: hermes (design), then gsd (scoped execution)
action: DEFINE_CONTRACT then GENERATE_TESTS and GENERATE_PATCH
title: Preserve MEG interval truth and reject stale source ticks
scope: retain mismatch diagnostics and reject aligned snapshots with invalid, future, or stale last live ticks
requested_paths:
  - core/market_event_graph_live_runtime_bridge.py
  - tests/test_market_event_graph_live_runtime_bridge.py
  - docs/agent_reviews/meg-interval-mismatch-diagnostics.md
allowed_paths: the three requested paths only
forbidden_paths: broker/order/risk/strategy paths, credentials, live runtime state, threshold changes, bar synthesis or forward-fill
expected_tests: focused MEG bridge and interval state-machine tests; py_compile; diff check; agent review evidence gate
acceptance_proof: exact mismatch remains rejected; aligned snapshots export only when each last live tick is finite, nonfuture, and within the existing freshness limit at observation cutoff; stale/future diagnostics persisted
```

## Hermes Architecture and Contract

The Oct. 1 artifact review showed accepted source bars whose interval-end timestamp was recent while some underlying last-live-tick timestamps were roughly a minute older. Existing bar freshness alone cannot prove that the observations supporting a bar are fresh. An aligned snapshot is exportable only when the index and every constituent have the exact same finite source bar-end epoch, valid live provenance, and a finite last live tick no later than both the observation cutoff and its own bar endpoint. At the observation cutoff, each last live tick must be no older than the existing `MEG_MAX_DECISION_FRESHNESS_SEC`.

Missing/non-finite tick provenance, a tick later than the cutoff or source endpoint, or a tick older than the limit fails closed. Rejections identify symbol, endpoint, last tick, age, cutoff, configured limit, and reason. Existing interval mismatch rejection remains unchanged and precedes tick validation. Never synthesize bars, forward-fill prices, relax freshness, or substitute receipt time. Output remains read-only and confers no live-execution authority.

## Evidence and Limitations

- In `/Volumes/TradeBotData/sessions/session_2026-10-01/2026-10-01/meg-live-2026-10-01-98670a53e299-8cf253a5738e/captured_metadata.jsonl`, the accepted 13:40 cycle has `source_bar_end_epoch=1790842200`, `observed_at_epoch=1790842211.518916`, and 51 provenance-bearing bars. Recursive inspection found all 51 last live ticks older than 15 seconds at observation time, with ages from approximately 63.5 to 67.5 seconds. This is direct evidence of stale-tick exposure in an accepted snapshot; it does not establish the cause of interval mismatch rejections.
- Rejected-cycle source endpoints were not recorded in the original run, so the exact source of each `INDEX_INTERVAL_MISALIGNED` rejection remains unproven.
- This fix can increase blocked MEG cycles when input ticks are stale. That is expected fail-closed behavior.

## GSD Execution and Validation

The implementation reuses `MEG_MAX_DECISION_FRESHNESS_SEC`; it adds no config key and changes no threshold. The runtime bridge, focused bridge tests, and this review document are the scoped paths. No broker, order, strategy, credential, risk, feed configuration, or live-process behavior is changed.

Acceptance requires tests proving: (1) a fresh aligned snapshot remains exportable, (2) an aligned stale tick is rejected with symbol/age evidence, (3) future ticks relative to the bar endpoint or observation cutoff are rejected, (4) non-finite ticks are rejected, (5) a tick exactly at the configured freshness limit is accepted, (6) interval mismatch stays rejected with endpoint diagnostics, and (7) every rejection retains `read_only=true`, `is_order_action=false`, `broker_api_called=false`, and `allowed_for_live_execution=false`. Local validation: 27 focused bridge/state-machine tests passed; `py_compile`, `git diff --check`, and the agent-review evidence gate passed.

## What This Does Not Prove

It does not explain the original interval mismatches, establish sustained feed health or depth persistence throughput, prove a trading edge, or certify paper/live readiness. A future read-only live observation is needed to establish whether and how often the new rejection occurs in production data.
