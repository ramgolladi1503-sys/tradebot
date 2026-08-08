# S002 V8 Repair Evidence

Status: REPAIR_IMPLEMENTED_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Trigger

Fresh bootstrap-independent review artifact:

`research/evidence/sprints/S002/S002_INDEPENDENT_RE_REVIEW_8E872_BOOTSTRAP_V2.md`

Controlled verdict:

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

Finding counts:

- CRITICAL: 0
- MAJOR: 1
- MINOR: 0
- mandatory UNKNOWN: 0

Blocking finding:

`8E872-V2-F-001`

## Finding reproduced from reviewer evidence

Two fail-open paths remained in candidate `8e87223efdb33bc73b58436cf590b7f3c7c10717`:

1. inherited mandatory Grade-B gate refs could be malformed or absent from declared complete prior provenance while B→A still PASSed;
2. extra known keys in `new_evidence_gate_bindings` were accepted and their values ignored when they were not required for the current transition.

## Repair

### V8 fixtures

`research/evidence/sprints/S002/S002_FIXTURES_V8_INHERITED_GATE_PROVENANCE.json`

Commit:

`e7a4f0ddd5d71deff3fc2cd3e54f46c0b4c34deb`

New attacks:

- C087 — malformed inherited mandatory refs must return controlled schema invalid;
- C088 — canonical inherited mandatory refs omitted from prior `evidence_refs` must return provenance missing;
- C089 — malformed extra known gate binding must fail closed;
- C090 — even valid-looking extra known gate bindings are rejected because the binding object must exactly match requested transition gates.

### Canonical validator

`scripts/mros/validate_s002_fixtures.py`

Commit:

`4d71405abc593daabef1bbd72afacc8e84a4598f`

Repair semantics:

- adds v8 corpus to canonical execution;
- requires exact key equality between `new_evidence_gate_bindings` and the requested transition gate set;
- canonicalizes every inherited mandatory gate evidence field;
- requires inherited mandatory gate refs to be members of declared prior `evidence_refs`;
- preserves requested-gate equality to genuinely new evidence;
- preserves old/new overlap rejection and existing fail-closed semantics.

### Contract synchronization

`research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`

Commit:

`0f88c5bfdbc43a008a558da341e5d08223d30988`

## Candidate

Exact repaired candidate HEAD to validate:

`0f88c5bfdbc43a008a558da341e5d08223d30988`

Later evidence/state-only commits must not be substituted as the implementation candidate.

## Required native gate

Run:

`python3 scripts/mros/validate_s002_fixtures.py`

Expected active checks:

`82`

Required result:

- pass = 82
- fail = 0
- exit code = 0
- exact candidate HEAD = `0f88c5bfdbc43a008a558da341e5d08223d30988`

If any check fails, S002 remains in repair.

If 82/82 passes, obtain a fresh bootstrap-independent review of that exact validated candidate. No previous review verdict may transfer across the repaired HEAD.

## Boundary

S002 remains ACTIVE and unaccepted.  
S003 remains NOT_STARTED.  
M2 remains NOT_STARTED.  
M9 remains NOT_STARTED.  
Review Board remains IMPLEMENTED_NOT_CALIBRATED.  
Audit Board remains IMPLEMENTED_NOT_CALIBRATED.  
Runtime authority remains NONE.
