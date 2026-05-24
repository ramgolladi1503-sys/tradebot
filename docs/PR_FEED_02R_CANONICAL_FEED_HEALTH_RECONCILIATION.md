# PR-FEED-02R — Canonical Feed Health Contract Reconciliation

## Purpose

PR-FEED-02R reconciles runtime feed overlay decisions with the canonical feed-health truth contract.

After PR-FEED-01, `core/feed_health_truth.py` is the FEED truth owner. This PR makes runtime overlay feed decisions consume that contract instead of maintaining a separate local `feed_ok` policy.

## Scope

In scope:

- Extend canonical feed truth with runtime state, feed state, LTP age, and depth age.
- Keep per-symbol option blocker and option tick age checks in canonical feed truth.
- Make `runtime_status_overlay.derive_feed_ok(...)` consume canonical feed truth.
- Add canonical feed-truth evidence to overlay payloads.
- Add targeted split-brain tests.

Out of scope:

- No websocket refactor.
- No subscription refactor.
- No token selection change.
- No feed hold gate yet.
- No warmup gate yet.
- No candidate or ranking suppression yet.
- No dashboard UI change.
- No strategy tuning.

## Changed files

- `core/feed_health_truth.py`
- `core/runtime_status_overlay.py`
- `tests/test_pr_feed_02r_canonical_feed_health_reconciliation.py`
- `docs/PR_FEED_02R_CANONICAL_FEED_HEALTH_RECONCILIATION.md`
- `docs/agent_reviews/pr_feed_02r_canonical_feed_health_reconciliation.md`

## Contract changes

Canonical feed truth now considers:

- Explicit global `feed_ok=false`
- Effective websocket disconnected
- Unsafe feed state such as `DOWN`
- Unsafe runtime state such as `STARTING`
- LTP tick age above SLA
- Depth tick age above SLA
- Per-symbol option blocker not OK
- Per-symbol option tick age above max threshold
- Symbol feed unknown evidence

Runtime overlay now exposes:

```python
classify_runtime_feed_health(feed_payload)
```

`derive_feed_ok(feed_payload)` now returns the canonical decision result.

## Negative cases proved

Tests prove:

1. Raw websocket connected cannot hide state-machine DOWN or no-message conditions.
2. Explicit `feed_ok=true` cannot override unsafe option blocker evidence.
3. Global feed OK cannot make stale symbol option ticks safe.
4. Runtime state and LTP age are part of the canonical runtime decision.
5. A fresh artifact does not override unhealthy feed payload.
6. A stale artifact remains separate from healthy feed payload.

## Acceptance criteria

- Runtime overlay feed decisions use canonical feed truth.
- Split-brain negative tests exist.
- Existing EDGE-43 feed-truth tests remain compatible.
- Feed transport behavior is unchanged.
- Strategy, ranking, and dashboard behavior are unchanged.
- CI and repo gates are green.

## Next PR

After this PR is merged and green:

```text
PR-FEED-03 — Feed Hold Gate
```

PR-FEED-03 should consume the canonical feed-health decision and prevent unsafe feed states from entering candidate or ranking paths.
