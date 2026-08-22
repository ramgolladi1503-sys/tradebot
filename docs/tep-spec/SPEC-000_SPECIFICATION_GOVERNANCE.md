# SPEC-000 — TEP Specification Governance

Status: DRAFT  
Version: 1.0.0-draft  
Platform: TradeBot Engineering Platform (TEP)  
Normative: Yes

## 1. Purpose

This specification defines how the TEP specification itself is governed. It exists to prevent architecture from drifting through chat history, implementation convenience, agent behavior, or undocumented local decisions.

TEP specifications are prescriptive. Repository artifacts and reproducible evidence outrank summaries and conversational memory.

## 2. Scope

This document governs:

- specification identifiers and versions;
- normative language;
- requirements and traceability;
- architecture decisions;
- change control;
- review and freeze states;
- implementation conformance;
- evidence requirements;
- deprecation and supersession.

It does not define runtime implementation details.

## 3. Normative language

The terms MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, MAY and OPTIONAL are normative.

A requirement without verifiable acceptance evidence is incomplete.

## 4. Authority hierarchy

When sources disagree, authority is ordered as follows:

1. immutable/reproducible repository and runtime evidence;
2. frozen TEP specifications and accepted ADRs;
3. current repository source at the bound SHA;
4. generated reports with provenance;
5. agent summaries;
6. chat memory.

No lower authority may silently override a higher authority.

## 5. Specification lifecycle

Every normative document has exactly one lifecycle state:

- DRAFT — actively designed; not implementation authority;
- REVIEW — complete enough for adversarial review;
- FROZEN — approved implementation authority;
- SUPERSEDED — replaced by a named newer authority;
- RETIRED — intentionally no longer applicable.

Only FROZEN documents may create mandatory implementation requirements.

## 6. Requirement identifiers

Requirements use stable IDs:

`REQ-<DOMAIN>-<NNN>`

Examples:

- REQ-MISSION-001
- REQ-AUTH-014
- REQ-CI-021

IDs are never reused. Removed requirements remain in history with disposition.

Each requirement MUST state:

- normative statement;
- rationale;
- owner subsystem;
- dependencies;
- authority implications;
- acceptance method;
- evidence expected.

## 7. Traceability

Normative implementation follows:

Requirement → Architecture/ADR → Interface or state contract → Implementation → Test → Evidence.

A production capability MUST NOT be certified if any mandatory traceability link is missing.

## 8. Architecture decisions

Material architectural choices require an ADR with:

- decision ID;
- context;
- considered alternatives;
- decision;
- consequences;
- affected requirements;
- migration impact;
- reversal/removal strategy.

Implementation convenience is not sufficient rationale for an ADR.

## 9. Change control

A frozen specification may change only through a reviewed change that identifies:

1. exact prior authority;
2. exact proposed delta;
3. affected requirements/interfaces/tests;
4. backward compatibility;
5. migration plan;
6. evidence needed to accept the change.

Silent semantic changes are prohibited.

## 10. Drift prevention gate

Before adding a capability, the proposer MUST answer:

1. Does equivalent capability already exist?
2. Which subsystem owns this responsibility?
3. Which requirement and ADR justify it?
4. Can configuration/data express it instead of new code?
5. What new authority is required?
6. What failure modes are introduced?
7. How is the capability resumed after interruption?
8. What evidence proves correctness?
9. What is the complexity cost?
10. How can it be deprecated or removed?

Missing answers block implementation.

## 11. Truth law

TEP MUST NOT convert:

- UNKNOWN to PASS;
- MISSING to ZERO;
- UNIT_TEST_PASS to LIVE_PASS;
- HISTORICAL_PASS to FORWARD_PASS;
- CORRELATION to CAUSATION;
- BACKTEST_EDGE to TRADABLE_EDGE.

These distinctions apply to engineering and trading evidence alike.

## 12. Mutation governance

Authority MUST precede mutation.

Every mutating capability MUST declare its required authority and produce attributable evidence.

Broker write, order, paper, live, destructive cleanup, GitHub metadata, push and merge authorities are distinct capabilities and MUST NOT be inferred from one another.

## 13. Implementation conformance

Workers such as Codex are implementation agents, not specification authorities.

Workers MAY implement, test, repair and refactor within frozen contracts. They MUST NOT silently redesign architecture to achieve a passing result.

If implementation cannot satisfy a frozen requirement, the correct outcome is BLOCKED or a specification change proposal—not weakened validation.

## 14. Review standard

A specification reaches FROZEN only after review establishes:

- internal consistency;
- ownership clarity;
- dependency clarity;
- explicit authority boundaries;
- explicit failure/recovery behavior;
- testability;
- traceability;
- no unresolved critical contradictions.

## 15. Versioning

TEP specification versions use semantic versioning at the package level.

- MAJOR: incompatible constitutional/architectural change;
- MINOR: backward-compatible normative capability addition;
- PATCH: clarification with no intended semantic change.

Individual documents carry their own revision metadata.

## 16. Evidence preservation

Evidence referenced by a frozen decision MUST be preserved with provenance sufficient to locate and verify it. Cleanup MUST NOT destroy unique evidence, local-only commits, or unresolved authority.

When ambiguity remains, default disposition is PRESERVE.

## 17. Acceptance criteria

SPEC-000 may move to REVIEW when:

- identifier conventions are defined;
- lifecycle states are defined;
- authority hierarchy is explicit;
- traceability is mandatory;
- drift prevention is mandatory;
- change control is explicit;
- implementation-agent authority is bounded.

It may move to FROZEN only with the Phase-0 constitution package.