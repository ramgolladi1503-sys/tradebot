# S001 — Acceptance-to-Verification Trace

Sprint: S001
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Branch: `research/mros-program-v1`
Status: FROZEN_FOR_REVIEW
Repair source: `S001_INDEPENDENT_REVIEW.md` F-003/F-004

## Purpose

Map every S001 design, QA, and evidence obligation identified by the authoritative manual to a deterministic verification method and repository artifact. This trace covers S001 only. WP001-level acceptance items assigned to later sprints remain future work and are not claimed complete here.

## Trace Matrix

| ID | S001 acceptance / design-freeze obligation | Verification method | Evidence / artifact | Current repair status |
|---|---|---|---|---|
| S001-AC-001 | Existing WP001 artifacts/conflicts/reusable contracts inspected | Review frozen conflict section against branch artifacts | `S001_CONTRACT_FREEZE.md` | READY_FOR_REVIEW |
| S001-AC-002 | In-scope / out-of-scope boundary frozen | Verify explicit non-goals + RC-001/RC-010 | `RESEARCH_CONSTITUTION.md`, `S001_CONTRACT_FREEZE.md` | READY_FOR_REVIEW |
| S001-AC-003 | RC-001 through RC-010 frozen | Static validator requires all rule IDs exactly once | `RESEARCH_CONSTITUTION.md`; `scripts/mros/validate_s001_contract.py` | READY_FOR_REVIEW |
| S001-AC-004 | No denominator-laundering loophole in frozen contract | Static tokens + adversarial review: post-hoc trade/observation exclusion must fail closed | RC-009 v1.0.1; `S001_INTERFACE_CONTRACT.md` I-006/I-007/E008/E009 | READY_FOR_REVIEW |
| S001-AC-005 | Component/API/schema responsibilities frozen | Review four logical contract responsibilities and required input/output surface | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-006 | Controlled knowledge classes frozen | Validator checks required class enum strings | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-007 | Controlled verdicts/statuses frozen | Validator checks required verdict/status values | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-008 | Authority scale matches manual | Validator rejects absence of `Research / R`, `Grade C/B/A/A+`, `Rejected`, `Unknown`; searches new contract for obsolete active A0–A5 semantics | `AUTHORITY_GRADES.md`, `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-009 | Stable fail-closed error contract frozen | Validator checks E001–E017 presence | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-010 | Invalid/ambiguous input fails closed | Review explicit invalid/ambiguous behavior table | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-011 | Evidence obligations frozen | Review exact branch/ref, version, input, procedure, output, independence, assumptions/unknowns requirements | `S001_INTERFACE_CONTRACT.md` | READY_FOR_REVIEW |
| S001-AC-012 | Cross-cutting decisions recorded | Confirm `DEC-2026-0001` and `DEC-2026-0002` exist and remain applicable | decision registry | READY_FOR_REVIEW |
| S001-AC-013 | Testability review maps every S001 acceptance item | Inspect this matrix for complete S001 design/QA/evidence mapping | `S001_ACCEPTANCE_TRACE.md` | READY_FOR_REVIEW |
| S001-AC-014 | Architecture/contract review performed | Independent reviewer attacks repaired HEAD | independent re-review artifact to be created by separate reviewer | BLOCKED_INDEPENDENT_REVIEW |
| S001-AC-015 | Schema/contract linting has a reproducible command | Run `python scripts/mros/validate_s001_contract.py` | validator + `S001_VALIDATION_OUTPUT.txt` | READY_FOR_REVIEW |
| S001-AC-016 | Threat/failure-mode review covers material loopholes | Independent adversarial cases include causal time, denominator laundering, self-review, runtime contamination, authority skipping | original review + required repaired-HEAD re-review | BLOCKED_INDEPENDENT_REVIEW |
| S001-AC-017 | Exact branch/commit recorded | Evidence manifest records repair base and repair commits; re-review records repaired HEAD | `S001_EVIDENCE_MANIFEST.md` | READY_FOR_REVIEW |
| S001-AC-018 | Changed-file manifest exists | Compare reviewed HEAD / repair base to repaired branch and list S001 repair paths | `S001_CHANGED_FILES.md` | READY_FOR_REVIEW |
| S001-AC-019 | Test/validation commands and outputs recorded | Execute targeted non-runtime validator and preserve stdout | `S001_VALIDATION_OUTPUT.txt` | READY_FOR_REVIEW |
| S001-AC-020 | Artifact identities/hashes available | Evidence manifest records Git blob/commit refs and SHA-256 where locally reproducible | `S001_EVIDENCE_MANIFEST.md` | READY_FOR_REVIEW |
| S001-AC-021 | Assumptions/unknowns recorded | Verify existing contract freeze sections and repair manifest | `S001_CONTRACT_FREEZE.md`, `S001_EVIDENCE_MANIFEST.md` | READY_FOR_REVIEW |
| S001-AC-022 | Independent attack evidence exists | Original review exists; repaired HEAD requires fresh independent review | `S001_INDEPENDENT_REVIEW.md`; future re-review | BLOCKED_INDEPENDENT_REVIEW |
| S001-AC-023 | Sprint decision recorded only after re-review | Ledger must remain non-accepted until independent repaired-HEAD verdict; primary agent records final decision after pass | `SPRINT_LEDGER.jsonl` | CORRECTLY_PENDING |
| S001-AC-024 | No out-of-scope runtime behavior change | Compare S001 repair changed paths; only governance/evidence/validation artifacts permitted | changed-file manifest + independent re-review | READY_FOR_REVIEW |
| S001-AC-025 | Authority/status language matches evidence | State remains `REVIEW_REQUIRED`; authority remains `Research / R` | `MROS_PROGRAM_STATE.yaml` | READY_FOR_REVIEW |
| S001-AC-026 | Evidence reproducible from documented command | Independent reviewer reruns validator on repaired HEAD and compares output | validator + output + re-review | BLOCKED_INDEPENDENT_REVIEW |
| S001-AC-027 | No unresolved Critical/High research-integrity defect | Fresh independent re-review must return no MAJOR/CRITICAL findings before acceptance | future re-review | BLOCKED_INDEPENDENT_REVIEW |
| S001-AC-028 | Evidence manifest sealed | Primary agent seals repair package before re-review; final S001 decision may reference it after re-review | `S001_EVIDENCE_MANIFEST.md` | READY_FOR_REVIEW |
| S001-AC-029 | Next sprint can begin without undocumented assumptions | Fresh independent re-review + primary sprint decision required | repaired artifacts + future re-review + ledger decision | BLOCKED_INDEPENDENT_REVIEW |

## Verification Command

Primary targeted validator:

```bash
python scripts/mros/validate_s001_contract.py
```

The command must:

1. read only governance/evidence files needed by S001;
2. perform no network/broker/runtime activity;
3. fail non-zero on missing RC rules, missing controlled vocabularies/error codes, or missing required repair wording;
4. print a deterministic PASS/FAIL checklist;
5. be rerunnable by an independent reviewer.

## Future-Sprint Boundary

The following WP001 acceptance capabilities are intentionally **not** claimed by S001 and belong to later WP001 sprints as defined by the manual:

- applying the Constitution to at least three historical examples;
- deterministic classification fixtures across reviewers;
- full negative-control suite implementing the frozen semantics;
- WP001-wide evidence manifest and work-package acceptance;
- completion of all five WP001 sprints.

Their absence must not be misreported as S001 completion defects unless the manual explicitly assigns them to S001.

## S001 Progression Rule

S001 may move from `REVIEW_REQUIRED` to accepted only when:

1. all READY_FOR_REVIEW items are present on the repaired HEAD;
2. the validator passes on that HEAD;
3. a genuinely independent reviewer re-runs/attacks the repaired HEAD;
4. no unresolved MAJOR or CRITICAL finding remains;
5. the primary agent records the sprint decision and updates the state/ledger;
6. the accepted evidence manifest references the exact reviewed repaired HEAD.

Until then, S002 remains blocked.
