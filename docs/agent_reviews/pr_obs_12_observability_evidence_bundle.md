mode: paper_review
timestamp: 2026-05-23T07:25:00Z
candidate_id: pr_obs_12_observability_evidence_bundle
decision: approve_scoped_observability_evidence_bundle
reason: adds_deterministic_observability_evidence_builder_without_product_runtime_behavior_changes
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/observability/EVIDENCE_BUNDLE.md

# PR-OBS-12 — Observability Evidence Bundle Agent Review Evidence

## Agent Work Contract

Scope:

- Add a deterministic evidence bundle builder for serialized observability events.
- Add a CLI that writes the five PR-OBS-12 JSON reports.
- Add documentation for inputs, outputs, determinism, and limits.
- Add tests proving report shape, deterministic output, validation, and safety boundaries.

Non-goals:

- No runtime auto-wiring.
- No strategy, ranking, risk, broker, or execution behavior changes.
- No dashboard UI changes.
- No claim that runtime emits complete event history yet.

## Scope Guard

Allowed files:

- `core/observability/evidence_bundle.py`
- `core/observability/__init__.py`
- `scripts/build_observability_evidence.py`
- `tests/test_observability_evidence_bundle.py`
- `docs/observability/EVIDENCE_BUNDLE.md`
- `docs/agent_reviews/pr_obs_12_observability_evidence_bundle.md`

Protected areas:

- Strategy generation remains untouched.
- Candidate scoring and ranking remain untouched.
- Risk gates remain untouched.
- Runtime entrypoints remain untouched.
- Broker adapters remain untouched.
- Product dashboard UI remains untouched.

## Grill Me Review

Challenge: Evidence files could create fake confidence if runtime does not emit complete events.

Answer: The documentation and evidence explicitly state this PR only builds reports from supplied events. Runtime completeness is deferred to later scoped PRs.

Challenge: Evidence generation must fail closed on invalid events.

Answer: The builder validates every event through the existing event schema. Missing required fields raise an evidence bundle error.

Challenge: Evidence must be deterministic for agent review.

Answer: Events are sorted by stable identity keys, and JSON output is written with sorted keys.

## Hermes Review

The implementation is small and reviewable:

- One pure module for report generation.
- One CLI for JSONL input to JSON reports.
- One focused test file.
- One focused documentation page.

No unrelated abstractions were added.

## GSD Review

This PR improves practical debugging because a reviewer can inspect:

- event summary,
- candidate decision funnel,
- fallback safety,
- feed freshness,
- latency by stage,

without opening Grafana.

This is the smallest useful PR-OBS-12 step before runtime auto-writing is introduced later.

## QA / Safety Review

Tests prove:

- all five required evidence report names exist,
- output is deterministic,
- invalid events fail closed,
- fallback executable count is reported,
- stale-feed executable count is reported,
- latency is grouped by stage,
- CLI avoids runtime startup and broker imports.

Safety boundaries:

- No product runtime behavior changes.
- No broker API behavior changes.
- No strategy or ranking mutation.
- No execution behavior mutation.

## Acceptance Proof

Expected validation commands:

```bash
python -m pytest tests/test_observability_evidence_bundle.py
python scripts/validate_agent_review_evidence.py
```

Manual local proof:

```bash
python scripts/build_observability_evidence.py --input runtime/logs/observability_events.jsonl --output-dir runtime/evidence
```

Expected output files:

```text
runtime/evidence/observability_summary.json
runtime/evidence/candidate_decision_funnel.json
runtime/evidence/fallback_safety_report.json
runtime/evidence/feed_freshness_report.json
runtime/evidence/latency_breakdown.json
```

## Runtime Proof Required After Merge

A later runtime-wiring PR must prove:

- a real run emits enough events for the bundle,
- every generated candidate reaches a terminal state,
- fallback and stale-feed safety are represented in evidence,
- CI can validate evidence schema from a run artifact.

## What This PR Does Not Prove

This PR does not prove:

- runtime emits complete event history,
- every candidate has lifecycle events,
- every live run writes evidence automatically,
- fallback safety is enforced by runtime gates,
- feed staleness is solved,
- ranking quality is improved,
- paper trading stability is improved,
- profitability is improved.

## Human Approval

Approved for PR creation as a scoped observability evidence infrastructure PR only.


## High-Risk Path Review

N/A
