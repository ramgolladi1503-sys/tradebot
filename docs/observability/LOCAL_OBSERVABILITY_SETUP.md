# Local Observability Setup

Status: PR-OBS-09  
Scope: local/free observability stack configuration only

## Purpose

This setup gives Tradebot a local observability spine without paid APM tools.

It starts:

- Tradebot metrics endpoint on port `9108`
- OpenTelemetry Collector on ports `4317`, `4318`, `8888`, and `8889`
- Prometheus on port `9090`
- Tempo on port `3200`
- Grafana OSS on port `3000`

## Start

```bash
docker compose -f docker-compose.observability.yml up --build
```

## Check endpoints

```text
Tradebot metrics: http://127.0.0.1:9108/metrics
Prometheus:       http://127.0.0.1:9090
Tempo:            http://127.0.0.1:3200
Grafana:          http://127.0.0.1:3000
```

Grafana is provisioned with Prometheus and Tempo datasources.

## What Prometheus scrapes

Prometheus scrapes:

```text
tradebot-metrics:9108
otel-collector:8888
otel-collector:8889
```

`tradebot-metrics:9108` comes from `scripts/run_metrics_server.py`, added in PR-OBS-08.

## What the OpenTelemetry Collector accepts

The collector accepts OTLP traffic at:

```text
otel-collector:4317  # OTLP/gRPC
otel-collector:4318  # OTLP/HTTP
```

Traces are exported to Tempo. Metrics are exposed through the collector Prometheus exporter on port `8889`.

## Safety boundaries

This stack is observability-only.

It must not:

- change runtime behavior
- start live trading
- call broker APIs
- place orders
- rescue missing data
- turn fallback candidates executable
- mutate strategy output
- mutate ranking output
- weaken risk checks
- become required for Tradebot to run

The Tradebot metrics service starts only the metrics endpoint. It does not start the trading runtime.

## Acceptance proof

Run static config validation:

```bash
python -m pytest tests/test_observability_local_stack.py
python scripts/validate_agent_review_evidence.py
```

Manual runtime proof after merge:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

Then verify:

- `http://127.0.0.1:9108/metrics` exposes Tradebot metrics
- Prometheus target `tradebot-metrics:9108` is up
- Grafana opens with Prometheus and Tempo datasources

## What this does not prove

This PR does not prove:

- runtime code emits live metrics
- runtime code emits traces
- candidate lifecycle is wired into observability
- fallback safety is enforced by dashboard panels
- trading edge improved
- paper trading stability improved
- profitability improved

This PR only adds the local free stack configuration that future instrumentation can use.
