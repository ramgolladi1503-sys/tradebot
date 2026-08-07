# S001 Independent Constitution Review

Reviewer role: Independent reviewer / skeptic; not the S001 implementation agent
Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S001
Branch: `research/mros-program-v1`
Reviewed HEAD: `004486fb185e052b3dee8d9f43cc838ea92bfc7e`
Review date: 2026-08-08
Final verdict: `S001_INDEPENDENT_REVIEW_REPAIR_REQUIRED`

## Independence statement

This reviewer did not implement S001 and did not rewrite the Constitution to obtain a passing result. This artifact records independent attack evidence only. This review does not advance `MROS_PROGRAM_STATE.yaml`, accept S001, begin S002, or grant market/runtime authority.

## Authoritative sources and reviewed artifacts

1. MROS Enterprise Engineering Manual & Research Handbook v1.0, repository-adopted by `DEC-2026-0001`; manual SHA-256 recorded by the program as `53350c3f60f2046180726077b0c18fb52222d6826d4d6e10fc746a46ab80cb39`.
2. `research/constitution/RESEARCH_CONSTITUTION.md` — blob `ada165b22a2a966b25e77bd0130ed6e976b635df`.
3. `research/evidence/sprints/S001/S001_CONTRACT_FREEZE.md` — blob `e976cce9fbbd5b4580da9787dbfa70122333a403`.
4. `research/governance/AUTHORITY_GRADES.md` — blob `c485a0f8915f2ff7d75a290a1e9f53d1c3fd6782`.
5. `research/program/MROS_PROGRAM_STATE.yaml` — reviewed through HEAD `004486fb185e052b3dee8d9f43cc838ea92bfc7e`; state is `M1 / WP001 / S001 / REVIEW_REQUIRED`.
6. `research/program/SPRINT_LEDGER.jsonl` — blob `b449145cd6acf25209dc13926a3a5161d1d1cf4c`.
7. `research/program/WORK_PACKAGE_LEDGER.jsonl` — blob `61c6b290b28e87506c1e9e364862eadcfe6aa108`.
8. `research/program/MILESTONE_LEDGER.jsonl` — blob `37aefa66fb4bbefc0039d15423fd7195a19e9d92`.
9. `research/registry/decisions/DEC-2026-0002.md` — blob `b1a50f6b3203c65151c367f22f7af82a4f3afe53`.
10. `AGENTS.md` — blob `dce2ba8432b11bc57d2f0c52f4987c2687afadc6`.

## Manual baseline used

The manual defines S001 as WP001 Contract & Design Freeze. Required design work includes repository conflict inspection; explicit scope; component/API/schema contracts, invariants, statuses, error codes and evidence obligations; ADRs for cross-cutting choices; and a testability review mapping every acceptance criterion to verification. Required evidence includes branch/commit, changed-file manifest, test commands/outputs, artifact IDs/hashes, assumptions/unknowns, independent attack notes, and a sprint decision record. S001 is Done only when acceptance criteria are satisfied, the evidence manifest is sealed, the sprint decision is recorded, and the next sprint can begin without undocumented assumptions.

The WP001 work-package acceptance criteria are broader and are not treated as already due merely because S001 exists: three historical examples, evidence-only promotion, consistent independent classification, no unresolved Critical/High defects, no out-of-scope changes, reproducibility, required report sections, and a complete reviewable WP evidence manifest. WP001 itself requires all five sprints. The current repository correctly states that WP001 is not complete.

## RC-001 through RC-010 verdicts

| Rule | Verdict | Review |
|---|---|---|
| RC-001 No Drift | PASS | Matches manual and requires a decision/impact review for material scope change. |
| RC-002 Evidence Promotion | PASS | Explicitly requires new registered evidence and predeclared gates; rejects CI/prose/confidence as evidence. |
| RC-003 Unknown Is Legal | PASS | `UNKNOWN`/`INSUFFICIENT EVIDENCE` are explicitly legal and cannot be coerced to support/rejection for closure. |
| RC-004 Independent Attack | PASS | Self-certification is prohibited and substantive independence is required. |
| RC-005 Calibration Before Trust | PASS | Strong verdicts are bounded by demonstrated operating characteristics, detection power, and representation coverage. |
| RC-006 No Silent Supersession | PASS | Prior claims/evidence/decisions remain queryable and belief changes require explicit supersession. |
| RC-007 Falsifiability | PASS | Material claims require destroyers and review/re-evaluation triggers. |
| RC-008 Causal Time | PASS | Explicitly prohibits look-ahead, future-derived membership, future labels in predictors, and outcome-contaminated feature selection. |
| RC-009 No Denominator Laundering | MAJOR | Correctly protects failed hypotheses/search budgets, but does not explicitly prohibit post-hoc observation/trade exclusion or metric-denominator reframing. A reported hit rate can therefore be selectively reframed without clearly violating the written rule. |
| RC-010 Runtime Separation | PASS | Runtime can consume governed certified knowledge but cannot invent/reinterpret/promote/weaken research authority. |

## S001 acceptance / design-freeze verdicts

| Requirement | Verdict | Evidence / problem |
|---|---|---|
| Inspect existing WP001 artifacts and record conflicts/reusable contracts | PASS | `S001_CONTRACT_FREEZE.md` records authority-scale, program-shape and PR-execution conflicts. |
| Freeze in-scope/out-of-scope boundaries | PASS | Constitution and freeze artifact constrain WP001 and explicitly exclude runtime/strategy work. |
| Define component/API/schema contracts, invariants, statuses, error codes and evidence obligations | MAJOR | Invariants/evidence obligations exist in prose, but no explicit component/API/schema contract, controlled status vocabulary, or error-code contract is frozen for S001. The manual specifically requires these before implementation. |
| ADRs for cross-cutting choices | PASS | `DEC-2026-0001` and `DEC-2026-0002` cover manual adoption and program execution mechanics. |
| Testability review maps every acceptance criterion to verification | MAJOR | The freeze artifact lists WP001 acceptance tests but does not provide a criterion-to-test/evidence trace for every S001 acceptance criterion. |
| QA: architecture/contract review, schema linting, threat/failure-mode review | MAJOR | This independent review supplies architecture/adversarial review, but there is no schema-lint evidence or documented executable/targeted validation command for the frozen contract. |
| Required evidence: exact branch/commit | PASS | Branch and implementation/reviewed commits are recorded. |
| Required evidence: changed-file manifest | MAJOR | No S001 changed-file manifest was found in the reviewed S001 evidence. |
| Required evidence: test commands and outputs | MAJOR | No S001 test/validation command output was found; `[skip ci]` is correctly not represented as QA evidence. |
| Required evidence: artifact IDs/hashes | MINOR | Key commits/blobs are identifiable, but S001 does not yet have a sealed evidence manifest with canonical evidence identity. |
| Required evidence: assumptions/unknowns | PASS | Present in `S001_CONTRACT_FREEZE.md`. |
| Required evidence: independent review/attack notes | PASS | This artifact supplies the independent review/attack evidence. |
| Required evidence: sprint decision record | MAJOR | Sprint ledger remains `IN_PROGRESS`; no S001 ACCEPT/REJECT/UNKNOWN decision exists, which is correct before review but blocks S001 Done. |
| No out-of-scope behavior change | PASS | Reviewed S001 changes are governance/program artifacts; no runtime authority is granted. |
| Authority/status language matches evidence | PASS | Repository says `Research / R`, `REVIEW_REQUIRED`, and not accepted. |
| Evidence reproducible from documented commands | MAJOR | No documented S001 verification commands/outputs exist yet. |
| No Critical/High research-integrity defect remains | MAJOR | The denominator-laundering loophole and missing enforceable contract/testability artifacts remain material governance defects. |
| Evidence manifest sealed and next sprint can begin without undocumented assumptions | MAJOR | No sealed S001 evidence manifest exists; S001 therefore does not satisfy its manual Definition of Done. |

## Adversarial cases

| Case | Result | Classification |
|---|---|---|
| A — predictor uses information five minutes after decision timestamp | RC-008 invalidates affected evidence until repaired/rerun | PASS |
| B — 70% hit rate after post-hoc exclusion of inconvenient trades | RC-009 protects search/campaign denominators but does not explicitly govern observation/trade denominator selection | MAJOR |
| C — cannot distinguish no edge from insufficient power | RC-003 and RC-005 require `Unknown`/bounded conclusion | PASS |
| D — implementing agent declares its own independent attack satisfied | RC-004 forbids this | PASS |
| E — governance sprint directly changes broker/execution behavior | RC-001/RC-010 plus scope lock and `AGENTS.md` prohibit it | PASS |
| F — Research/R hypothesis jumps directly to Grade A | burden-of-proof/promotion language says no level may be skipped; Grade A requirements independently block it | PASS |
| G — exceptional backtest lacks provenance/reproducibility | burden of proof and repository/reproducibility rules block high authority | PASS |
| H — zero survivors becomes `no structural edge exists` | RC-003/RC-005 and burden of proof require a bounded/Unknown conclusion absent adequate power/representation authority | PASS |
| I — newer calibrated evidence contradicts historical evidence | RC-006 requires explicit supersession while preserving history | PASS |
| J — obsolete A0–A5 scale used for new MROS records | `AUTHORITY_GRADES.md` explicitly supersedes A0–A5; finding must be corrected, not silently translated | PASS |
| K — green CI is presented as scientific certification | RC-002 explicitly says green CI alone is not new evidence | PASS |
| L — runtime output is used to retroactively validate a research claim | RC-010 explicitly prohibits this | PASS |

## Findings

### F-001 — MAJOR — RC-009 does not close the post-hoc metric denominator loophole

The manual's minimum RC-009 wording focuses on failed hypotheses and search budgets. The Constitution expands this to multiplicity denominators and campaign identities but still does not state that an experiment may not selectively exclude observations/trades/outcomes after seeing results or redefine a reported metric denominator post hoc. Because the rule is titled `No Denominator Laundering`, future agents could plausibly claim that post-hoc hit-rate filtering is outside its literal scope.

Required repair: freeze an explicit denominator rule covering search-family denominators and within-experiment/reporting denominators. Post-hoc exclusions must be prohibited unless preregistered or treated as a new exploratory analysis with preserved original denominator and reduced authority.

### F-002 — MAJOR — Required S001 interface/schema/status/error contract is missing

S001 freezes prose rules but does not freeze the manual-required component/API/schema contract, controlled statuses, error codes, and fail-closed semantics that S002 is supposed to implement. Deferring the entire machine-readable contract to S002 means S002 can choose semantics that were not actually frozen by S001.

Required repair: add a narrow S001 contract artifact defining at least the inputs/outputs or schema surface that S002 must implement, controlled knowledge/verdict/authority/status vocabularies, invalid/ambiguous input behavior, and fail-closed error/status semantics. Do not implement S002.

### F-003 — MAJOR — Acceptance-to-verification trace is incomplete

The manual requires every S001 acceptance criterion to map to a verifiable test/evidence artifact. The current freeze document lists WP-level tests but not a full S001 trace matrix.

Required repair: add an S001 acceptance trace mapping each design/QA/evidence criterion to an existing or planned verification artifact and command. Planned S002/S003 tests may be identified as future, but S001's own design-freeze criteria must be verifiable now.

### F-004 — MAJOR — S001 evidence package is incomplete

No changed-file manifest, test/validation command outputs, sealed S001 evidence manifest, or sprint decision record exists at reviewed HEAD. The ledger correctly remains `IN_PROGRESS`; that honesty is a PASS for authority semantics, but it means S001 cannot yet be accepted.

Required repair: after the design repairs, run targeted non-runtime validation, record exact commands/outputs, produce the S001 changed-file/evidence manifest with hashes, and let the primary agent issue the sprint decision only after independent re-review.

### F-005 — MINOR — Evidence identity is not yet canonical

The S001 artifact records commits and this review records blob hashes, but no canonical S001 Evidence ID is assigned. This is not independently authority-breaking because WP003 owns the full identity registry, but S001 should still seal a local evidence manifest that can later be migrated without ambiguity.

## Finding counts

- MINOR: 1
- MAJOR: 4
- CRITICAL: 0
- UNKNOWN: 0

## Unresolved unknowns

None that prevent this review verdict. WP001-level historical-example application and cross-reviewer classification consistency are intentionally future WP001 work and remain unproven; they must not be represented as completed by S001.

## Final reviewer verdict

`S001_INDEPENDENT_REVIEW_REPAIR_REQUIRED`

The Constitution is directionally strong and nine of ten RC rules pass this attack as written, but S001 does not deserve acceptance yet. The post-hoc denominator loophole is material, and the manual-required design contract/testability/evidence package is incomplete.

The primary MROS agent may safely consume this review as independent evidence. It may not advance to S002 until the S001 repairs are made, independently re-reviewed, the S001 evidence manifest is sealed, and the sprint decision is recorded under the manual.
