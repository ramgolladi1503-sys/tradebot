mode: paper_review
timestamp: 2026-05-23T07:00:00Z
candidate_id: pr_obs_11_loki_log_correlation
decision: approve_scoped_loki_log_correlation
reason: adds_local_log_correlation_configuration_without_product_runtime_behavior_changes
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/observability/LOG_CORRELATION.md

# PR-OBS-11 — Loki Log Correlation Agent Review Evidence

## Agent Work Contract

Scope:

- Add local Loki configuration.
- Add local Promtail configuration.
- Add Loki as a Grafana datasource.
- Add Loki and Promtail to the local observability compose file.
- Add documentation for trace and candidate log search.
- Add static tests that prove configuration shape, read-only log mounts, and correlation fields.

Non-goals:

- No runtime instrumentation changes.
- No strategy, ranking, risk, or execution behavior changes.
- No broker API integration changes.
- No cloud dependency.
- No paid APM dependency.

## Scope Guard

Allowed files:

- `docker-compose.observability.yml`
- `observability/loki-config.yaml`
- `observability/promtail-config.yaml`
- `observability/grafana/provisioning/datasources/datasources.yml`
- `docs/observability/LOG_CORRELATION.md`
- `tests/test_observability_log_correlation.py`
- `docs/agent_reviews/pr_obs_11_loki_log_correlation.md`

Protected areas:

- Strategy generation remains untouched.
- Candidate scoring and ranking remain untouched.
- Risk gates remain untouched.
- Runtime entrypoints remain untouched.
- Broker adapters remain untouched.
- Dashboard product UI remains untouched.

## Grill Me Review

Challenge: Adding logs without runtime wiring could look like progress theater.

Answer: This PR intentionally adds only the local storage/search pipeline. Runtime log emission completeness belongs to later evidence and invariant PRs. This PR must not claim every event is logged.

Challenge: Loki labels can become high-cardinality if trace or candidate identity is used as labels.

Answer: Promtail extracts identity fields as structured metadata. Labels remain limited to stable low-cardinality values such as service, source, and execution mode.

Challenge: Mounting the full repository into Promtail would be unsafe and noisy.

Answer: Promtail mounts only `logs/` and `runtime/` read-only.

## Hermes Review

Delivery is small and reviewable:

- Local Loki service.
- Local Promtail service.
- Grafana Loki datasource.
- Documentation with query examples and limits.
- Static tests proving the config contract.

The implementation avoids unrelated abstractions and avoids changing runtime behavior.

## GSD Review

This PR improves debugging readiness because a reviewer can search structured logs by identity fields once runtime emits them:

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

Smallest useful step is completed: local log storage and local Grafana search path exist.

## QA / Safety Review

Static tests prove:

- Loki and Promtail services exist.
- Loki datasource is provisioned in Grafana.
- Promtail mounts only specific log directories read-only.
- Required correlation fields are parsed.
- High-cardinality identity fields are not configured as Loki labels.
- Documentation records acceptance and limitations.

Safety boundaries:

- Observability remains read-only.
- No product runtime behavior changes.
- No broker API behavior changes.
- No strategy or ranking mutation.

## Acceptance Proof

Expected validation commands:

```bash
python -m pytest tests/test_observability_log_correlation.py tests/test_observability_local_stack.py
python scripts/validate_agent_review_evidence.py
```

Manual post-merge checks:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

Then verify:

- Loki responds at `http://127.0.0.1:3100/ready`.
- Grafana shows the Loki datasource.
- Grafana Explore can query `{service="tradebot"}` when logs exist.

## Runtime Proof Required After Merge

A later runtime-wiring PR must prove:

- cycle logs include trace identity,
- candidate logs include candidate identity,
- blocked decisions include reasons,
- fallback and stale-feed records are searchable,
- logs correlate with traces and metrics.

## What This PR Does Not Prove

This PR does not prove:

- runtime emits complete structured logs,
- every candidate has a full decision history in logs,
- every trace has matching logs,
- fallback safety is enforced,
- feed staleness is solved,
- ranking quality is improved,
- paper trading stability is improved,
- profitability is improved.

## Human Approval

Approved for PR creation as a scoped observability infrastructure PR only.
