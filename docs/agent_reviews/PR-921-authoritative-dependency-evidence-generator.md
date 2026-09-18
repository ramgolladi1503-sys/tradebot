# PR #921 — Authoritative Release Dependency Evidence Generator & Primitive Repairs

## Evidence Contract Fields

- mode: OFFLINE_RELEASE_INFRASTRUCTURE
- candidate_id: PR-921-authoritative-dependency-generator
- decision: ADD_AUTHORITATIVE_RELEASE_DEPENDENCY_GENERATOR
- reason: SHA cae620... had DependencyEvidence contracts but lacked committed repository-owned generator infrastructure for release certification.
- timestamp: 2026-09-18T17:15:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/PR-921-authoritative-dependency-evidence-generator.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: #921
- Branch: fix/mros-authoritative-dependency-evidence-generator-v1
- Scope: Add immutable repository-owned release dependency evidence generator and fix release primitive generator defects.
- Allowed files:
  - core/release_dependency_evidence.py
  - scripts/generate_release_dependency_evidence.py
  - scripts/generate_release_primitives.py
  - scripts/generate_evidence_integrity_primitive.py
  - tests/test_release_dependency_evidence.py
  - tests/test_release_dependency_adversarial.py
  - docs/release_manager/AUTHORITATIVE_DEPENDENCY_GENERATOR_GAP_AUDIT.json
  - docs/agent_reviews/PR-921-authoritative-dependency-evidence-generator.md
- Forbidden files:
  - main.py
  - core/orchestrator.py
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - strategies/
  - config/
- Forbidden behaviors:
  - No broker placement changes.
  - No live order behavior changes.
  - No feed/WebSocket behavior changes.
  - No strategy, ranking, scoring, or threshold changes.
  - No dashboard changes.
- Acceptance tests:
  - AST module dependency scanning resolves relative and absolute imports deterministically.
  - Syntax errors, dynamic imports (`__import__`, `importlib.import_module`), and parse exceptions fail closed (`complete=False`).
  - Missing governed critical/bounded roots fail closed (`complete=False`).
  - Independent verifier detects tamper in candidate SHA, base SHA, edges, roots, and completeness.
  - Degraded-mode and evidence-integrity primitive generators produce valid genuine primitives.

## Scope Guard

Verdict: PASS

Checked:
- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No feed/WebSocket behavior change.
- Zero mutations to execution/risk/broker paths.

Blocking issues: none.

## Grill Me Review

Verdict: PASS

Critique:
- Risk: AST parser could miss dynamically constructed imports.
  - Mitigation: Any call to `__import__`, `import_module`, `eval`, or `exec` explicitly registers as an unresolved reason, forcing `complete=False` and triggering full UNKNOWN_IMPACT gate sets.
- Risk: Circular self-hashing in bundle evaluation.
  - Mitigation: `evidence_integrity` explicitly inspects the other 17 gate primitives, verifying their existence, safety, and non-reuse before hashing the bundle.

Blocking issues: none.

## Hermes Review

Verdict: PASS

Architecture alignment:
- Binds to existing canonical `core.release_change_impact.DependencyEvidence` dataclass.
- Preserves single authoritative certification path without creating secondary authorities.
- Enforces strict fail-closed contract where uncertainty preserves `complete=False`.

Blocking issues: none.

## GSD Review

Verdict: PASS

Implementation status:
- `core/release_dependency_evidence.py` implemented.
- `scripts/generate_release_dependency_evidence.py` CLI implemented.
- Primitive generator repairs verified.
- 16 new unit + adversarial tests passing.

Blocking issues: none.

## QA / Safety Review

Verdict: PASS

Safety invariants verified:
- `broker_write_authority` = false
- `order_authority` = false
- `paper_authorized` = false
- `live_authorized` = false
- `ORDERS_PLACED` = 0
- `ORDERS_MODIFIED` = 0
- `ORDERS_CANCELLED` = 0

Blocking issues: none.

## Acceptance Proof

- Dogfood executed on PR #921:
  - `DOGFOOD_BASE_SHA`: cae620bea88c1caba79fe68cb3f296ab597f4056
  - `DOGFOOD_CANDIDATE_SHA`: fdd4d8d4da1c89945ae3ebac4a87cac4cd9cefd3
  - `DOGFOOD_DEPENDENCY_COMPLETE`: False (conservatively preserved due to 143 unresolvable imports in research/legacy scripts)
  - `DOGFOOD_REQUIRED_GATES`: 18 gates required under fail-closed UNKNOWN_IMPACT
  - `DOGFOOD_SEMANTIC_SHA256`: 8a208ecf8b21d7bb410322e5aa7ec75de2ee2a9b2773c57c951350c9c8546735
- 16 new unit and adversarial tests pass (`tests/test_release_dependency_evidence.py`, `tests/test_release_dependency_adversarial.py`).
- 89 existing release and orchestrator tests pass.

## Runtime Proof Required After Merge

- Execute clean post-merge smoke test verifying `core.release_dependency_evidence` is callable on the new merged main commit without uncommitted modifications.

## What This PR Does Not Prove

- Does not prove natural candidate traversal or live order execution.
- Does not clean up Trade Truth hash contract.
- Does not certify live trading or prospective strategies.

## Human Approval

Approved for release-infrastructure implementation and merge into main.
