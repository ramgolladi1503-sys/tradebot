# HOTFIX/EDGE-79B — Market Close Feed State Classifier

## Purpose

HOTFIX/EDGE-79B adds a pure market-close feed state classifier before EDGE-80 NoTradeOracle.

The goal is to avoid confusing websocket connectivity with stale market data near close.

## Problem this fixes

A user may see `feed disconnected`, while the real state is:

- websocket remained connected
- LTP became stale near close
- option feed or cycle latency may be stale
- market may be closed or in a close-window slowdown

NoTradeOracle needs these states as evidence instead of guessing.

## States

The classifier emits one state:

- `WEBSOCKET_DISCONNECTED`
- `LTP_STALE`
- `OPTION_FEED_STALE`
- `CLOSE_WINDOW_TICK_SLOWDOWN`
- `CYCLE_LATENCY_STALE`
- `MARKET_CLOSED`
- `FEED_STATE_HEALTHY`
- `FEED_STATE_UNKNOWN`

## Behavior

State priority is deterministic:

1. Market closed
2. Websocket disconnected
3. Cycle latency stale
4. LTP stale or close-window slowdown
5. Option feed stale or close-window slowdown
6. Unknown if no usable evidence exists
7. Healthy if all supplied freshness facts are within SLA

## Example NoTradeOracle evidence

`No trade because market was in closing window and LTP exceeded freshness SLA. WebSocket remained connected. This was not a socket disconnect.`

## Scope

This PR is diagnostic-only.

It does not reconnect feeds, resubscribe tokens, modify runtime state, change dashboard, rank candidates, score edge, or add strategy behavior.

## Test command

`PYTHONPATH=. python -m pytest tests/test_hotfix_edge_79b_market_close_feed_state.py`

## Next PR

EDGE-80 — NoTradeOracle.
