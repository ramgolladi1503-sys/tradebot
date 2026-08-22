# TEP v1 — ADR Compliance and Open Decisions

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

This document repairs Phase-0 findings F-002, F-006 and F-007. `05_ARCHITECTURE_DECISIONS.md` is the ADR index. This document supplies the governed fields required for the Phase-0 ADR set without pretending unresolved implementation choices are frozen.

## Required ADR fields

Every ADR must identify: decision, status, affected requirements, considered alternatives, consequences, migration impact, and reversal/removal strategy.

## ADR compliance matrix

| ADR | Status | Affected requirements | Considered alternatives | Consequences | Migration impact | Reversal/removal strategy |
|---|---|---|---|---|---|---|
| ADR-001 TEP above TBOS | ACCEPTED | REQ-GOV-003, REQ-SCHED-001 | TBOS as whole platform; per-workflow controllers | separates governance/domain from runtime | existing orchestrators become migration inputs, not platform authority | constitutional ADR required to reverse |
| ADR-002 Modular monolith first | ACCEPTED | REQ-ARCH-001 | microservices/Kubernetes; single giant script | lower operational complexity with enforceable modules | local Mac deployment can adopt modules incrementally | split processes/services later behind same interfaces |
| ADR-003 Declarative missions | ACCEPTED | REQ-MISSION-001/002, REQ-TASK-001 | imperative Python mission controllers; prompt transcripts | reproducible/versioned missions | existing workflow logic must be mapped into definitions/handlers | migration tool may generate definitions; reversal requires mission-contract replacement |
| ADR-004 Service-owned semantics | ACCEPTED | REQ-GOV-003, REQ-SCHED-001 | scheduler-owned policy; worker-owned policy | explicit ownership, more interfaces | existing mixed controllers require decomposition | merge modules only if ownership remains singular |
| ADR-005 Replaceable workers | ACCEPTED | REQ-WORKER-001/002/003 | Codex-specific platform | prevents vendor/model lock and self-certification | Codex becomes adapter | replace adapter without changing task/state contracts |
| ADR-006 Explicit capability/authority | ACCEPTED | REQ-AUTH-001/002/003, REQ-CAP-001 | tool-access-as-authority; global mutation flag | safer but more explicit decisions | existing flags mapped to catalogue | evolve capability composition via governed spec |
| ADR-007 Durable event/state model | ACCEPTED | REQ-STATE-001..003, REQ-EVENT-001 | chat history; flat transient memory | restartability/idempotency complexity | existing audit artifacts imported only as evidence/migration input | storage engine replaceable behind state contracts |
| ADR-008 Evidence/knowledge separate | ACCEPTED | REQ-EVID-001/002, REQ-KNOW-001 | unified blob store with ambiguous semantics | stronger provenance/truth boundaries | classify existing artifacts by role | storage can converge physically while logical contracts remain separate |
| ADR-009 GitHub source authority | ACCEPTED | REQ-GIT-001, REQ-GH-001 | local canonical repo; TEP source DB | avoids competing source truth | reconcile local work against GitHub | requires explicit source-authority governance change |
| ADR-010 External large evidence by reference | ACCEPTED | REQ-EVID-001/002 | store all evidence in Git/repository DB | scalable evidence preservation but requires mount/provenance handling | preserve existing TradeBotData roots/manifests | migrate artifacts only with hash-preserving manifest |
| ADR-011 Serial merge/parallel preparation | ACCEPTED | REQ-MERGE-001/002 | fully serial fleet; concurrent merges | throughput without stale-main integration | existing fleet queues map to serialization keys | serialization strategy can change if equivalent JIT guarantees proven |
| ADR-012 Successor PR exceptional | ACCEPTED | REQ-MERGE-003 | successor-per-repair; never-successor | reduces PR proliferation while allowing necessary reconstruction | current successors require explicit lineage | policy may tighten; cannot silently broaden |
| ADR-013 Persistent supervisor | ACCEPTED | REQ-OBS-001, REQ-SCHED-002 | interactive-only runner; cron-only passes | autonomous continuity requires lifecycle ops | validated launchd behavior can inform migration | supervisor implementation replaceable if singleton/recovery preserved |
| ADR-014 launchd not architecture | ACCEPTED | REQ-ARCH-001 | launchd-specific runtime semantics | deployment portability | existing plist retained as deployment artifact | switch service manager without mission semantic change |
| ADR-015 Transactional local state store first | PROVISIONAL | REQ-STATE-001, REQ-EVENT-001 | JSON files; remote DB; embedded transactional DB | exact engine intentionally unresolved | M1 schema design may proceed abstractly; M2 persistence coding cannot | ADR-026 must ACCEPT engine before M2 persistence implementation |
| ADR-016 Append-preserved evidence | ACCEPTED | REQ-EVID-001/002 | mutable evidence files | stronger auditability, storage growth | existing sealed evidence remains untouched | retention/archive policy may move artifacts without mutating content |
| ADR-017 Typed blocker model | ACCEPTED | REQ-STATE-002/003, REQ-HUMAN-001 | generic BLOCKED | better autonomous routing, larger state taxonomy | map old blockers conservatively | taxonomy may extend; cannot collapse distinctions used by gates |
| ADR-018 CI waits worker-free | ACCEPTED | REQ-SCHED-003, REQ-CI-001 | periodic worker reasoning during CI | token efficiency and less speculative repair | existing watcher logic can migrate if validated | only change if evidence shows worker involvement is required for a specific terminal classification |
| ADR-019 Baseline failure convergence | ACCEPTED | REQ-CI-001 | repair each PR independently | reduces duplicate repairs but needs baseline tests | fleet failure history becomes knowledge/evidence | candidate-specific repair remains allowed when causation is proven |
| ADR-020 Research certification outside scheduler | ACCEPTED | REQ-RES-001..004 | scheduler self-certification | independent claims, additional validator components | preserve existing research evidence boundaries | certification service can evolve independently |
| ADR-021 Live observation separate execution | ACCEPTED | REQ-LIVE-001 | unified broker runtime | prevents authority widening | current read-only observers map cleanly | reversal requires explicit trading safety architecture review |
| ADR-022 Dynamic session subscription | ACCEPTED | REQ-LIVE-002 | hardcoded historical totals | correct dated launch truth | migrate counts to evidence, not constants | none; future contract may change derivation method |
| ADR-023 Runtime output isolation | ACCEPTED | REQ-LIVE-003 | source checkout runtime output | protects source cleanliness, requires configured storage | existing contaminated artifacts preserved/migrated by hash | test fixtures remain explicit exception |
| ADR-024 Market-calendar lifecycle | ACCEPTED | REQ-LIVE-004 | manual shutdown only; fixed clock | reduces post-market exposure | existing runtime adds calendar/drain capability | fallback manual safety stop retained |
| ADR-025 Complexity admission gate | ACCEPTED | REQ-ARCH-001 | unconstrained module/service growth | slower additions but lower platform sprawl | new TEP components require rationale | governance can revise admission criteria |

## Open implementation ADR gates

### ADR-026 — Local transactional database engine
Status: REQUIRED_BEFORE_M2_PERSISTENCE_IMPLEMENTATION.
Constraints: local transactional semantics; atomic state/event commit; crash recovery; migration/backup; no external service dependency required for v1; Python/tooling compatibility; evidence-safe corruption behavior.
Candidates must be evaluated against repository/runtime compatibility before selection.

### ADR-027 — Process topology
Status: REQUIRED_BEFORE_M2_DEPLOYMENT_FREEZE.
Allowed architectural range: one process or small supervised process set. Must preserve interface ownership, singleton supervisor, transactional state and crash boundaries.

### ADR-028 — Local API transport
Status: REQUIRED_BEFORE_M9_API_IMPLEMENTATION.
Must preserve capability/authority mediation and must not allow UI/application bypass of service boundaries.

### ADR-029 — Secret provider
Status: REQUIRED_BEFORE_ANY_TEP_COMPONENT_HANDLES_PRODUCTION_CREDENTIALS.
Must satisfy REQ-SECRET-001 and minimum-scope mediation.

## Milestone prohibition

M1 may define schemas/interfaces without choosing ADR-026/027/028. M2 persistence implementation MUST NOT begin until ADR-026 is ACCEPTED. Deployment freeze MUST NOT occur until ADR-027 is ACCEPTED. M9 mutation API implementation MUST NOT begin until ADR-028 is ACCEPTED. Production credential integration MUST NOT begin until ADR-029 is ACCEPTED.