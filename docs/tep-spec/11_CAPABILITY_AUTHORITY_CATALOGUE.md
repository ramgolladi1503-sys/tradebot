# TEP v1 — Capability and Authority Catalogue

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

Repairs Phase-0 finding F-004.

| Capability | Owner | Default | Required authority | JIT checks | Evidence |
|---|---|---|---|---|---|
| READ_REPOSITORY | Git Service | allowed by mission | read scope | repository/ref identity | read provenance |
| PUSH_BRANCH | Git Service | DENY | GITHUB_PUSH_AUTHORIZED | repo, branch, expected head, scope, non-protected target, task fingerprint | before/after SHA + push result |
| UPDATE_PR_METADATA | GitHub Service | DENY | GITHUB_PR_METADATA_AUTHORIZED | PR identity/head/base/state + task fingerprint | before/after PR snapshot |
| MERGE_PR | Merge Service | DENY | GITHUB_PR_MERGE_AUTHORIZED | refreshed main, exact head/base, required CI/review, mergeability, dependency readiness | premerge gate + merge SHA |
| CLOSE_PR | GitHub Service | DENY | GITHUB_PR_METADATA_AUTHORIZED | exact PR, preservation/supersession disposition | before/after PR + disposition evidence |
| CREATE_PR | GitHub Service | DENY | GITHUB_PR_METADATA_AUTHORIZED | successor-necessity gate, exact head/base, no duplicate integration surface | PR snapshot + justification |
| CREATE_BRANCH | Git Service | DENY for mutating mission | GITHUB_PUSH_AUTHORIZED | exact source SHA/ref, naming/scope policy | created ref evidence |
| DELETE_WORKTREE | Cleanup Service | DENY | DESTRUCTIVE_LOCAL_CLEANUP_AUTHORIZED | REQ-CLEAN-001 preservation predicates + target identity | preservation manifest + deletion result |
| DELETE_LOCAL_PATH | Cleanup Service | DENY | DESTRUCTIVE_LOCAL_CLEANUP_AUTHORIZED | canonical/protected-path rejection + preservation predicates | manifest + result |
| START_READ_ONLY_OBSERVER | Live Observation Service | DENY unless mission grants read-only launch | READ_ONLY_LIVE_OBSERVATION_AUTHORIZED | exact launch plan, market/session, source SHA, storage, singleton, broker-write false | launch record |
| STOP_READ_ONLY_OBSERVER | Live Observation Service | allowed for safety/governed owner | observer lifecycle authority | exact observer identity, drain target | shutdown/drain evidence |
| BROKER_WRITE | Trading Execution Service (future) | DENY | BROKER_WRITE_AUTHORITY | separately frozen trading contract | broker mutation evidence |
| PLACE_ORDER | Trading Execution Service (future) | DENY | ORDER_AUTHORITY plus applicable broker/live authority | instrument/order/risk/freshness contract | order audit evidence |
| PAPER_EXECUTE | Trading Execution Service (future) | DENY | PAPER_AUTHORIZED | paper environment/strategy authority | paper execution ledger |
| LIVE_EXECUTE | Trading Execution Service (future) | DENY | LIVE_AUTHORIZED plus all lower execution/risk authorities | fresh live authority and risk gates | live execution ledger |
| SEAL_EVIDENCE | Evidence Service | DENY except evidence workflow | EVIDENCE_SEAL_AUTHORIZED or frozen internal service policy | artifact hash, provenance, validator, claim scope | sealed EvidenceRecord |
| ACCESS_PROTECTED_HOLDOUT | Research Governance | DENY | HOLDOUT_ACCESS_AUTHORIZED | frozen hypothesis/spec and selection boundary | access ledger |
| CERTIFY_STRUCTURAL_EDGE | Independent Research Validator | DENY | STRUCTURAL_EDGE_CERTIFICATION_AUTHORIZED | all applicable certification gates | certification bundle |

## Authority invariants

1. Authorities are capability-specific and do not imply one another.
2. Authority is evaluated against mission/task/target scope, not merely a global boolean.
3. An authorization may expire or be invalidated by target/dependency drift.
4. Worker possession of credentials/tools does not constitute authority.
5. Safety shutdown may be permitted even when startup/mutation authority is absent, provided it cannot widen capability.
6. Read-only live observation does not imply broker write, order, paper or live execution authority.
7. Structural-edge certification authority is separate from research execution authority.

## Human-only authority classes

The following require explicit human policy approval in v1 unless a later frozen specification changes them:

- granting BROKER_WRITE, ORDER, PAPER or LIVE execution authority;
- granting destructive cleanup authority over unresolved/previously protected unique authority;
- accepting an architecture/specification freeze or incompatible constitutional change;
- accepting explicit risk where a required independent validator cannot be satisfied;
- credential enrollment/rotation where external provider requires human action.

Routine CI failures, merge conflicts, candidate test failures, environment retries, normal CI waits and already-authorized bounded branch repair are not inherently human-only.

## Escalation payload

TRUE_HUMAN_APPROVAL_REQUIRED MUST contain: decision ID; exact requested decision; why automation cannot decide under frozen policy; alternatives; evidence refs; risk/consequence per alternative; authority being requested; expiry/scope; safe default if no response.