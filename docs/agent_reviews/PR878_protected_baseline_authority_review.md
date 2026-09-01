mode: READ_ONLY
candidate_id: PR878
decision: MERGE_ONLY_AFTER_REQUIRED_CHECKS_PASS
reason: Repair repository-controlled protected runtime baseline authority without weakening protected scope.
timestamp: 2026-09-01T16:23:00+05:30
is_order_action: false
broker_api_called: false
source: PR878_protected_baseline_authority_review

# PR878 Protected Baseline Authority Review

## Agent Work Contract

- source_agent: ChatGPT/Codex governed repository workflow
- action: GOVERNANCE_REPAIR
- title: Repair protected runtime baseline authority
- scope: repair stale repository-controlled CI authority used by PR818 live-flow freeze and PR782 protected-runtime scope validation
- requested_paths: `.github/workflows/repo-forensics-pr-gate.yml`, `.github/workflows/pr782-remaining-evidence-contracts.yml`, and this review evidence
- allowed_paths: governance/workflow files and review evidence only
- forbidden_paths: broker, order, risk, CAS, strategy, auth, database, persistence implementation, and market-data runtime logic
- expected_tests: protected CI, focused contracts, repo-forensics, code-excellence, safety, and exact-SHA identity checks
- acceptance_proof: current protected main authority passes; unauthorized protected-runtime mutation remains rejected; no gate is removed or weakened

## Scope Guard

This change updates only repository-controlled CI authority. It does not alter runtime execution, broker connectivity, order authority, CAS semantics, strategy logic, risk controls, authentication behavior, persistence implementation, or market data handling.

## Grill Me Review

The repair is invalid if it merely moves a hash forward because main changed. The advancement must be tied to governed protected-main history, keep the protected path set intact, and preserve fail-closed behavior for unauthorized runtime edits. The PR782 verifier must compare the actual PR base to the actual head rather than a stale historical branch while retaining an explicit allowed path surface.

## Hermes Review

The smallest legitimate repair is to advance the integrated PR818 protected-main baseline to the already-governed protected main that includes the merged PR876 shutdown-boundary repair, while leaving the frozen production path set and enforcement unchanged, and to make PR782 scope verification base/head accurate.

## GSD Review

No production code is changed. The candidate contains only CI/governance workflow edits and this evidence file. Historical frozen live SHA semantics are not replaced by a permissive wildcard or disabled check.

## QA / Safety Review

Required validation is entirely offline/CI. No broker session, live feed, credentials, orders, SQLite runtime state, or preserved Sep-1 forensic evidence is touched. Negative-control behavior must continue to reject unauthorized protected-runtime changes.

## Acceptance Proof

Acceptance requires all required checks on the exact PR878 head to pass, including code-excellence base authority, focused contracts, repo-forensics, exact-SHA identity, safety checks, and the trusted PR818 freeze target. A check may not be removed, skipped through workflow disabling, or bypassed administratively to obtain green status.

## Runtime Proof Required After Merge

None for this governance-only PR. Runtime proof remains required separately for PR877's shutdown repair after PR877 is merged and a fresh read-only live session is run under the governed observation contract.

## What This PR Does Not Prove

It does not prove PR877 is correct, does not prove Sep-1 persistence durability, does not prove live drain revalidation, does not prove CAS prospective support, does not prove structural trading edge, and does not authorize live or paper order execution.

## Human Approval

Merge is permitted only after protected CI is green on the exact head and the repository's normal branch-protection policy is satisfied. No force/admin merge is authorized.