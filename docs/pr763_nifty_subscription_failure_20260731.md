# PR #763 NIFTY Subscription Failure - 2026-07-31

## Classified Run

- Run ID: `unified-pr748-756-20260731-f19aaf366f1a-live-549424f8`
- Campaign commit SHA: `44443e0119021c0a92b95162ac6857734670ad21`
- Composition manifest SHA: `f19aaf366f1af0997baa5d7616bb2b3897242f63056640eca10fc6da57c5ebc4`
- Evidence root: `runtime/diagnostics/unified_live_validation_pr748_756_v1/unified-pr748-756-20260731-f19aaf366f1a-live-549424f8`
- Artifact manifest SHA: `fdbdeaf67288731119df1df93cc268021c40c896ce8cfa435823a37086395d0c`
- Classification:

```text
POST_FIX_LIVE_DEFECT_OBSERVED
SUBSCRIPTION_REQUEST_FAILED
```

## Stop Window

- Launch time: derived from `presession/campaign_identity.json` and the launcher child start in the sealed root.
- Stop time: derived from `postmarket/evidence_accounting.json` `end_epoch` and sealed shutdown.
- The run was sealed and left read-only.

## First Failure

The first subscription failure was emitted from the live-source bridge as:

```text
market_event_graph_live_source_rejected reason=SUBSCRIPTION_REQUEST_FAILED identities=NIFTY
```

This occurred after the PR #749 source was enabled and the authoritative live-universe path was supplied.

## Surrounding Sealed Evidence

- `live/feed_truth_samples.jsonl` repeatedly showed `feed_fresh=true`, `ws_connected=true`, `truth_integrity_status=OK`.
- `live/subscription_events.jsonl` rows for the candidate source were present, but they did not contain feed-session or reconnect metadata because the websocket subscription success markers were not being recorded.
- `live/subscription_registry_samples.jsonl` had the same empty subscription evidence shape.
- `live/research_preoutcome_states.jsonl` showed `completed_bar_count=0` because the subscription evidence never reached a validated success state.
- `live/market_event_graph_intervals.jsonl` remained blocked with `MISSING_SOURCE_BARS`.

## Trace

```text
launcher child environment
-> main.py
-> Kite WebSocket initialization
-> PR #748 observation registry
-> PR #749 constituent-source attachment
-> authoritative universe load
-> identity-to-token resolution
-> subscription token-union creation
-> mutation queue
-> KiteTicker.subscribe(...)
-> mode assignment
-> subscription registry acknowledgement
```

Exact failure class:

1. The runtime built the correct integer token union for NIFTY and its 50 constituents.
2. The websocket path called `ws.subscribe(...)` and `ws.set_mode(...)`.
3. The code did not record `_record_subscription_requested(...)`, `_record_subscription_request_succeeded(...)`, or `_record_mode_request_succeeded(...)` at the actual subscribe sites.
4. The bridge validator in `core/market_event_graph_live_runtime_bridge.py` requires `subscribe_call_succeeded_epoch`, `mode_request_succeeded_epoch`, and related evidence to be present for every required symbol.
5. With those markers absent, the bridge rejected NIFTY as `SUBSCRIPTION_REQUEST_FAILED`.

## Failure Class

This was not a token-shape bug.

It was an evidence-bookkeeping defect:

- the runtime payload was `list[int]`;
- the authoritative universe was present and valid;
- the actual subscription call path did not persist the success markers the bridge validates.

## Fix Applied

- Added subscription request/success bookkeeping at the actual websocket subscribe sites in `core/kite_depth_ws.py`.
- Added a regression test proving the evidence record now includes NIFTY subscription request, success, and mode success markers once the integer token path is recorded.

## Validation

Focused tests after the fix:

```text
33 passed
```

The run remains a live defect until the next governed live validation confirms the subscription acknowledgement path in real runtime conditions.
