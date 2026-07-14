# Agent Review Evidence — EDGE-50 Latest Artifact Freshness Guard

mode: PAPER
candidate_id: EDGE-50-LATEST-ARTIFACT-FRESHNESS-GUARD
decision: ADD_READ_ONLY_LATEST_ARTIFACT_FRESHNESS_GUARD
reason: Latest runtime/report artifacts require explicit freshness validation before being trusted as current evidence.
timestamp: 2026-05-24T10:10:59Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_50_LATEST_ARTIFACT_FRESHNESS_GUARD.md and tests/test_edge50_latest_artifact_freshness_guard.py

## Agent Work Contract

Scope: add a pure/read-only latest artifact freshness guard.

Allowed:

- add freshness decision/report dataclasses
- support payload and JSON path assessment
- support deterministic now_epoch injection for tests
- add negative tests for stale, absent, invalid, future, and unknown timestamp paths
- add docs and agent evidence

Not allowed:

- runtime wiring
- dashboard wiring
- artifact writer changes
- strategy changes
- broker integration changes
- live runtime behavior changes
- order placement or order intent

## Grill Me Review

Risk: a `latest` file can exist but be stale, creating fake confidence in the UI/runtime report.

Decision: the guard requires explicit timestamp evidence and max-age validation.

Risk: a file can be absent or invalid and silently look like no candidates/no issue.

Decision: absent path, absent payload, non-object JSON, and invalid JSON produce explicit non-fresh statuses.

Risk: future timestamps can make stale data look fresh.

Decision: future timestamp beyond tolerance is non-fresh and carries `artifact_timestamp_in_future`.

## Hermes Review

No broker imports, runtime mutation, dashboard action, live runtime behavior, or order action is introduced.

The report emits explicit non-action fields:

- `is_order_action=false`
- `broker_api_called=false`
- `live_order_action=false`
- `broker_order_action=false`

## GSD Review

This PR solves only the artifact freshness contract. It does not wire dashboard or runtime decisions yet. That keeps the change small, testable, and reviewable.

## Scope Guard

- in_scope_list: latest artifact freshness guard module, tests, docs, agent evidence
- out_of_scope_list: runtime wiring, dashboard wiring, artifact writer changes, broker integration, strategy tuning, live behavior
- files_changed_list: core/latest_artifact_freshness_guard.py, tests/test_edge50_latest_artifact_freshness_guard.py, docs/EDGE_50_LATEST_ARTIFACT_FRESHNESS_GUARD.md, docs/agent_reviews/edge_50_latest_artifact_freshness_guard.md
- files_not_touched_list: execution engine, broker clients, dashboard app, strategy modules, runtime startup, artifact writers
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

Tests cover:

- fresh artifact
- stale artifact
- absent payload and path
- absent file path
- invalid JSON/non-object JSON
- absent timestamp
- future timestamp
- nested metadata timestamp
- batch aggregation and non-action fields

## Runtime Proof Required After Merge

- Future PR must wire runtime/report readers to call the guard before trusting latest artifacts.
- Future UI/reporting must show freshness status and blockers separately from candidate quality.
- Future runtime behavior must fail closed when latest evidence is stale or unavailable.

## What This PR Does Not Prove

- It does not prove dashboard freshness rendering.
- It does not prove runtime latest-artifact gating.
- It does not prove artifact writer freshness.
- It does not prove profitability or execution quality.

## Human Approval

Approved for PR scope: EDGE-50 only, read-only latest artifact freshness guard, no runtime/dashboard/broker behavior change.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge50_latest_artifact_freshness_guard.py
```

Expected: all EDGE-50 freshness guard tests pass.


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
