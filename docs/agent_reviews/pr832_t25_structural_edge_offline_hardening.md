# PR832 — T25 Structural-Edge Decision Offline Hardening Review

mode: RESEARCH
candidate_id: PR832_T25_STRUCTURAL_EDGE_OFFLINE_HARDENING
decision: HARDEN_T25_OFFLINE_EVIDENCE_BINDING
reason: Require artifact-byte and candidate-identity verification before T25 consumes offline evidence; preserve fail-closed non-live semantics.
timestamp: 2026-08-23T06:30:00+05:30
is_order_action: false
broker_api_called: false
source: PR832_OFFLINE_HARDENING_REVIEW

## Agent Work Contract

Objective: review the narrow offline hardening of MROS task T25, `Structural-edge decision`, at the PR832 candidate. The implementation scope is `research/mros_certification/evaluation.py` plus `tests/research/test_mros_evaluation.py`; this review artifact is governance evidence only. The frozen 2026-08-18 live producer, broker integration, order routing, feed ownership, strategy generation, ranking, risk, and runtime authorization are outside scope.

Authority boundary: T25 may decide structural-edge certification only from sufficient immutable evidence. Prediction quality by itself is not tradable edge. T24 prospective evaluation remains an upstream dependency and prospective/live evidence is not supplied by this PR.

## Scope Guard

The repair requires exact candidate identity and evidence descriptors that resolve to actual regular, non-symlink JSON artifacts. T25 reads the artifact bytes itself, checks the declared SHA-256 against those bytes, parses the artifact payload, verifies the evidence kind and exact candidate SHA, and only then consumes gate-specific fields. Missing, malformed, mismatched, reused, or tampered evidence remains fail-closed. Separate trading-integration authority remains false. No high-risk production path listed by the repository validator is modified.

## Grill Me Review

Adversarial review found a material weakness in the earlier PR832 candidate: although it required `artifact_sha256` strings in caller-provided mappings, it did not open or hash any artifact, so a caller could construct an entirely PASS-shaped in-memory bundle using arbitrary 64-hex strings and obtain `CERTIFIED`. That defect is repaired in the current branch by making the artifact bytes, not the caller dictionary, authoritative.

Current adversarial questions include:

- Can caller-supplied booleans alone produce `CERTIFIED`? No; verified artifact evidence is required.
- Can a PASS-shaped in-memory dictionary with a valid-looking hash produce `CERTIFIED`? It must be rejected because an artifact path is required and the bytes are verified.
- Can artifact bytes be changed after the descriptor hash is created? The hash mismatch must be rejected.
- Can one valid artifact be reused for another evidence gate? The artifact `evidence_kind` must match the requested gate.
- Can malformed or non-exact candidate identity be accepted? The contract requires an exact 40-hex Git SHA.
- Can missing evidence be treated as success? No; it remains `NOT_CERTIFIED` or raises a fail-closed validation error.
- Can an upstream `INVALIDATED` state be propagated without verified prospective evidence? No.
- Does T25 machinery validation prove a structural edge exists? No.
- Does this change grant broker, paper, order, or live authority? No.

## Hermes Review

Evidence semantics are now artifact-backed. The caller supplies only descriptors and compatibility assertions. T25 independently reads and hashes each artifact and uses the parsed payload as evidence authority. Candidate identity and evidence kind are checked inside the artifact payload. The review found no intended path from T25 to broker/feed/order execution authority.

## GSD Review

The work remains narrowly focused on the proven T25 evidence-authority defect. It does not introduce a new observer, generic framework, producer adapter, broker dependency, or live dependency. An isolated validation base is used only to execute exact-head focused/freshness CI with full Git history; it is not a production merge target.

## QA / Safety Review

The original PR body recorded `12 passed` for the earlier reconstructed candidate. That historical run does not validate the current artifact-backed repair. The current candidate therefore remains pending fresh exact-head focused/adversarial validation. Repository-wide CI has also shown unrelated market-data quote-cache failures and freshness failures caused by shallow Git history; these are not converted into PASS and are being separated with an exact-head full-history validation gate.

Safety remains:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
LIVE_READY=false
STRUCTURAL_EDGE_CERTIFIED=false
```

## Acceptance Proof

Acceptance requires the focused T25 and freshness suites to pass on the exact final candidate with full Git history; PASS-shaped in-memory evidence must be rejected; artifact tampering and evidence-kind reuse must be rejected; malformed/missing/mismatched evidence must fail closed; execution authority must remain false; the mandatory governance gate must pass; and an independent exact-SHA review must find no remaining material evidence-authority defect. This document does not self-certify those pending gates.

## Runtime Proof Required After Merge

No live runtime proof is required to establish the narrow offline correctness of the T25 decision machinery. Separately, any future claim of prospective support or structural-edge certification requires fresh prospective evidence through T24 and the governed downstream decision process. Unit tests, fixtures, historical evidence, and this PR cannot substitute for that evidence.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, historical edge, out-of-sample edge, execution viability, prospective support, structural edge, live readiness, paper readiness, broker readiness, or authorization to trade. It does not certify T01–T35 as a whole. A later T25 decision may only consume evidence that separately satisfies those gates.

## Human Approval

The user authorized offline engineering and validation work on MROS/T25 and PR815. No approval to merge this T25 branch into `main`, alter the frozen producer, place/modify/cancel orders, enable paper/live authority, or make a structural-edge claim has been granted. This PR remains a draft research candidate until the governed evidence gates are satisfied.
