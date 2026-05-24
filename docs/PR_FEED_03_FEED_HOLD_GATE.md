# PR-FEED-03 — Feed Hold Gate

## Purpose

PR-FEED-03 adds a small read-only feed hold gate that consumes canonical feed-health truth before ranking output is allowed.

The goal is to ensure unsafe feed evidence cannot produce executable-ranked output.

## Scope

In scope:

- Add `core/feed_hold_gate.py`.
- Consume `FeedHealthTruthDecision` from canonical feed truth.
- Return a zero-rank, zero-executable ranking report when feed truth is unhealthy.
- Preserve normal ranking behavior when feed truth is healthy.
- Add negative tests for stale/unhealthy feed suppression.

Out of scope:

- No websocket refactor.
- No reconnect logic.
- No subscription changes.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order intent.
- No live execution behavior.

## Contract

`classify_feed_hold(feed_health)` returns read-only evidence:

- `hold_active=true` when canonical feed truth is unhealthy.
- `hold_active=false` when canonical feed truth is healthy.
- `is_order_action=false`.
- `append=false`.
- `broker_api_called=false` is not required because the gate does not call brokers.

`apply_feed_hold_to_ranking(scores, feed_health, directional_balance=None)` returns:

- Existing normal ranking when feed truth is healthy.
- Zero ranks and zero executable count when feed truth is unhealthy.
- `feed_health_hold` blocker when blocked.
- Source score count in metadata for traceability.

## Negative cases proved

Tests prove:

1. Unhealthy feed truth activates hold.
2. Unhealthy feed truth suppresses all executable ranking output.
3. Healthy feed truth preserves normal ranking order.
4. Missing/invalid feed truth fails closed.
5. Hold evidence is JSON serializable and non-action.

## Acceptance criteria

- Feed hold gate is read-only.
- No broker/order/live behavior is introduced.
- Unhealthy feed truth cannot emit ranked executable output.
- Healthy feed truth preserves existing ranking behavior.
- Existing ranking tests remain compatible.
- CI and repo gates are green.

## Next PR

After this PR is merged and green, continue to the next scoped feed-readiness step only. Do not broaden into websocket rewrites, strategies, dashboard UI, or live order behavior.