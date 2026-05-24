# PR-FEED-04 — Feed Recovery Warmup Gate

## Purpose

PR-FEED-04 adds a small read-only feed recovery warmup gate.

The goal is to prevent executable ranking output from resuming immediately after feed recovery until explicit warmup evidence is satisfied.

A feed can move from unhealthy to healthy, but that does not prove the stream is stable enough yet. This PR makes that transition visible and fail-closed while warmup is active.

## Scope

In scope:

- Add `core/feed_recovery_warmup_gate.py`.
- Consume canonical `FeedHealthTruthDecision`.
- Consume explicit recovery context:
  - previous feed health
  - recovered timestamp
  - current timestamp
  - healthy sample count
  - minimum warmup seconds
  - minimum healthy samples
- Return zero-rank, zero-executable ranking report while warmup is active.
- Preserve normal ranking after warmup criteria are satisfied.
- Fail closed when recovered timestamp is missing during a recovery transition.
- Add negative tests for recovery warmup suppression.

Out of scope:

- No websocket refactor.
- No reconnect logic.
- No resubscribe logic.
- No subscription changes.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order intent.
- No live execution behavior.

## Contract

`classify_feed_recovery_warmup(feed_health, ...)` returns read-only evidence:

- `warmup_active=true` when current feed is healthy after recovery but warmup evidence is incomplete.
- `warmup_active=false` when current feed is healthy and no recovery transition is supplied.
- `warmup_active=false` when current feed is healthy after recovery and both elapsed time and healthy sample criteria are satisfied.
- `warmup_active=true` when current feed truth is unhealthy.
- `is_order_action=false`.
- `append=false`.

`apply_feed_recovery_warmup_to_ranking(scores, feed_health, ...)` returns:

- Existing normal ranking when warmup is clear or complete.
- Zero ranks and zero executable count when warmup is active.
- `feed_recovery_warmup` blocker when blocked.
- Source score count in metadata for traceability.

## Negative cases proved

Tests prove:

1. Recovery warmup evidence is read-only and non-action.
2. Recently recovered feed suppresses executable ranking until elapsed time and healthy sample criteria are satisfied.
3. Ranking resumes after warmup criteria are satisfied.
4. Missing recovery timestamp fails closed during a recovery transition.
5. Unhealthy feed truth fails closed.
6. Healthy feed without recovery context preserves ranking.
7. Warmup evidence is JSON serializable and non-action.

## Acceptance criteria

- Recovery warmup gate is read-only.
- No broker/order/live behavior is introduced.
- No reconnect/resubscribe/websocket behavior is introduced.
- Recovered feed cannot immediately emit executable ranked output without warmup evidence.
- Healthy feed after completed warmup preserves existing ranking behavior.
- Existing ranking and feed hold tests remain compatible.
- CI and repo gates are green.

## Next PR

After this PR is merged and green, continue to the next scoped feed-readiness step only:

```text
PR-FEED-05 — Exact Option Token Freshness Gate
```

Do not broaden into websocket rewrites, strategies, dashboard UI, or live order behavior.
