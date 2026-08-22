# TEP v1 — Canonical Requirement Catalogue

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

This catalogue repairs Phase-0 review finding F-001. Each requirement is stable and enumerable. Detailed implementation traceability is completed as milestones produce interfaces, tests and evidence.

| ID | Requirement | Owner | Dependencies | Authority implication | Acceptance method | Expected evidence |
|---|---|---|---|---|---|---|
| REQ-GOV-001 | Frozen specifications MUST outrank implementation convenience and conversational instructions. | Enterprise Governance | SPEC-000 | None | contradiction review | exact-SHA spec review |
| REQ-GOV-002 | UNKNOWN, MISSING, ZERO and PASS MUST remain semantically distinct. | Enterprise Governance | SPEC-000, LAW-010 | None | adversarial truth tests | test report |
| REQ-GOV-003 | Every material capability MUST have one authoritative owner. | Enterprise Governance | SPEC-002 | None | ownership matrix review | architecture report |
| REQ-MISSION-001 | Missions MUST be versioned declarative definitions, not opaque controller programs. | Mission Engine | ADR-003 | mission admission | schema validation | definition hash + validator result |
| REQ-MISSION-002 | Mission completion MUST be computed from durable task/evidence state against a frozen completion contract. | Mission Engine | REQ-STATE-001 | None | lifecycle tests | completion evaluation record |
| REQ-TASK-001 | Tasks MUST declare dependencies, capability, owner, retry/wait policy and terminal contract. | Mission Engine/TBOS | REQ-MISSION-001 | capability-specific | schema tests | task definition record |
| REQ-STATE-001 | Mission/task lifecycle state MUST be durable and transactionally committed. | TBOS/State Store | ADR-007 | None | crash/failure injection | state/event transaction evidence |
| REQ-STATE-002 | Illegal state transitions MUST be rejected. | TBOS | REQ-STATE-001 | None | transition matrix tests | negative test report |
| REQ-STATE-003 | A completed worker execution MUST NOT be rerun solely because validation was interrupted. | TBOS | REQ-STATE-001, REQ-WORKER-002 | mutation-dependent | crash-resume test | execution/result fingerprint evidence |
| REQ-SCHED-001 | Scheduler MUST compute runnable work from durable dependencies/state and MUST NOT execute domain business logic. | TBOS Scheduler | LAW-004 | None | architecture + scheduler tests | dependency/run queue evidence |
| REQ-SCHED-002 | Waiting/blocked independent work MUST NOT prevent unrelated runnable work. | TBOS Scheduler | LAW-024 | None | multi-lane scheduler test | event timeline |
| REQ-SCHED-003 | CI/time/external waits SHOULD consume no worker invocation while no repair decision is required. | TBOS/CI Service | ADR-018 | None | wait simulation | worker invocation counter + events |
| REQ-EVENT-001 | Durable events MUST be idempotently consumable after restart. | TBOS Event Router | REQ-STATE-001 | None | duplicate/restart tests | event ledger |
| REQ-AUTH-001 | Authority MUST precede every governed mutation. | Authority Service | LAW-001 | all mutation capabilities | adversarial mutation tests | AuthorityDecision + mutation evidence |
| REQ-AUTH-002 | GitHub metadata, push, merge, destructive cleanup, broker write, order, paper and live authorities MUST be independent unless explicitly composed by frozen policy. | Authority Service | LAW-014 | named capabilities | authority matrix tests | decision ledger |
| REQ-AUTH-003 | Irreversible operations MUST refresh relevant authority and target fingerprints immediately before mutation. | Authority Service/owning service | LAW-012 | mutation capability | drift injection | JIT decision evidence |
| REQ-CAP-001 | Every material capability MUST declare owner, prerequisites, authority, validators and evidence contract. | Capability Registry | REQ-GOV-003 | capability-specific | catalogue completeness | capability registry snapshot |
| REQ-WORKER-001 | Workers MUST be replaceable execution backends and MUST NOT own authoritative mission state or self-grant authority. | Worker Manager | ADR-005 | scoped worker execution | sandbox/adversarial tests | WorkerExecution record |
| REQ-WORKER-002 | Worker outputs MUST remain proposals until independently validated by the owning contract. | Worker Manager/Validator | LAW-022 | capability-dependent | forged-PASS test | validator record |
| REQ-WORKER-003 | Worker execution MUST be bounded by exact task fingerprint, allowed scope and resource/token budget. | Worker Manager | REQ-TASK-001 | worker execution | scope escape tests | execution envelope |
| REQ-DRIVER-001 | Drivers MUST adapt external systems without owning business policy. | Driver Framework | LAW-006 | driver-specific | dependency/architecture tests | boundary test report |
| REQ-GIT-001 | Git service MUST establish exact repository/ref/diff authority before repository mutation. | Git Service | REQ-AUTH-003 | PUSH_BRANCH etc. | ref drift tests | ref/diff snapshot |
| REQ-GH-001 | GitHub service MUST own PR metadata/state semantics. | GitHub Service | REQ-GOV-003 | UPDATE_PR_METADATA | service tests | PR snapshots |
| REQ-CI-001 | CI failures MUST be classified before candidate source repair when baseline/environment causation is plausible. | CI Service | ADR-019 | rerun/repair as applicable | baseline comparison corpus | classification evidence |
| REQ-CI-002 | Required CI/review gates MUST NOT be weakened merely to obtain PASS. | CI/Review Services | LAW-020 | None | adversarial policy tests | configuration diff + test result |
| REQ-MERGE-001 | Merge candidates MUST be JIT rechecked against refreshed protected source authority. | Merge Service | REQ-AUTH-003, REQ-GIT-001 | MERGE_PR | head/base drift tests | premerge gate record |
| REQ-MERGE-002 | Repository merges MUST serialize and invalidate affected stale downstream readiness after main changes. | Merge Service/TBOS | ADR-011 | MERGE_PR | concurrent lane integration test | merge/event timeline |
| REQ-MERGE-003 | Successor PR creation MUST be exceptional and justified by explicit lineage/preservation/reconstruction evidence. | GitHub/Merge Services | ADR-012 | UPDATE_PR_METADATA/PUSH_BRANCH | scenario review | relationship record |
| REQ-CLEAN-001 | Destructive cleanup MUST require proof that unique commits, untracked data, active runtime role, credentials/evidence and unresolved mappings are absent or preserved. | Cleanup Service | LAW-018 | DELETE_WORKTREE/filesystem delete | destructive safety corpus | preservation manifest |
| REQ-EVID-001 | Governed evidence MUST bind claim, producer, validator, source/data authority, immutable artifact reference and limitations. | Evidence Service | ADR-008, ADR-016 | None | schema + tamper tests | EvidenceRecord |
| REQ-EVID-002 | Sealed evidence MUST be immutable/content-addressed; corrections MUST supersede rather than overwrite. | Evidence Service | REQ-EVID-001 | evidence seal | tamper test | hashes + supersession record |
| REQ-KNOW-001 | Knowledge MUST retain provenance/freshness and MUST NOT grant mutation authority. | Knowledge Service | LAW-007 | None | forged-authority test | query + rejected decision |
| REQ-OBS-001 | Long-running work MUST expose current state, progress time, blocker/wait reason, attempts and evidence/result refs. | Observability | REQ-STATE-001 | None | observability contract test | status snapshot |
| REQ-LIVE-001 | Read-only observation MUST remain capability-separated from broker/order execution. | Live Observation Service | ADR-021 | START_READ_ONLY_OBSERVER only | authority adversarial test | decision/event evidence |
| REQ-LIVE-002 | Session subscription sets MUST be derived from dated launch contracts rather than permanent historical totals. | Live Observation Service | ADR-022 | read-only launch | dated-plan tests | launch plan + convergence report |
| REQ-LIVE-003 | Live runtime outputs MUST be isolated from frozen source checkouts. | Live Observation Service | ADR-023 | runtime write path | path enforcement test | runtime manifest |
| REQ-LIVE-004 | Market observers MUST support calendar-aware graceful shutdown/drain. | Live Observation Service/TBOS | ADR-024 | observer lifecycle | simulated/real read-only lifecycle test | shutdown evidence |
| REQ-RES-001 | Research hypotheses/specifications MUST be frozen before protected outcome/holdout access where selection bias matters. | Research Governance | IR-018 | research data authority | leak audit | frozen spec/hash + access ledger |
| REQ-RES-002 | Failed hypotheses MUST be durably retained with enough provenance to prevent blind retesting. | Research Governance/Knowledge | LAW failed-research policy | None | registry tests | failure registry entry |
| REQ-RES-003 | Broad discovery MUST track search pressure/multiple testing. | Research Governance | LAW-017 | None | research mission tests | search-pressure ledger |
| REQ-RES-004 | Economic certification MUST distinguish historical, OOS, execution, prospective and structural-edge states and include realistic applicable costs. | Research Validators | LAW-016 | certification authority | validator corpus | certification evidence bundle |
| REQ-MIG-001 | Existing infrastructure MUST be classified REUSE_VERIFIED, REIMPLEMENT_REQUIRED or UNKNOWN_PROVENANCE before migration/replacement. | Migration Service/Architecture | M10 | replacement/delete authority as applicable | migration review | provenance/equivalence report |
| REQ-HUMAN-001 | Human escalation MUST be reserved for policy-defined irreducible decisions and MUST include decision requested, alternatives, evidence, consequence of no decision and authority required. | TBOS/Authority/Governance | LAW human-role policy | human-only capability | escalation contract tests | escalation record |
| REQ-ARCH-001 | Critical dependency boundaries MUST be mechanically testable rather than relying only on code review convention. | Architecture Governance | D-001..D-010 | None | import/dependency boundary tests | architecture test report |
| REQ-CONFIG-001 | Mission-relevant configuration MUST be versioned/hashed and referenced by execution/evidence. | Configuration Registry | IR-026 | configuration change as applicable | reproducibility test | config hash refs |
| REQ-SECRET-001 | Secrets MUST be mediated and excluded from durable prompts/state/evidence bodies. | Secret/Driver boundary | IR-027 | credential use | scanning/adversarial tests | secret-scan report |

## Phase-0 traceability rule

Every frozen ADR, interface, state contract and capability MUST be mapped to one or more REQ IDs from this catalogue. `16_PHASE0_TRACEABILITY_MATRIX.md` is the canonical mapping surface and satisfies this requirement without requiring duplicate inline REQ columns in every source table. Source documents MAY carry inline REQ references for readability, but those are secondary and MUST NOT contradict document 16.

M1+ implementation artifacts MUST extend the chain to implementation, tests and evidence. A missing implementation/test link before implementation exists is not a Phase-0 defect; a missing architectural mapping in document 16 is.