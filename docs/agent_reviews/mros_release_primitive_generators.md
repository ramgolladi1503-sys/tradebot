# Agent Review: MROS Release Primitive Generators & Registry

## Purpose
Resolve the release-governance blocker identified post-PR #910: missing genuine repository-owned primitive generators for `option_mirror`, `evidence_integrity`, and `security_authority`, and eliminate the forgeability of the generic exit-code-zero placeholder primitive.

## Design Approach
1. **Repository-Owned Gate Registry (`core/release_gate_registry.py`)**:
   - Explicitly defines immutable contracts for all 18 gates required under `UNKNOWN_IMPACT`.
   - Binds gate semantic identity to generator identity, exact command prefix, required factual observation keys, and recomputation predicate.
   - Detects and rejects generic placeholder primitives (`{"command": "governed:<gate>", "exit_code": 0}`) and unmeasured constants.
2. **`option_mirror` Generator (`scripts/generate_option_mirror_primitive.py`)**:
   - Tests deterministic offline option-mirror readiness transitions and non-fatal degradation fallback to `MorningState.LIVE_DEGRADED` on stale/unavailable mirror.
   - Proves missing mirror fails closed. Captures raw output and SHA256 digest.
3. **`evidence_integrity` Generator (`scripts/generate_evidence_integrity_primitive.py`)**:
   - Implements AQ-11..AQ-20 compliance: checks manifest schema, verifies path safety (zero path traversal, zero symlink escape), asserts all referenced artifacts exist, verifies SHA256 hashes, disallows primitive reuse across gates, and computes a reproducible bundle digest.
4. **`security_authority` Generator (`scripts/generate_security_authority_primitive.py`)**:
   - Implements AQ-01..AQ-10 compliance: verifies singular candidate selection authority in `ReleaseStore.record_verified_selection`, singular execution authority, and observer execution isolation (zero `ExecutionRouter` calls).
   - Uses an active dynamic test spy to measure `broker_write_calls_measured = 0` and `order_actions_measured = 0` with `measurement_method = "spy_counter_verified"`. Rejects unmeasured constant forgery.
5. **Master Generator CLI (`scripts/generate_release_primitives.py`)**:
   - Runs all 18 genuine gate checks offline and produces a complete, authentic primitive evidence root.
6. **Hardened Certifier (`core/release_certification.py`)**:
   - Checks symlinks before resolution (`path.is_symlink()`).
   - Verifies primitive authenticity and rejects placeholder primitives, duplicate primitive paths, and duplicate primitive file digests.
7. **20-Attack Adversarial Mutation Campaign (`scripts/release_generator_mutation_campaign.py`)**:
   - Proves detection of all 20 mandatory attack classes.

## Non-Claims
- `broker_write_authority = false`
- `order_authority = false`
- `paper_authorized = false`
- `live_authorized = false`
- No orders placed, modified, or cancelled.
- No live observer launched.
- No strategy thresholds or live trading parameters modified.
