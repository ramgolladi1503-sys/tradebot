# Agent Review Evidence — EDGE-38 Runtime Evidence Capture Guard

mode: PAPER
candidate_id: EDGE-38-RUNTIME-EVIDENCE-CAPTURE-GUARD
decision: APPROVED_FOR_CI_REVIEW
reason: Offline evidence capture guard only.
timestamp: 2026-05-23T21:25:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_38_runtime_evidence_capture_guard.md

## Agent Work Contract

Scope is limited to a deterministic guard report for existing diagnostic evidence packs.

Allowed files:

- `core/runtime_evidence_capture_guard.py`
- `scripts/guard_runtime_evidence_capture.py`
- `tests/test_runtime_evidence_capture_guard.py`
- `docs/EDGE_38_RUNTIME_EVIDENCE_CAPTURE_GUARD.md`
- `docs/agent_reviews/edge_38_runtime_evidence_capture_guard.md`

Not allowed:

- Strategy tuning
- Dashboard changes
- Threshold loosening
- Runtime mutation
- Broker integration changes

## Grill Me Review

Question: Does this fix feed quality?

Answer: No. It proves the evidence pack can be diagnosed through required sections.

Question: Can this change candidate selection?

Answer: No. The guard reads files and returns a report.

Question: Can this hide incomplete evidence?

Answer: No. Missing required sections return `CAPTURE_GUARD_INCOMPLETE`.

## Hermes Review

The report exposes stable keys:

- `verdict`
- `required_sections`
- `sections`
- `diagnosis_verdict`
- `diagnosis_totals`
- `evidence_map`
- `snapshots`

These keys are deterministic and serializable.

## GSD Review

EDGE-38 should not invent another analyzer. The smallest useful increment is a guard wrapper on top of the EDGE-37 replay report that proves all required diagnosis sections exist.

## Scope Guard

The implementation only adds an offline guard module, CLI, tests, and docs. It does not alter runtime behavior.

## QA / Safety Review

- The guard reads evidence directories or bundles.
- The guard does not import broker adapters.
- The guard does not mutate runtime state.
- The guard fails closed when feed, freshness, or final no-trade sections are missing.
- The output includes safety metadata proving it is not an order action.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_runtime_evidence_capture_guard.py
```

Expected proof:

- Complete synthetic live diagnostic evidence returns `CAPTURE_GUARD_OK`.
- Required sections are feed, freshness, fallback, candidate funnel, score flattening, and final no-trade reasons.
- Tar bundle input is supported.
- Safety metadata is serialized.
- Incomplete snapshots fail closed with `CAPTURE_GUARD_INCOMPLETE`.
- Markdown output includes every required section.

## Runtime Proof Required After Merge

A later real evidence run should prove:

- The CLI can read an actual `runtime/evidence/live_diag_*` pack.
- The JSON report is saved as a durable artifact.
- Incomplete evidence packs fail the guard with a clear missing-section reason.

## What This PR Does Not Prove

- It does not fix quote truth.
- It does not fix feed split-brain behavior.
- It does not improve strategies.
- It does not prove profitability.
- It does not change candidate generation.

## Human Approval

Approved to proceed as an offline evidence-capture guard because it turns manual diagnosis expectations into deterministic report sections without changing trading behavior.

## Approval Evidence

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_runtime_evidence_capture_guard.py
```
