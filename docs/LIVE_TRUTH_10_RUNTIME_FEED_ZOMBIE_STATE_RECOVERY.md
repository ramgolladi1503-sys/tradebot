# LIVE-TRUTH-10 — Runtime Feed Zombie State Recovery

## Context

Live session `.runtime/live_sessions/live_apm_20260529_095620` showed a dangerous runtime truth gap: the Python process stayed alive while live feed evidence degraded into a dead state.

Observed evidence:

- `ws_connected=false`
- `subscribed_tokens_count=0`
- `subscribed_option_tokens_count=0`
- `subscriptions_count=0`
- `runtime_state=null`
- `sla_status=STALE`
- LTP/depth stale for hundreds of seconds
- GLOBAL gate emitted `slo_failover` and then `risk_halt`

The process was safe because gates failed closed, but runtime health was not explicit enough about the feed-zombie condition.

## What changed

This PR adds a deterministic read-only classifier for live feed zombie state:

- `core/feed_zombie_state.py`

Runtime health now embeds the classifier result under:

```json
{
  "feed": {
    "feed_zombie": {
      "source": "feed_zombie_state_v1",
      "is_zombie": true,
      "state": "FEED_ZOMBIE",
      "blockers": [
        "feed_zombie_no_subscriptions",
        "feed_zombie_ws_disconnected",
        "feed_zombie_stale_feed"
      ],
      "read_only": true,
      "append": false,
      "is_order_action": false
    }
  }
}
```

When the zombie condition is true, runtime health also exposes:

```json
{
  "feed": {
    "runtime_state": "FEED_ZOMBIE",
    "blockers": ["feed_zombie_no_subscriptions"]
  }
}
```

## Zombie definition

A feed zombie requires all of the following:

1. Live feed is required.
2. Websocket is disconnected.
3. Subscribed token counts are zero.
4. Freshness/SLA is stale, breached, degraded, or has feed reasons.

This avoids false positives where only one field is temporarily missing.

## Hard safety boundaries

- No broker calls.
- No live orders.
- No reconnect behavior changed.
- No strategy logic changed.
- No ranking logic changed.
- No dashboard changes.
- No thresholds loosened.

## Test coverage

Focused tests cover:

- market-open live feed zombie detection
- healthy live feed not classified as zombie
- market-closed false-positive prevention
- explicit live-feed requirement offhours
- partial failure does not become zombie until all zombie conditions hold

Run:

```bash
PYTHONPATH=. python -m pytest -q tests/test_live_truth_10_feed_zombie_state.py
```
