# Prometheus Metrics Export

Status: PR-OBS-08  
Scope: in-memory metrics registry and optional local `/metrics` script only

## Purpose

Metrics make Tradebot health measurable without opening logs or tracing tools.

This PR adds a small stdlib metrics registry that renders Prometheus text format. It does not wire metrics into runtime, strategy, ranking, risk, dashboard, paper execution, live execution, or broker paths.

## Metrics contract

Declared metrics:

```text
tradebot_feed_age_ms
tradebot_feed_stale_total
tradebot_candidates_generated_total
tradebot_candidates_ranked_total
tradebot_candidates_blocked_total
tradebot_fallback_candidates_total
tradebot_fallback_executable_total
tradebot_strategy_latency_ms
tradebot_scoring_latency_ms
tradebot_ranking_latency_ms
tradebot_dashboard_write_latency_ms
tradebot_paper_order_attempt_total
tradebot_live_order_attempt_total
```

`*_total` metrics are counters. Age and latency metrics are gauges.

## Safety invariant

```text
tradebot_fallback_executable_total = 0
```

If this metric is greater than zero, Tradebot is unsafe. The registry includes `assert_safety()` to fail if this count moves away from zero.

## Optional local endpoint

Run manually:

```bash
python scripts/run_metrics_server.py --host 127.0.0.1 --port 9108
```

Then read:

```text
http://127.0.0.1:9108/metrics
```

The script serves the registry only. It does not start automatically and does not connect to broker/runtime paths.

## Out of scope

This PR does not add:

- runtime metric wiring
- Prometheus scrape config
- Grafana dashboards
- OpenTelemetry collector config
- Loki log correlation
- evidence aggregation
- broker calls
- order actions
- strategy/ranking/risk/dashboard behavior changes

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_metrics.py tests/test_observability_tracing.py tests/test_observability_events.py
python scripts/validate_agent_review_evidence.py
```

## Runtime proof required later

A future wiring PR must prove actual runtime updates from safe boundaries:

- feed age is updated from the feed boundary
- stale feed count increments from the feed boundary
- generated/ranked/blocked counts update from candidate flow boundaries
- fallback executable count remains zero
- paper/live order attempt counters do not hide boundary violations
