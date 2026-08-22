# TEP v1 — Acceptance Criteria

Status: DRAFT
Version: 1.0.0-draft

## Phase-0 acceptance

TEP Phase 0 passes only if all criteria below are independently reviewable from repository artifacts.

### AC-001 — Complete constitution
The frozen Phase-0 constitution MUST contain, at one exact SHA, SPEC-000, SPEC-001, SPEC-002 and normative documents `00_MASTER_PLAN.md` through `16_PHASE0_TRACEABILITY_MATRIX.md`. Phase review reports are evidence artifacts, not normative constitution members. Adding/removing a normative Phase-0 document requires this manifest to change before freeze.

### AC-002 — Terminology consistency
Canonical terms have one meaning across the package. Conflicting definitions are resolved before freeze.

### AC-003 — Ownership completeness
Every foundational responsibility has exactly one authoritative owner. Shared collaboration is allowed; ambiguous state/policy ownership is not.

### AC-004 — Dependency integrity
The module graph has no prohibited ownership cycles and defines enforceable dependency boundaries.

### AC-005 — Durable execution semantics
Task/mission lifecycle, crash recovery, leases, idempotency, wait behavior and validation-after-restart are specified.

### AC-006 — Authority model
Material mutations have explicit capability-specific authority boundaries. Tool possession/access cannot substitute for authorization. `11_CAPABILITY_AUTHORITY_CATALOGUE.md` is the canonical authority-default source.

### AC-007 — Evidence and traceability model
Evidence, knowledge, state and worker output are explicitly distinct. Certification scope cannot exceed validator/evidence scope. Every Phase-0 REQ has architectural traceability through `16_PHASE0_TRACEABILITY_MATRIX.md`; implementation/test/evidence links are explicitly deferred until their milestone exists and cannot be inferred from Phase-0 PASS.

### AC-008 — Repository convergence model
The architecture supports independent parallel preparation/CI and serial refreshed-main integration, without requiring successor PR creation as the default.

### AC-009 — CI continuation model
CI waits consume no worker tokens; terminal failures are classified before repair; baseline/environment failures are not automatically blamed on candidates.

### AC-010 — Preservation model
Unique commits, dirty/untracked files, runtime roles, credentials/evidence and unresolved mappings block destructive cleanup until preserved/proven safe.

### AC-011 — Live safety
Read-only observation is isolated from broker/order execution authority; defaults remain false; live evidence is not inferred from historical/mock evidence.

### AC-012 — Research truthfulness
The architecture preserves leakage, OOS, costs, robustness, multiple testing, independent verification and prospective distinctions; operational success cannot certify economic edge.

### AC-013 — Complexity control
v1 non-goals and admission rules prevent unnecessary distributed infrastructure, generic automation sprawl and duplicate services.

### AC-014 — Migration safety
The roadmap explicitly preserves validated existing artifacts until provenance/equivalence and rollback are established.

### AC-015 — Implementation gate
No document claims implementation validity merely because architecture text exists. `TEP_IMPLEMENTATION_AUTHORIZED` remains false until the constitution is frozen. Phase-0 PASS may authorize only the next explicitly bounded milestone; it does not authorize all M1–M10 work.

## Phase-0 review procedure

1. Freeze candidate package SHA.
2. Run mechanical checks for missing documents, duplicate IDs, broken cross-references, orphaned REQ/LAW/IR identifiers and prohibited terms/authority contradictions.
3. Perform architecture consistency review.
4. Perform adversarial safety/governance review.
5. Record all findings with severity and exact document/section.
6. Repair findings without silently changing unrelated scope.
7. Repeat against new exact SHA.
8. Freeze only when no critical/high unresolved contradiction remains and all acceptance criteria have explicit evidence.

## Phase-0 verdicts

Allowed verdicts:

- PASS — all criteria satisfied at exact SHA;
- BLOCKED — external/authority prerequisite prevents review completion;
- FAIL — specification materially violates criteria;
- INCOMPLETE — package is not yet review-ready.

No PARTIAL PASS is a freeze verdict.

## Implementation milestone acceptance

Each M1–M10 milestone requires its own exact-SHA evidence bundle including tests, negative/adversarial tests where applicable, authority state, known limitations and independent validation result. Passing an earlier milestone never certifies a later one.