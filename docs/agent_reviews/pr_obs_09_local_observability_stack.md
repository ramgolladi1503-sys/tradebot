# PR-OBS-09 Agent Review Evidence — Local Free Observability Stack

mode: paper_review
timestamp: 2026-05-23T06:20:00Z
candidate_id: pr_obs_09_local_observability_stack
decision: approve_scoped_local_observability_stack
reason: adds_local_stack_configuration_without_runtime_or_trading_behavior_changes
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docker-compose.observability.yml

Status: scoped implementation evidence for PR-OBS-09  
Scope: local/free observability stack configuration only

---

## Agent Work Contract

This PR implements PR-OBS-09 from the Observability Architecture roadmap.

The work contract is limited to:

- add `docker-compose.observability.yml`
- add `observability/otel-collector-config.yaml`
- add `observability/prometheus.yml`
- add `observability/tempo.yaml`
- add `observability/grafana/provisioning/datasources/datasources.yml`
- add `docs/observability/LOCAL_OBSERVABILITY_SETUP.md`
- add `tests/test_observability_local_stack.py`
- add this mandatory agent review evidence file
- keep the stack manual, local, free, and disconnected from live trading behavior

---

## Scope Guard

In scope:

- local Docker Compose stack
- Tradebot metrics endpoint container using `scripts/run_metrics_server.py`
- OpenTelemetry Collector OTLP receiver
- OpenTelemetry Collector Prometheus exporter
- Prometheus scrape config
- Tempo local trace backend
- Grafana OSS datasource provisioning
- static tests proving config shape and safety boundaries
- setup documentation and manual acceptance proof

Out of scope:

- runtime observability wiring
- candidate lifecycle wiring
- strategy changes
- ranking changes
- risk changes
- dashboard UI changes
- paper execution changes
- live execution changes
- broker calls
- order actions
- Grafana dashboards
- Loki log correlation
- evidence bundle generation
- auto-starting the stack from Tradebot runtime

---

## Grill Me Review

Review stance: challenge whether this PR creates fake observability confidence.

Findings:

- The PR does not claim runtime emits traces yet.
- The PR does not claim runtime emits metrics beyond the standalone PR-OBS-08 metrics endpoint.
- The PR does not wire collectors into runtime, strategy, ranking, risk, dashboard, paper, live, or broker paths.
- The stack is manual and local.
- The stack uses free OSS components.
- Static tests verify service names, ports, scrape targets, collector routes, and safety exclusions.
- Grafana datasource provisioning is included, but dashboards are deliberately left for PR-OBS-10.

Verdict: pass for PR-OBS-09 configuration scope.

---

## Hermes Review

Review stance: check boundaries, clarity, and maintainability.

Boundary result:

- No `core/` file changed.
- No feed runtime file changed.
- No strategy file changed.
- No ranking file changed.
- No risk file changed.
- No execution file changed.
- No dashboard file changed.
- No broker file changed.
- No runtime startup file changed.
- No external Python dependency added.

Configuration added:

- Docker Compose defines isolated observability services.
- Prometheus scrapes `tradebot-metrics:9108` and collector exporters.
- Collector accepts OTLP and routes traces to Tempo.
- Grafana provisions Prometheus and Tempo datasources.

Verdict: pass for handoff quality.

---

## GSD Review

Review stance: judge whether this PR creates useful forward movement without overengineering.

Delivery value:

- Developers can run the local observability stack with one compose file.
- Prometheus can scrape the metrics endpoint added in PR-OBS-08.
- Future OpenTelemetry runtime instrumentation has a local collector endpoint.
- Grafana has datasources without manual clicking.
- Tests protect accidental startup of live trading commands in the compose file.

Execution quality:

- The implementation is configuration-only.
- The PR avoids dashboard JSON before metrics and trace wiring are actually useful.
- The PR avoids Loki until the roadmap reaches log correlation.
- The PR avoids paid APM tools.
- The PR avoids runtime behavior changes.

Verdict: pass.

---

## QA / Safety Review

QA stance: prove this does not weaken the trading system.

Safety checks:

- The Tradebot service runs only `scripts/run_metrics_server.py`.
- The compose file sets `EXECUTION_MODE: PAPER`.
- The compose file sets `KITE_USE_API: "false"`.
- The compose file does not call `run_live.sh`.
- The compose file does not call `main.py`.
- The compose file does not reference `core/orchestrator.py`.
- The stack is not imported or started by runtime code.
- No broker or order code is changed.

Verdict: pass.

---

## Acceptance Proof

Acceptance proof for this PR:

- `docker-compose.observability.yml` defines the local stack.
- `observability/otel-collector-config.yaml` defines OTLP trace and metric pipelines.
- `observability/prometheus.yml` defines local scrape targets.
- `observability/tempo.yaml` defines a local trace backend.
- `observability/grafana/provisioning/datasources/datasources.yml` provisions Grafana datasources.
- `docs/observability/LOCAL_OBSERVABILITY_SETUP.md` records usage, endpoints, safety limits, and manual proof.
- `tests/test_observability_local_stack.py` verifies config shape and safety limits.
- Agent evidence includes the required review sections.

Expected commands:

```bash
python -m pytest tests/test_observability_local_stack.py tests/test_observability_metrics.py
python scripts/validate_agent_review_evidence.py
```

Manual command after merge:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

---

## Runtime Proof Required After Merge

Runtime proof for this PR is manual stack startup only because the PR intentionally does not wire runtime instrumentation.

Required manual proof after merge:

- `docker compose -f docker-compose.observability.yml config` succeeds.
- `docker compose -f docker-compose.observability.yml up --build` starts services.
- `http://127.0.0.1:9108/metrics` exposes metrics.
- Prometheus shows `tradebot-metrics:9108` as a target.
- Grafana opens with Prometheus and Tempo datasources.

---

## What This PR Does Not Prove

This PR does not prove:

- live runtime emits metrics
- live runtime emits traces
- candidate lifecycle instrumentation is wired
- fallback safety is enforced by dashboards
- ranking quality improved
- paper trading stability improved
- trade quality improved
- profitability improved

This PR only adds local free observability stack configuration.

---

## Human Approval

User reported PR #207 merged and requested continuation with implementation, pull request creation, and CI follow-through until green.

This implementation follows PR-OBS-09 after merged PR-OBS-08 and does not cross into runtime wiring, strategy, ranking, risk, dashboard UI, paper execution, live execution, or broker behavior.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
