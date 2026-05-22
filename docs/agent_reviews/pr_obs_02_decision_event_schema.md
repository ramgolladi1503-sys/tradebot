# PR-OBS-02 Agent Review Evidence — Structured Decision Event Schema

mode: paper_review
timestamp: 2026-05-23T01:25:00Z
candidate_id: pr_obs_02_decision_event_schema
decision: approve_scoped_event_schema_pr
reason: adds_read_only_observability_event_schema_and_negative_schema_tests_without_runtime_wiring
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: core/observability/events.py

Status: scoped implementation evidence for PR-OBS-02  
Scope: observability event schema only

---

## Agent Work Contract

This PR implements the second code step from the Observability Architecture roadmap: a structured decision-event schema for future logs, traces, metrics, and evidence records.

The work contract is limited to:

- add `core/observability/events.py`
- export event schema helpers from `core/observability/__init__.py`
- add `docs/observability/EVENT_SCHEMA.md`
- add unit behavior tests for event serialization and schema rejection paths
- keep the implementation independent from runtime, strategy, ranking, risk, dashboard, and broker boundaries

---

## Scope Guard

In scope:

- `ObservabilityEvent` dataclass
- `ObservabilityEventError`
- `REQUIRED_EVENT_FIELDS`
- `validate_event_payload`
- event serialization with required identity and safety fields
- candidate event validation requiring `candidate_id`
- blocked/downgraded/rejected/suppressed/ignored validation requiring a populated `reason`
- explicit rejection when the order-action safety flag is enabled
- explicit rejection when the broker-called safety flag is enabled
- schema documentation
- behavior and negative tests

Out of scope:

- runtime instrumentation
- JSON logging adapter
- OpenTelemetry spans
- Prometheus metrics
- Grafana dashboards
- Loki logs
- trace replay
- evidence bundle writer
- paper execution wiring
- live runtime wiring
- strategy behavior changes
- ranking behavior changes
- risk behavior changes
- dashboard behavior changes

Files intentionally not touched:

- strategies
- risk modules
- execution modules
- broker modules
- dashboard runtime files
- market-data feed modules

---

## Grill Me Review

Review stance: challenge whether this PR creates fake confidence.

Findings:

- The PR does not claim runtime events are emitted yet.
- The PR does not claim logs, traces, metrics, dashboards, or evidence bundles exist.
- The schema rejects candidate events without candidate identity.
- The schema rejects blocked-like decisions unless a populated reason is supplied.
- The schema rejects enabled order-action and broker-called safety flags.
- Tests include negative cases for unsafe schema states.

Main risk:

- Future PRs could bypass this schema and write raw JSON directly.

Mitigation:

- The schema doc and public export make this the canonical event contract for later adapters.

Verdict: pass for PR-OBS-02 scope.

---

## Hermes Review

Review stance: check boundaries and handoff clarity.

Boundary result:

- No runtime startup files changed.
- No market feed files changed.
- No strategy files changed.
- No ranking files changed.
- No execution boundary files changed.
- No dashboard files changed.
- No external observability dependency added.

Public API added:

- `ObservabilityEvent`
- `ObservabilityEventError`
- `REQUIRED_EVENT_FIELDS`
- `validate_event_payload`

Verdict: pass for handoff quality.

---

## GSD Review

Review stance: judge whether this PR moves the roadmap forward with useful evidence.

Delivery value:

- Future PR-OBS-03 can use the schema for structured JSON logging.
- Future PR-OBS-04 and PR-OBS-05 can emit runtime and candidate lifecycle events using this contract.
- Future PR-OBS-07 can attach event identity fields to trace spans.
- Future PR-OBS-12 can validate evidence bundle payloads against this event shape.

Execution quality:

- The implementation is small.
- The schema is deterministic and local.
- The validation fails closed on absent identity, unpopulated reasons for terminal decisions, and unsafe action flags.
- Tests cover both accepted and rejected payloads.

Next PR:

- PR-OBS-03 — Structured JSON Logging Adapter.

Verdict: pass.

---

## QA / Safety Review

QA stance: prove this does not weaken the trading system.

Safety checks:

- The schema does not import broker modules.
- The schema does not import strategy modules.
- The schema does not import dashboard modules.
- The schema does not mutate runtime state.
- The schema does not create order intent.
- The schema rejects an enabled order-action safety flag.
- The schema rejects an enabled broker-called safety flag.
- Candidate events require candidate identity.
- Blocked-like decisions require an explicit populated reason.

Test coverage added:

- runtime event serialization with required non-action fields
- candidate event rejection without `candidate_id`
- blocked event rejection without `reason`
- candidate blocked event serialization with reason and attributes
- event object rejection when order-action or broker-called flags are enabled
- raw payload rejection when the source field is absent
- raw payload rejection for unsafe non-action field state
- context-to-event merge behavior

Verdict: pass.

---

## Acceptance Proof

Acceptance proof for this PR:

- `core/observability/events.py` defines the structured event schema.
- `core/observability/__init__.py` exports the schema API.
- `docs/observability/EVENT_SCHEMA.md` records the schema contract.
- `tests/test_observability_events.py` verifies positive and negative behavior.
- Agent evidence includes the required review sections.
- Evidence header includes the required CE fields.

Expected commands:

```bash
python -m pytest tests/test_observability_events.py
python scripts/validate_agent_review_evidence.py
```

---

## Runtime Proof Required After Merge

No runtime proof is required for this PR because the schema is not wired into runtime flow yet.

Runtime proof becomes required in later PRs when events are emitted from actual runtime or candidate flow, especially:

- PR-OBS-04 Runtime Cycle Instrumentation
- PR-OBS-05 Candidate Lifecycle Decision Events
- PR-OBS-06 Feed Freshness and Fallback Safety Events

---

## What This PR Does Not Prove

This PR does not prove:

- runtime cycles emit observability events
- candidates emit lifecycle events
- structured logs are written
- traces are exported
- metrics are exported
- dashboards exist
- log correlation exists
- evidence bundles are generated
- feed freshness is measured at runtime
- fallback safety is enforced by runtime wiring
- ranking quality is improved
- profitability is improved

This PR only adds the structured event schema contract.

---

## Human Approval

User confirmed PR-OBS-01 was merged and asked to proceed.

This PR follows the documented roadmap and implements PR-OBS-02 only. The scope is intentionally narrow to avoid broad runtime changes before the schema contract is stable.
