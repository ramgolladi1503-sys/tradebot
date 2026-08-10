# PR #782 Remaining Evidence Contracts — Agent Review Evidence

## Agent Work Contract

Close only the three evidence gaps found after the governed 2026-08-04 Kite observation:

1. canonical seal markers required by PR #782;
2. persisted read-only authority snapshots;
3. append-only MEG traversal and successful-export evidence.

The work must remain read-only and must not change strategy, risk, feed semantics, broker wiring, execution, order routing, fills, or profitability claims.

## Scope Guard

Allowed production paths:

- `core/read_only_live_evidence.py`
- `core/kite_read_only_observation_runtime.py`
- `scripts/seal_pr763_read_only_evidence.py`

Allowed supporting paths:

- focused tests and workflow;
- this review document;
- offline closure documentation after tests pass.

The previously sealed 2026-08-04 evidence root is immutable and is not modified or retroactively certified.

## Grill Me Review

Questions that must remain answerable from code and tests:

- Does a successful MEG export remain provable after later duplicate or rejected cycles?
- Can the same completed index interval create more than one successful export?
- Are misalignment retries bounded?
- Does every completed observation interval produce durable authority evidence without order authority?
- Does the final sealer create exactly `artifact_manifest.json`, `SHA256SUMS`, and `SEALED`?
- Does tampering or a missing required artifact fail closed?
- Is the strict broker/execution import boundary unchanged?

## Hermes Review

Evidence chain:

```text
real/synthetic completed interval
→ bounded MEG evaluation
→ append-only traversal event
→ append-only successful export when accepted
→ read-only authority snapshot
→ graceful drain evidence
→ canonical seal markers
→ PR #782 verifier
```

Every ledger row includes a deterministic semantic hash and stable session/interval identity. Latest-cycle summaries are convenience views only; cumulative certification truth comes from append-only ledgers.

## GSD Review

Goal: remove the three exact failed gates without architecture drift.

Signals:

- one authority ledger and one latest authority snapshot;
- one MEG traversal ledger and one success-only export ledger;
- one canonical sealing command reusing the repository sealer;
- focused positive and negative controls;
- no changes to broker, execution, risk, strategy, or feed modules.

Decision boundary:

```text
Offline tests passing ≠ live certification.
```

A fresh governed Kite market session remains mandatory.

## QA / Safety Review

Required safety properties:

- `read_only=true`;
- `broker_write_authority=false`;
- `order_authority=false`;
- `allowed_for_live_execution=false`;
- `allowed_for_paper_execution=false`;
- no broker adapter, order router, fill, or execution construction;
- production import firewall remains strict;
- canonical verifier continues to fail closed.

Tests cover canonical sealing, authority snapshots, cumulative MEG success, duplicate suppression, bounded retries, and a synthetic full PR #782 fixture.

## Acceptance Proof

Acceptance requires all of the following on one commit:

- changed modules compile;
- focused suites pass in isolated Python processes;
- suites pass again in reverse order;
- protected runtime drift is false;
- diff check passes;
- Agent Review Evidence Gate passes;
- repository CI does not reveal a change-related regression.

At the time this document was first added, CI was still running. No offline pass verdict is asserted here until the checks complete.

## Runtime Proof Required After Merge

Do not merge merely because offline checks pass.

One fresh governed Kite read-only market-hours session must prove:

- 51-token subscription/FULL truth;
- completed index and constituent intervals;
- at least one durable live-source MEG export;
- append-only authority snapshots;
- persistence reconciliation and graceful shutdown;
- canonical seal markers;
- `PASS_READ_ONLY_POST_MARKET_RELIABILITY`;
- PR #783 certificate assembly only after PR #782 passes.

## What This PR Does Not Prove

This PR does not prove:

- profitability or structural trading edge;
- strategy quality;
- broker execution correctness;
- fill quality or slippage;
- paper/live trading readiness;
- unattended or autonomous trading readiness;
- successful certification of the already sealed 2026-08-04 run.

## Human Approval

Human approval is required before merge and before starting the fresh governed Kite session.

Reviewers must confirm:

- the previous sealed evidence remains untouched;
- the diff stays within the declared scope;
- all required checks pass on the final head;
- the PR remains draft and marked `DO NOT MERGE — FRESH GOVERNED KITE SESSION REQUIRED` until runtime proof is reviewed.
