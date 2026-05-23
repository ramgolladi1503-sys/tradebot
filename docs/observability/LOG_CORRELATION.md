# Loki Log Correlation

Status: PR-OBS-11  
Scope: local/free log correlation configuration only

## Purpose

PR-OBS-11 adds local log correlation to the Tradebot observability stack.

The goal is to search structured Tradebot logs by stable observability identity so debugging can move from guessing to evidence:

- `trace_id`
- `candidate_id`
- `cycle_id`
- `run_id`
- `strategy_id`
- `stage`
- `decision`
- `reason`
- `fallback_state`
- `execution_mode`

## Stack pieces

This PR adds:

```text
Loki      local log store on port 3100
Promtail  local file reader for Tradebot log files
Grafana   Loki datasource provisioning
```

Promtail reads only local log directories mounted read-only:

```text
./logs    -> /var/log/tradebot/logs:ro
./runtime -> /var/log/tradebot/runtime:ro
```

It does not mount the full repository.

## Start

```bash
docker compose -f docker-compose.observability.yml up --build
```

## Check endpoint

```text
Loki: http://127.0.0.1:3100/ready
```

Grafana is available at:

```text
http://127.0.0.1:3000
```

Grafana is provisioned with Prometheus, Tempo, and Loki datasources.

## Query examples

Use Grafana Explore with the Loki datasource.

Find Tradebot logs:

```logql
{service="tradebot"}
```

Find logs that contain a trace identity:

```logql
{service="tradebot"} |= "trace_id"
```

Find logs that contain a candidate identity:

```logql
{service="tradebot"} |= "candidate_id"
```

Find fallback-related decision records:

```logql
{service="tradebot"} |= "fallback_state"
```

Find blocked decision records:

```logql
{service="tradebot"} |= "blocked"
```

## Label policy

High-cardinality identity fields are extracted as structured metadata, not labels.

Stored as structured metadata:

```text
trace_id
candidate_id
cycle_id
run_id
strategy_id
stage
decision
reason
fallback_state
```

Allowed as labels:

```text
service
source
execution_mode
```

This keeps Loki usable locally without creating excessive label cardinality.

## Safety boundaries

This PR is observability-only.

It must not:

- change runtime behavior
- call broker APIs
- start the trading runtime
- rescue missing data
- mutate strategy output
- mutate ranking output
- mutate risk checks
- make observability required for Tradebot to run

Promtail reads logs only. Loki stores logs only. Grafana searches logs only.

## Acceptance proof

Run static config validation:

```bash
python -m pytest tests/test_observability_log_correlation.py tests/test_observability_local_stack.py
python scripts/validate_agent_review_evidence.py
```

Manual runtime proof after merge:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

Then verify:

- Loki endpoint `http://127.0.0.1:3100/ready` responds
- Grafana shows the Loki datasource
- Grafana Explore can query `{service="tradebot"}`
- Logs containing `trace_id` can be found when such log lines exist
- Logs containing `candidate_id` can be found when such log lines exist

## What this does not prove

This PR does not wire runtime code to emit more logs.

It does not prove:

- every runtime event has a log line
- every candidate lifecycle stage is logged
- every trace has logs
- every candidate has logs
- fallback safety is enforced
- feed freshness is solved
- ranking quality is improved
- paper trading stability is improved
- profitability is improved

This PR only adds local log correlation infrastructure that future runtime instrumentation can use.
