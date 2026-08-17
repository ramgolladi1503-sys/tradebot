# PR832 — T25 Structural-Edge Decision Offline Hardening Review

## Agent Work Contract

Objective: review the narrow offline hardening of MROS task T25, `Structural-edge decision`, at the PR832 candidate. The allowed implementation scope is `research/mros_certification/evaluation.py` plus `tests/research/test_mros_evaluation.py`; this review artifact is governance evidence only. The frozen 2026-08-18 live producer, broker integration, order routing, feed ownership, strategy generation, ranking, risk, and runtime authorization are outside scope.

Authority boundary: T25 may decide structural-edge certification only from sufficient immutable evidence. Prediction quality by itself is not tradable edge. T24 prospective evaluation remains an upstream dependency and prospective/live evidence is not supplied by this PR.

## Scope Guard

Observed implementation scope is limited to the T25 evaluation module and its focused tests. The repair requires exact candidate identity and immutable SHA-256-bound evidence for positive certification; missing or inconsistent evidence remains fail-closed. Separate trading-integration authority remains false. No high-risk production path listed by the repository validator is modified.

## Grill Me Review

Adversarial questions applied to the change:

- Can caller-supplied booleans alone produce `CERTIFIED`? The intended repaired contract says no; positive certification requires bound evidence.
- Can malformed or non-exact candidate identity be accepted? The intended repaired contract requires an exact 40-hex Git SHA.
- Can missing evidence be treated as success? No; it must remain `NOT_CERTIFIED`.
- Can an upstream `INVALIDATED` state be propagated without supporting evidence? No; the repair requires evidence for that propagation.
- Does a T25 machinery pass prove a structural edge exists? No.
- Does this change grant broker, paper, order, or live authority? No.

## Hermes Review

Data/evidence semantics are explicit: candidate identity and evidence digests must bind the decision, caller compatibility assertions must agree with the evidence bundle, and absent evidence cannot be converted into a positive claim. The review found no intended path from the T25 decision function to broker/feed/order execution authority.

## GSD Review

The repair addresses the smallest proven defect in the previous T25 implementation: positive certification previously depended too heavily on caller-supplied status/boolean values rather than immutable candidate-bound evidence. The chosen scope does not introduce a new observer, generic framework, producer adapter, or live dependency.

## QA / Safety Review

The PR body records an isolated focused run of the reconstructed exact candidate module/test surface with `12 passed`; this is supporting offline implementation evidence and not a substitute for GitHub CI or prospective evidence. Current repository-wide CI also contains failures outside this two-file T25 scope and separate MROS freshness checks; those must be classified from primitive evidence before any offline PASS verdict. Safety remains:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
LIVE_READY=false
STRUCTURAL_EDGE_CERTIFIED=false
```

## Acceptance Proof

Acceptance requires all of the following before T25 offline validation can be promoted: the focused T25 suite passes on the exact final candidate; positive certification is impossible without immutable candidate-bound evidence; malformed/missing/mismatched evidence fails closed; execution authority remains false; required governance checks pass; and an independent exact-SHA verifier reviews the final candidate. This document does not self-certify those pending gates.

## Runtime Proof Required After Merge

No runtime proof is required to establish the narrow offline correctness of the T25 decision machinery. Separately, any future claim of prospective support or structural-edge certification requires fresh prospective evidence through T24 and the governed downstream decision process. Unit tests, fixtures, historical evidence, and this PR cannot substitute for that evidence.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, historical edge, out-of-sample edge, execution viability, prospective support, structural edge, live readiness, paper readiness, broker readiness, or authorization to trade. It does not certify T01–T35 as a whole. It only hardens T25's offline decision machinery if the final exact-SHA validation gates pass.

## Human Approval

The user authorized offline engineering and validation work on MROS/T25 and PR815. No approval to merge this T25 branch into `main`, alter the frozen producer, place/modify/cancel orders, enable paper/live authority, or make a structural-edge claim has been granted. This PR remains a draft research candidate until the governed evidence gates are satisfied.
