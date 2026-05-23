# PR-OBS-10 — Grafana Dashboard Provisioning Evidence

## Agent Work Contract

Build local Grafana dashboard provisioning for the existing free observability stack.

Allowed scope:

- Grafana dashboard provider configuration.
- Static dashboard JSON.
- Compose mounts needed to load dashboards.
- Documentation for local usage and limitations.
- Static tests proving provisioning paths, panel intent, and safety boundaries.

Out of scope:

- No runtime instrumentation.
- No strategy changes.
- No ranking changes.
- No risk changes.
- No execution changes.
- No broker calls.
- No order actions.
- No paid observability tools.
- No dashboard mutation controls.

## Scope Guard

Changed files are limited to observability configuration, observability docs, tests, and agent evidence.

The PR must remain read-only from a product behavior perspective. The dashboard may observe metrics when they exist, but it must not create, mutate, suppress, or rescue product decisions.

## Grill Me Review

Risk: Dashboard panels can create fake confidence if metrics are not wired yet.

Mitigation: Documentation explicitly states that empty panels are expected until later runtime and candidate metrics are wired. Tests only prove provisioning and query intent, not runtime truth.

Risk: Dashboard provisioning can accidentally become a runtime dependency.

Mitigation: Compose keeps Grafana inside the optional local observability stack. Product runtime files are not changed.

Risk: Dashboard controls could mutate state.

Mitigation: This PR adds static panels only. No buttons, API controls, order actions, or mutation endpoints are added.

## Hermes Review

The implementation should be understandable by a reviewer without running Grafana:

- Compose mounts dashboard provider and dashboard JSON read-only.
- Provider YAML points Grafana at `/var/lib/grafana/dashboards`.
- Dashboard JSON uses the existing Prometheus datasource UID.
- Tests parse the JSON and assert required panel titles and PromQL expressions.
- Docs explain what the dashboard proves and does not prove.

## GSD Review

This PR is useful because it converts the local observability stack from raw services into a reviewable debugging surface.

It does not solve feed staleness, fallback contamination, candidate ranking, execution readiness, or profitability. It only creates the dashboard skeleton required to see those signals once later PRs wire real metrics.

## QA / Safety Review

Acceptance commands:

```bash
python -m pytest tests/test_observability_grafana_dashboards.py tests/test_observability_local_stack.py
python scripts/validate_agent_review_evidence.py
```

Manual local check after merge:

```bash
docker compose -f docker-compose.observability.yml config
docker compose -f docker-compose.observability.yml up --build
```

## Acceptance Proof

Required proof for this PR:

- Dashboard provider exists.
- Dashboard JSON is valid.
- Dashboard uses the Prometheus datasource.
- Dashboard includes panels for runtime cycles, candidate events, blocked reasons, downgraded reasons, fallback safety, feed freshness, and collector health.
- Compose mounts dashboard files read-only.
- No runtime, strategy, risk, execution, or broker files are changed.

## Human Approval

Ready for human review after CI passes.
