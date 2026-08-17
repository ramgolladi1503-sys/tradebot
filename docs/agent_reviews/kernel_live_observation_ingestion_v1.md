# Kernel Live Observation Ingestion V1 — Agent Review Evidence

## Agent Work Contract

Objective: add the smallest post-close, research-only evidence-ingestion boundary required for the 2026-08-18 governed observation session, based on sealed Strategy Certification Kernel authority `46dd4f7df9b63486eb633a12baf25412cd4f761d`.

Allowed scope is limited to a new external-runtime bundle sealer, a new post-close ingestion verifier, focused/adversarial tests, one focused CI workflow, and this review evidence document.

Prohibited scope: modifying the frozen live producer, changing existing kernel certification semantics, owning broker/feed/WebSocket/subscription state, writing producer databases, placing/modifying/cancelling orders, changing strategy/ranking/risk logic, granting paper/live authority, or claiming structural edge from implementation tests.

## Scope Guard

The candidate is forked from exact sealed kernel SHA `46dd4f7df9b63486eb633a12baf25412cd4f761d` and adds five files only:

- `scripts/research/hypothesis_factory/seal_live_observation_bundle_v1.py`
- `scripts/research/hypothesis_factory/ingest_live_observation_evidence_v1.py`
- `tests/research/test_live_observation_kernel_ingestion_v1.py`
- `.github/workflows/kernel-live-observation-ingestion-v1.yml`
- this review document

No existing kernel or producer source file is modified. Any expansion into live runtime wiring, feed ownership, execution logic, or an existing certification gate is out of scope and must fail this review.

## Grill Me Review

Critical attack questions were applied:

1. **Can a caller supply a SHA-looking string and bypass the real producer?** No. Both sealing and ingestion inspect the actual producer worktree with Git, require exact HEAD equality, and require a clean worktree.
2. **Can an artifact be swapped after sealing?** No. Ingestion recomputes SHA-256 and byte size; symlinks, path escape, path reuse, and mismatches fail closed.
3. **Can historical/replay/synthetic/fallback material be promoted to prospective by metadata?** Explicit provenance/source markers for those classes are rejected. CAS is restricted to `CAPTURE_THEN_OFFLINE`.
4. **Can missing observations be converted to zeros?** Explicit missing-to-zero metadata is rejected, and H1 must retain the frozen missing-bar policy.
5. **Can a valid-looking H1 manifest authorize the wrong session?** No. The adapter does not trust the manifest for the session date; it validates the exact 27-bar timestamp grid for the requested date and cross-binds CSV -> manifest -> producer SQLite hashes.
6. **Can this adapter grant trading authority if all evidence passes?** No. Its outputs explicitly keep broker, order, paper, live, and structural-edge authority false.

## Hermes Review

Architecture/plumbing review:

- Producer is read-only from this lane; Git and artifact bytes are inspected post-close.
- Runtime evidence remains under the external observation root, not tracked repository runtime.
- No secondary WebSocket, feed, broker, or subscription owner is introduced.
- The sealer creates a new bundle manifest; it does not alter raw evidence.
- The ingestion verifier creates a new verification record; it does not alter source evidence or the producer database.
- Existing kernel v2 causal/mutation/negative-control gates remain independent and unchanged.

Known trust boundary: the frozen producer launcher does not currently emit a cryptographically signed producer-attestation manifest. This candidate therefore establishes source authority from the actual frozen producer Git worktree plus exact SHA/clean-status checks and post-close artifact byte hashes. That is narrower than cryptographic runtime attestation and must not be described as such.

## GSD Review

**Goal:** make tomorrow's post-close evidence consumable by the governed kernel without touching market-hours execution.

**Scope:** five additive files on sealed kernel authority; no existing behavior changes.

**Data/evidence:** external runtime artifacts only. H1 requires the producer SQLite, exported CSV, and exporter manifest. CAS evidence remains capture-then-offline. Missing fields remain missing.

**Done condition:** exact-head focused/adversarial tests pass; artifact/provenance attacks fail closed; review evidence gate passes; independent exact-SHA review finds no material defect; the frozen post-close command resolves without broker/order authority.

## QA / Safety Review

Focused adversarial coverage includes:

- valid H1 exact-byte ingestion with zero authority;
- wrong producer SHA;
- dirty producer worktree;
- artifact tampering;
- wrong observation date;
- missing-to-zero metadata;
- incomplete H1 bar coverage;
- symlink artifact substitution;
- runtime-root path escape;
- CAS prospective-promotion attempt;
- replay metadata promotion attempt;
- repository output-path mutation attempt;
- prohibited broker/WebSocket/order imports and calls.

Safety invariants remain:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
STRUCTURAL_EDGE_CERTIFIED=false
```

## Acceptance Proof

Acceptance requires all of the following on the exact candidate SHA:

1. `python -m py_compile` succeeds for sealer, ingestion verifier, and focused tests.
2. `pytest -q -o addopts='' tests/research/test_live_observation_kernel_ingestion_v1.py` passes.
3. The focused workflow's no-authority static gate passes.
4. The repository agent-review evidence gate passes without weakening or bypassing its validator.
5. Diff remains additive and bounded to the five declared files relative to exact sealed base `46dd4f7d...`.
6. Independent exact-SHA review finds MAJOR=0 and CRITICAL=0 for this ingestion boundary.

A unit/CI pass establishes implementation validity only. It is not live/prospective evidence.

## Runtime Proof Required After Merge

This candidate is not intended to be merged into the frozen producer before the 2026-08-18 session. If this implementation is later promoted into a governed branch, runtime proof is still required separately.

For the 2026-08-18 observation, the actual post-close proof must use real session artifacts from the frozen producer worktree at `f0f5b3d3659415ab36662291e91b8f57fd8d1e07`, verify that worktree remains clean, seal the actual external runtime artifacts, and run ingestion against those exact bytes. Historical/replay/fixture/unit-test evidence cannot substitute for that runtime proof.

## What This PR Does Not Prove

This PR does **not** prove:

- that the 2026-08-18 market session has occurred successfully;
- live/prospective support for H1, CAS, PR815, T24, T25, or T26;
- profitability or structural edge;
- execution viability, fills, slippage, liquidity, or capacity;
- paper or live trading readiness;
- cryptographic runtime attestation from the producer;
- permission to place, modify, or cancel any order.

## Human Approval

No merge to the frozen producer, no trading-authority change, and no economic promotion is authorized by this review. Any later merge/promotion must be an explicit human decision after exact-SHA evidence review. The 2026-08-18 session remains observation-only with all execution-authority flags false.

## High-Risk Path Review

Reviewed high-risk boundaries:

1. **Frozen producer mutation:** no writes are made to the producer worktree or producer database. Producer Git status must remain clean.
2. **Feed/WebSocket ownership:** neither script imports Kite/broker/WebSocket clients or subscribes to market data.
3. **Order authority:** no order placement/modification/cancellation path exists. All authority flags remain false.
4. **Evidence promotion:** historical/replay/synthetic/fallback sources cannot be relabeled as prospective by this boundary.
5. **Missing-value laundering:** explicit missing-to-zero markers are rejected; H1 requires its frozen `MISSING; no forward-fill, backfill, interpolation, or substitution` policy.
6. **Artifact substitution/tampering:** every file is regular, non-symlink, runtime-root constrained, unique, size-bound, and SHA-256 verified again at ingestion.
7. **Wrong-day evidence:** bundle observation date and H1 timestamp grid are bound to the requested session date.
8. **Wrong producer authority:** declared SHA and actual producer worktree HEAD must exactly match; dirty or drifting worktrees fail closed.
9. **CAS overclaim:** CAS artifacts may only enter as `CAPTURE_THEN_OFFLINE`; this boundary cannot convert them into live/prospective edge evidence.
10. **Repository/runtime contamination:** output records must be external to both producer and kernel repositories and inside the external runtime root.

## Controlled Verdict Boundary

The maximum permitted pre-market claim after exact-head tests and independent review pass is:

`KERNEL_INGESTION_IMPLEMENTATION_VALID=PASS`

Actual August 18 evidence is not created by CI. A successful post-close ingestion may establish only that sealed artifacts match the frozen producer/session provenance contract. It does not itself establish prospective performance, structural edge, execution viability, paper/live readiness, or trading authority.
