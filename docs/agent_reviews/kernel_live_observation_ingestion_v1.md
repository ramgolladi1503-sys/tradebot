# Kernel Live Observation Ingestion V1 — Agent Review Evidence

## Summary

Adds a post-close, research-only evidence boundary on top of sealed Strategy Certification Kernel authority `46dd4f7df9b63486eb633a12baf25412cd4f761d`.

The implementation does not change the frozen live producer, strategy logic, ranking, risk, feed ownership, WebSocket subscriptions, broker behavior, order behavior, paper/live authority, or the existing kernel certification gates.

## Scope

Changed implementation scope is limited to:

- `scripts/research/hypothesis_factory/seal_live_observation_bundle_v1.py`
- `scripts/research/hypothesis_factory/ingest_live_observation_evidence_v1.py`
- `tests/research/test_live_observation_kernel_ingestion_v1.py`
- `.github/workflows/kernel-live-observation-ingestion-v1.yml`
- this review document

The sealer verifies the actual producer worktree is clean at an explicit exact Git SHA, restricts artifacts to regular non-symlink files under an external runtime root, hashes every artifact, and writes a new bundle manifest without mutating source evidence.

The ingestion adapter re-verifies the producer worktree and SHA, recomputes artifact hashes and sizes, rejects path escape/symlink/reuse, rejects replay/synthetic/historical/fallback promotion markers, preserves missingness, cross-checks the H1 27-bar CSV against its source/output hashes, and keeps CAS artifacts `CAPTURE_THEN_OFFLINE` only.

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

## Known Trust Boundary

The frozen `run_live_safe.sh` launcher does not itself emit a cryptographically signed producer-attestation artifact. This adapter therefore establishes source authority by independently reading the actual frozen producer worktree with Git, requiring exact SHA plus clean status, and byte-hashing the external artifacts post-close.

For H1, the existing exporter manifest does not explicitly carry the observation date or current exporter Git SHA. The kernel does not trust those missing fields. Instead it derives the observation date from the required exact 27-bar timestamp grid and binds the H1 CSV to the producer SQLite through the exporter's `source_sha256`, `source_path`, and `output_csv_sha256` fields.

This is an implementation/provenance boundary, not proof that market observations are economically useful.

## Validation

The focused suite covers:

- valid H1 exact-byte ingestion with zero authority;
- wrong producer SHA;
- dirty producer worktree;
- artifact tampering;
- wrong observation date;
- missing-to-zero metadata;
- incomplete H1 bar coverage;
- symlink artifact substitution;
- runtime-root path escape;
- CAS prospective promotion attempt;
- replay metadata promotion attempt;
- repository output-path mutation attempt;
- prohibited broker/WebSocket/order imports and calls.

CI compiles the implementation, runs the focused/adversarial suite on the exact PR head, and statically asserts the no-authority contract.

## Controlled Verdict Boundary

The maximum permitted pre-market claim after exact-head tests and independent review pass is:

`KERNEL_INGESTION_IMPLEMENTATION_VALID=PASS`

Actual August 18 evidence remains unavailable until the market session occurs. A successful post-close ingestion may establish only that sealed artifacts match the frozen producer/session provenance contract. It does not itself establish prospective performance, structural edge, execution viability, paper/live readiness, or trading authority.

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
STRUCTURAL_EDGE_CERTIFIED=false
```
