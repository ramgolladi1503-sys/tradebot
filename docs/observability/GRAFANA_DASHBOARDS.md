# Grafana Dashboard Provisioning

PR-OBS-10 adds local Grafana dashboard provisioning for the Tradebot observability stack.

## Scope

This is configuration, documentation, and static validation only.

It provisions:

- a Grafana dashboard provider at `/etc/grafana/provisioning/dashboards`
- dashboard JSON loaded from `/var/lib/grafana/dashboards`
- one starter dashboard: `Tradebot Observability Spine`

The dashboard is intentionally local and free. It uses the Prometheus datasource created by the local observability stack.

## Dashboard panels

The starter dashboard focuses on the first debugging questions Tradebot needs to answer:

| Panel | Purpose |
| --- | --- |
| Metrics Endpoint Up | Confirms Prometheus can scrape the local Tradebot metrics endpoint. |
| Runtime Cycles Observed | Shows whether runtime-cycle metrics are being emitted once runtime wiring exists. |
| Candidate Events Observed | Shows candidate lifecycle volume once candidate event metrics are wired. |
| Blocked Candidate Reasons | Helps identify why candidates are blocked. |
| Downgraded Candidate Reasons | Helps identify why candidates are downgraded before execution readiness. |
| Fallback Safety Signals | Helps reveal fallback-data contamination. |
| Feed Freshness Signals | Helps reveal feed staleness states. |
| Observability Pipeline Metrics | Confirms the OpenTelemetry Collector metrics path is alive. |

## Safety boundaries

This PR must not:

- change strategy behavior
- change ranking behavior
- change risk behavior
- change execution behavior
- call broker APIs
- place, modify, or cancel orders
- make the observability stack required for Tradebot to run
- hide missing metrics with fake success data
- add dashboard buttons or controls that can mutate product state

## Expected local flow

```bash
docker compose -f docker-compose.observability.yml up --build
```

Then open Grafana at `http://127.0.0.1:3000` and inspect the `Tradebot / Tradebot Observability Spine` dashboard.

Some panels may show no data until the corresponding runtime and candidate metrics are wired by later PRs. That is expected. This PR proves dashboard provisioning, not full runtime instrumentation.

## Acceptance checks

```bash
python -m pytest tests/test_observability_grafana_dashboards.py tests/test_observability_local_stack.py
python scripts/validate_agent_review_evidence.py
```

Manual check after merge:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

## What this PR does not prove

- It does not prove live runtime events are emitted.
- It does not prove candidate lifecycle metrics are populated.
- It does not prove feed staleness is solved.
- It does not prove fallback candidates are safe.
- It does not prove execution readiness.
- It does not prove profitability.
