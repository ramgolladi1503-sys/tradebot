# MROS Release Primitive Generators & Gate Registry Review Evidence

mode: review
candidate_id: fix/mros-release-primitive-generators-v1
decision: VALIDATION_IN_PROGRESS
reason: implement genuine repository-owned primitive generators for option_mirror, evidence_integrity, and security_authority
timestamp: 2026-09-16T18:50:00+00:00
is_order_action: false
broker_api_called: false
source: repository-owned generator scripts, gate registry, and 20-attack mutation campaign

## Agent Work Contract

Scope is strictly limited to resolving the release-governance blocker identified post-PR #910: implementing genuine repository-owned primitive generators for option_mirror, evidence_integrity, and security_authority, eliminating generic placeholder primitives, adding path.is_symlink() pre-resolution checks, and validating all 20 adversarial mutation attacks. Strategy thresholds, alpha logic, ranking, risk gates, broker APIs, and live order execution are strictly forbidden.

## Scope Guard

Production release state remains governed. Changes are strictly confined to release certification, gate generator registry, standalone primitive generators, and focused test suites.

## Grill Me Review

The review verifies that:
1. Gate semantic names in core/release_change_impact.py are bound to immutable generator identities, execution commands, and factual observation schemas in core/release_gate_registry.py.
2. Generic exit-code-zero placeholder primitives ({"command": "governed:<gate>", "exit_code": 0}) are explicitly detected and rejected fail-closed.
3. option_mirror generator tests deterministic offline option-mirror readiness transitions and non-fatal degradation to MorningState.LIVE_DEGRADED on stale/unavailable mirror.
4. evidence_integrity generator verifies AQ-11..AQ-20 integrity: manifest schema, path safety (zero path traversal, zero symlink escape), artifact existence, sha256 matching, and zero primitive reuse across gates.
5. security_authority generator verifies singular selection authority, singular execution authority, observer execution isolation, and measures zero broker writes via dynamic test spies (measurement_method="spy_counter_verified").
6. Symlink check in core/release_certification.py runs before path.resolve() to prevent symlink bypass.

## Hermes Review

Authority boundaries remain singular and immutable:
- candidate_selection_authority_count = 1
- ExecutionRouter_CALL_COUNT = 0
- broker_write_calls_total = 0
- orders_placed = 0, orders_modified = 0, orders_cancelled = 0
- read_only = true, broker_write_authority = false, order_authority = false

## GSD Review

Changes are strictly confined to the release governance, generator registry, and test files:
- core/release_certification.py
- core/release_gate_registry.py
- scripts/generate_evidence_integrity_primitive.py
- scripts/generate_option_mirror_primitive.py
- scripts/generate_release_primitives.py
- scripts/generate_security_authority_primitive.py
- scripts/release_generator_mutation_campaign.py
- tests/test_release_primitive_generators.py
- docs/agent_reviews/mros_release_primitive_generators.md

## QA / Safety Review

Focused test suites verify 34/34 passing tests and 20/20 adversarial mutations detected:
- tests/test_release_primitive_generators.py (9 passed)
- tests/test_release_certification.py (6 passed)
- tests/test_release_rebootstrap.py (12 passed)
- tests/test_release_rebootstrap_attacks.py (5 passed)
- tests/test_release_rebootstrap_campaign.py (2 passed)
- scripts/release_generator_mutation_campaign.py (20/20 attacks detected)

## Acceptance Proof

Acceptance requires passing unit tests, whole-tree syntax compilation, 20-attack mutation campaign detection, and zero execution leaks.

## Runtime Proof Required After Merge

Post-merge verification requires generating genuine primitives for all 18 gates for the exact merge commit SHA using scripts/generate_release_primitives.py, certifying via release manager, and verifying independent attestation before promotion.

## What This PR Does Not Prove

This PR does not claim execution viability, does not claim structural economic edge, does not authorize live or paper execution, and does not start any live observer.

## Human Approval

Human review and merge approval on GitHub is required before production promotion.
