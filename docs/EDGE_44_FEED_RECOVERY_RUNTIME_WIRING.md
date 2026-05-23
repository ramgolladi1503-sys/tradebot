# EDGE-44 — Feed Recovery Runtime Wiring

## Purpose

EDGE-44 adds a small, read-only feed recovery runtime classifier that turns the current feed runtime snapshot into an explicit recovery state and action hint.

This PR does not change websocket recovery behavior. It gives operators and later runtime wiring a deterministic explanation of the feed recovery posture.

## Scope

Included:

- Pure classifier in `core/feed_recovery_runtime.py`
- Structured decision payload via `FeedRecoveryRuntimeDecision.to_payload()`
- Tests for market closed, auth blocked, healthy feed, websocket disconnected, silent feed, missing subscriptions, option feed blockers, and invalid payloads

Excluded:

- No websocket rewrite
- No new broker calls
- No order placement changes
- No execution behavior changes
- No strategy changes
- No dashboard work
- No restart threshold changes

## Recovery states

| State | Meaning | Action hint |
| --- | --- | --- |
| `MARKET_CLOSED` | Market is closed; no recovery should be attempted | `no_recovery_market_closed` |
| `AUTH_BLOCKED` | Runtime is blocked by auth and needs manual/session repair | `manual_auth_required` |
| `HEALTHY` | Feed is already healthy | `no_recovery_needed` |
| `WS_DISCONNECTED` | Runtime shows websocket disconnected | `full_restart_candidate` |
| `SILENT_FEED` | Runtime is connected-ish but no messages are flowing | `silent_reconnect_candidate` |
| `NO_SUBSCRIPTIONS` | Intended tokens exist but no tokens are subscribed | `resubscribe_candidate` |
| `OPTION_SUBSCRIPTIONS_MISSING` | Option subscriptions are missing or zero while intended tokens exist | `option_resubscribe_candidate` |
| `OPTION_FEED_BLOCKED` | Per-symbol option feed blocker is active | `option_freshness_recovery_candidate` |
| `STALE_TICKS` | Tick age is stale and needs recovery attention | `tick_stale_recovery_candidate` |
| `DEGRADED_UNKNOWN` | Feed is unhealthy but does not match a known recovery state | `inspect_feed_runtime` |

## Safety contract

The classifier is intentionally pure and side-effect free. It does not import or call Kite websocket objects, broker adapters, order modules, strategy modules, dashboard modules, or restart functions.

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_feed_recovery_runtime.py
```

## Next wiring after this PR

A later PR can attach `classify_feed_recovery_runtime(payload).to_payload()` to the runtime JSON output after proving the pure classifier contract is stable.
