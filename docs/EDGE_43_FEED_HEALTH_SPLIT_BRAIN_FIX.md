# EDGE-43 — Feed Health Split-Brain Fix

## Purpose

EDGE-43 introduces a canonical read-only feed-health truth contract to reconcile global feed state and per-symbol option-feed state.

The bug pattern is split-brain feed evidence:

- global `feed_ok=false`
- websocket/effective websocket disconnected or degraded
- per-symbol option feed reason still says `OK`
- stale or absent per-symbol option tick age is not reflected in one stable decision

This PR prevents diagnostic and downstream layers from treating symbol-level option feed evidence as healthy when the global feed or symbol-specific evidence says otherwise.

## Implementation

### `core/feed_health_truth.py`

Adds:

- `SymbolFeedTruth`
- `FeedHealthTruthDecision`
- `classify_symbol_feed_truth()`
- `classify_feed_health_truth()`

The classifier reconciles:

- global `feed_ok`
- `ws_connected`
- `effective_ws_connected`
- `option_feed_block_reason_by_symbol`
- `option_last_tick_age_by_symbol`
- optional `symbol_feed_ok_by_symbol` / `feed_ok_by_symbol`

It produces stable reasons:

- `global_feed_unhealthy`
- `websocket_disconnected`
- `option_feed_blocked`
- `option_ticks_stale`
- `option_age_missing`
- `symbol_feed_unknown`

## Contract behavior

A feed is not healthy if:

- global feed is explicitly unhealthy
- websocket/effective websocket is disconnected
- any evaluated symbol has stale option tick age
- any evaluated symbol has non-OK option feed blocker

A symbol can be individually healthy while the global feed is unhealthy; the top-level decision still fails closed. This preserves evidence while preventing split-brain interpretation.

## Tests

`tests/test_edge43_feed_health_truth.py` proves:

- consistent healthy feed passes
- global unhealthy blocks even if per-symbol reason is `OK`
- disconnected websocket blocks feed truth
- stale option tick age blocks symbol and top-level truth
- option feed blocker is preserved
- symbols are discovered from payload maps
- invalid payload fails closed
- payload serialization preserves symbol reasons

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge43_feed_health_truth.py
```

## Safety

- No broker imports
- No websocket reconnect code
- No subscription mutation
- No runtime mutation
- No strategy tuning
- No dashboard changes
- No threshold loosening
- No order behavior

This is a read-only evidence contract only.

## Out of scope

- Wiring this into dashboard/reporting is later work.
- Symbol-level execution safety remains EDGE-45.
- Candidate status cleanup remains EDGE-47.
- Scoring truth hardening remains EDGE-48.
