# SPEC-001 — TEP Specification Writing Standard

Status: DRAFT  
Version: 1.0.0-draft  
Normative: Yes

## 1. Purpose

Define the mandatory structure and writing rules for TEP normative specifications so that humans and implementation workers interpret the same contract.

## 2. Required document header

Every normative specification MUST declare:

- stable document ID and title;
- lifecycle state;
- version;
- normative/non-normative status;
- owner subsystem;
- dependencies;
- supersedes/superseded-by when applicable.

## 3. Required subsystem template

Every subsystem specification MUST contain, where applicable:

1. Purpose
2. Responsibilities
3. Explicit non-responsibilities
4. Requirements
5. Dependencies
6. Public interfaces
7. Inputs and outputs
8. Data model
9. State machine
10. Events
11. Authority requirements
12. Failure taxonomy
13. Recovery/resume semantics
14. Idempotency/concurrency semantics
15. Security and safety boundaries
16. Observability/evidence
17. Performance/capacity constraints
18. Testing
19. Acceptance criteria
20. Migration/deprecation
21. Open questions

An omitted section MUST say why it is not applicable.

## 4. Requirement style

Requirements MUST be atomic, testable and unambiguous.

Bad: `The scheduler should be robust.`

Good: `REQ-SCHED-014: After process restart, the scheduler MUST reconstruct runnable task state from durable state without re-executing a task whose completion evidence has already been committed.`

## 5. Examples are non-authoritative

Examples illustrate requirements but MUST NOT create hidden requirements. If behavior is mandatory, it requires a REQ ID.

## 6. State definitions

Every state MUST define:

- entry conditions;
- legal outgoing transitions;
- prohibited transitions;
- durable fields;
- recovery behavior;
- evidence emitted.

No undocumented runtime state is permitted in a conforming implementation.

## 7. Interface definitions

Every public operation MUST define:

- operation name;
- caller contract;
- input schema;
- output schema;
- required authority;
- preconditions;
- postconditions;
- idempotency;
- errors;
- evidence/events.

## 8. Failure definitions

Failures MUST be classified rather than flattened into generic exceptions.

Minimum categories:

- candidate/source defect;
- dependency defect;
- repository baseline defect;
- environment failure;
- infrastructure failure;
- external-service failure;
- authority failure;
- evidence failure;
- data-quality failure;
- invariant violation;
- unknown.

UNKNOWN MUST remain UNKNOWN until evidence supports reclassification.

## 9. Diagrams

Textual diagrams MAY be used during v1. A diagram MUST not be the only normative definition of behavior; corresponding requirements/contracts remain authoritative.

## 10. Cross references

Cross references MUST use stable document IDs, requirement IDs, ADR IDs or interface IDs rather than conversational descriptions.

## 11. Terminology

Terms defined in the canonical glossary MUST be used consistently. A specification MUST NOT redefine a glossary term locally without a formal glossary change.

## 12. Trading claims

Specifications dealing with research or live markets MUST distinguish:

- IMPLEMENTATION_VALID;
- HISTORICAL_EDGE_SUPPORTED;
- OUT_OF_SAMPLE_SUPPORTED;
- EXECUTION_VIABLE;
- PROSPECTIVE_SUPPORTED;
- STRUCTURAL_EDGE_CERTIFIED.

No lower state implies a higher state.

## 13. Implementation neutrality

Architecture documents SHOULD specify contracts before concrete implementation choices. Where a technology is mandatory, an ADR MUST justify it.

## 14. Review checklist

Before REVIEW:

- all MUST/SHALL statements have stable requirement IDs or are constitutional rules;
- undefined terminology is eliminated;
- failure and recovery semantics are explicit;
- authority requirements are explicit;
- test/acceptance method exists;
- open questions are visible rather than silently assumed.

## 15. Acceptance criteria

SPEC-001 is acceptable when every later TEP subsystem can be authored from this template without inventing local documentation conventions.