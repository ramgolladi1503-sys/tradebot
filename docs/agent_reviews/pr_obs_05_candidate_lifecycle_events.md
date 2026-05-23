# PR-OBS-05 Agent Review Evidence — Candidate Lifecycle Decision Events

mode: paper_review
timestamp: 2026-05-23T07:35:00Z
candidate_id: pr_obs_05_candidate_lifecycle_events
decision: approve_scoped_candidate_lifecycle_event_shell
reason: adds_read_only_candidate_lifecycle_event_shell_without_pipeline_wiring_or_execution_side_effects
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: core/observability/candidate_lifecycle.py

Status: scoped implementation evidence for PR-OBS-05  
Scope: candidate lifecycle event shell only

---

## Agent Work Contract

This PR implements PR-OBS-05 from the Observability Architecture roadmap: Candidate Lifecycle Decision Events.

The work contract is limited to:

- add `core/observability/candidate_lifecycle.py`
- export candidate lifecycle helpers from `core/observability/__init__.py`
- add `tests/test_observability_candidate_lifecycle.py`
- add `docs/observability/CANDIDATE_LIFECYCLE_EVENTS.md`
- add this mandatory agent review evidence file
- keep all behavior read-only and disconnected from strategy, ranking, risk, dashboard, paper execution, live execution, and broker paths

---

## Scope Guard

In scope:

- `CandidateLifecycleEventEmitter`
- `CandidateLifecycleEventError`
- candidate generated event construction
- candidate normalized event construction
- candidate scored event construction
- candidate ranked event construction
- candidate displayed event construction
- candidate paper-ready event construction
- candidate paper-submitted event construction
- candidate blocked event construction
- candidate downgraded event construction
- candidate ignored-with-reason event construction
- optional JSONL write through `ObservabilityJsonLogger`
- candidate ID validation
- reason validation for blocked, downgraded, and ignored events
- tests proving emitted payloads keep `is_order_action=false` and `broker_api_called=false`

Out of scope:

- pipeline wiring
- candidate generation changes
- normalization behavior changes
- scoring changes
- ranking changes
- risk changes
- review queue changes
- dashboard changes
- paper execution changes
- live execution changes
- broker calls
- order actions
- OpenTelemetry
- Prometheus
- Grafana, Loki, Tempo, or Jaeger
- evidence aggregation

Files intentionally not touched:

- strategy modules
- ranking modules
- risk modules
- broker modules
- execution modules
- dashboard files
- runtime startup scripts
- market-data feed modules

---

## Grill Me Review

Review stance: challenge whether this PR creates fake candidate lifecycle confidence.

Findings:

- The PR does not claim real runtime candidates are fully instrumented yet.
- The PR does not wire the emitter into strategy, ranking, risk, dashboard, or paper execution paths.
- The PR only creates a tested shell future pipeline instrumentation can call.
- The emitter uses the existing event schema and JSON logger instead of raw dictionaries.
- Candidate ID is required at emitter construction.
- Blocked, downgraded, and ignored candidate events require a reason before write.
- Tests prove emitted payloads remain non-action and broker-free.

Main risk:

- Future work could mistake this shell for proof that no candidate is silently dropped.

Mitigation:

- Documentation and evidence explicitly state that lifecycle completeness requires later safe pipeline wiring and evidence checks.

Verdict: pass for PR-OBS-05 shell scope.

---

## Hermes Review

Review stance: check boundaries, clarity, and maintainability.

Boundary result:

- No strategy file changed.
- No ranking file changed.
- No risk file changed.
- No execution file changed.
- No dashboard file changed.
- No broker file changed.
- No runtime startup file changed.
- No external observability dependency added.

Public API added:

- `CandidateLifecycleEventEmitter`
- `CandidateLifecycleEventError`

Maintainability notes:

- The emitter owns candidate lifecycle event construction only.
- The emitter delegates schema validation to `ObservabilityEvent`.
- The emitter delegates JSON output to `ObservabilityJsonLogger`.
- Future pipeline wiring should call this emitter rather than duplicating candidate event payload logic.

Verdict: pass for handoff quality.

---

## GSD Review

Review stance: judge whether this PR creates useful forward movement without overengineering.

Delivery value:

- Future pipeline instrumentation can emit candidate events through one tested path.
- Candidate lifecycle events now have consistent names, stages, decisions, IDs, and safety fields.
- Future evidence-bundle work can reason over the same candidate event contract.
- Future safety invariant tests can validate that blocked/downgraded/ignored events always include reasons.

Execution quality:

- The implementation is small.
- The API is explicit.
- No external telemetry stack is introduced.
- No trading behavior is modified.
- Tests cover normal lifecycle events, terminal reason requirements, JSON writing, and candidate ID validation.

Next PR:

- Continue the Observability Architecture roadmap only after PR-OBS-05 is merged and green.

Verdict: pass.

---

## QA / Safety Review

QA stance: prove this does not weaken the trading system.

Safety checks:

- The emitter does not import broker modules.
- The emitter does not import strategy modules.
- The emitter does not import ranking modules.
- The emitter does not import risk modules.
- The emitter does not import dashboard modules.
- The emitter does not place orders.
- The emitter does not call broker APIs.
- The emitter does not mutate candidate state.
- The emitter emits schema-validated observability events only.
- The emitted payloads preserve explicit non-action safety fields.

Test coverage added:

- generated event has candidate identity and safety fields
- normal lifecycle progression events are valid non-action payloads
- blocked, downgraded, and ignored events require reasons
- blocked event serializes reason and fallback state
- downgraded and ignored events serialize reasons
- blank candidate ID is rejected
- JSON logger write emits one line without business side effects

Verdict: pass.

---

## Acceptance Proof

Acceptance proof for this PR:

- `core/observability/candidate_lifecycle.py` defines the candidate lifecycle event emitter shell.
- `core/observability/__init__.py` exports the candidate lifecycle API.
- `tests/test_observability_candidate_lifecycle.py` verifies the shell behavior.
- `docs/observability/CANDIDATE_LIFECYCLE_EVENTS.md` records the contract and exclusions.
- Agent evidence includes the required review sections.
- Evidence header includes CE metadata fields.

Expected commands:

```bash
python -m pytest tests/test_observability_candidate_lifecycle.py tests/test_observability_events.py tests/test_observability_json_logger.py
python scripts/validate_agent_review_evidence.py
```

---

## Runtime Proof Required After Merge

No live candidate lifecycle proof is required for this PR because the emitter shell is intentionally not wired into candidate pipeline execution.

Runtime proof becomes required in a future scoped PR that connects candidate lifecycle events to safe read-only pipeline boundaries.

Future runtime proof should show:

- one generated candidate event emitted from the actual safe candidate boundary
- one scored or ranked candidate event emitted from the actual safe candidate boundary
- one terminal event emitted for blocked, downgraded, displayed, paper-ready, paper-submitted, or ignored candidate state
- no broker API calls during event emission
- no order actions during event emission
- no strategy, ranking, risk, or execution behavior changes caused by observability emission

---

## What This PR Does Not Prove

This PR does not prove:

- every real candidate is instrumented
- generated candidates have complete runtime lifecycle evidence
- blocked candidates appear in runtime evidence
- there are no silent candidate drops
- candidate lifecycle evidence is aggregated
- feed freshness events are emitted
- fallback safety events are emitted
- OpenTelemetry works
- Prometheus metrics exist
- Grafana, Loki, Tempo, or Jaeger are configured
- dashboard observability exists
- paper trading stability improved
- trade quality improved
- profitability improved

This PR only adds the read-only candidate lifecycle event emitter shell.

---

## Human Approval

User requested continuation after merged PR #203 / PR-OBS-04 and asked to proceed until CI is green after the pull request is created.

This implementation follows the documented PR-OBS-05 roadmap scope and does not cross into runtime wiring, strategy, ranking, risk, dashboard, paper execution, live execution, or broker behavior.
