## Ops Runbook (Auth, Freshness, Feed Breaker)

### Auth Warmup Run
Use the canonical auth check to validate token health before market hours.

- Script: `scripts/auth_warmup.py`
- Output: `logs/auth_warmup.json`
- Canonical health: `core/auth_health.get_kite_auth_health()`

Expected:
- `ok: true` when token is valid.
- `ok: false` with reason code on failure.

### Freshness Thresholds
Canonical freshness SLA is computed only by `core/freshness_sla.get_freshness_status()`.

Relevant config keys:
- `SLA_MAX_LTP_AGE_SEC` (default 2.5)
- `SLA_MAX_DEPTH_AGE_SEC` (default 2.0)
- `FEED_FRESHNESS_TTL_SEC` (default 5.0 cache)

Behavior:
- Market closed: freshness enforcement suppressed, but health still reported.
- Market open: stale ticks/depth produce `ok: false` with reasons.

Logs:
- `logs/freshness_sla.jsonl` (structured events, throttled).

### Feed Circuit Breaker
Full feed restart storms trip a persistent breaker.

State file:
- `logs/feed_circuit_breaker.json`

Trip behavior:
- Set by depth WS restarts when restart storm threshold is exceeded.
- Triggers risk halt `feed_restart_storm`.

Manual clear (required):
- `python scripts/clear_feed_breaker.py --yes-i-mean-it`

Readiness gate:
- Breaker trip is a hard blocker in `core/readiness_gate`.
