# GSD execution — PR948 observation identity repair

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Repair MEG cash-observation identity without regressing current feed protections
**scope:** Implement the Hermes contract on the current main base in both depth subscription builders.
**requested_paths:** `core/depth_subscription_engine.py`, `core/kite_depth_ws.py`, `tests/test_depth_subscription_tokens.py`, `tests/test_subscription_universe_123_contract.py`
**allowed_paths:** requested source/tests, this plan, the Hermes contract, the PR review, and directly relevant evidence.
**forbidden_paths:** raising the existing 123-token MEG ceiling, freshness/recovery changes, risk/kill-switch changes, broker/order calls, credentials, live-mode changes, production-data mutation, and unrelated paths.
**expected_tests:** MEG input filtering and identity classification in both builders; blocked merge identity remains absent; a general budget above 123 is capped in MEG mode; exact 123 union and production option resolver ownership remain unchanged.
**acceptance_proof:** focused deterministic regression suite, existing exact-topology test, changed-path safety review, and exact-head hosted CI. No live execution.

## Steps

1. Update the PR branch to current `main`; preserve current recovery, option-health evidence, and subscription-budget behavior from main when resolving stale conflicts.
2. Filter requested option symbols to the configured index product set and enforce the existing 123-token ceiling only when MEG mode is enabled.
3. After successful registry merge, publish active observation identities consistently across token maps and underlying maps; make no identity updates on blocked merge.
4. Test both builders with 50 synthetic cash constituents, explicit option resolver call capture, a requested budget of 150, a blocked merge, incomplete identity coverage, and cash-only input. Preserve the exact 123-token topology.
5. Run focused tests, `git diff --check`, and all applicable hosted checks. Exclude PR782/PR818 checks per user direction without editing or weakening them.

## Risk and rollback

An unverified token classification could contaminate option/depth accounting. Only validated registry entries in the final union are mapped. Rollback reverts the scoped source/test changes; no config migration is required.

## Execution result

Implemented in both the installed depth engine and the canonical Kite builder. MEG input symbols are filtered to the three supported index option products; a request containing only cash constituent symbols fails closed. The direct engine also caps a requested/configured budget of 150 at the existing 123-token MEG limit. After a successful union, registry identity is validated for complete coverage, final-union membership, and conflicts before generic and underlying identity maps are updated. A failed union or inconsistent registry identity publishes no observation-only identity and does not enable the observation readiness state.

Focused validation on the local candidate: `pytest -q tests/test_depth_subscription_tokens.py tests/test_depth_subscription_refresh_contract.py tests/test_subscription_universe_123_contract.py tests/test_kite_depth_ws_stability.py` — **90 passed**. `git diff --check` passes. Hosted exact-head CI is pending. PR782 and PR818 checks remain excluded per user direction and are not considered passing.

No live process or broker was contacted. Live observation readiness remains unverified until separate authorized read-only runtime evidence is captured.

## Configuration, migration, and rollout

- New config keys: none.
- Migration: none.
- Rollout: merge only after exact-head in-scope CI passes; then separately perform authorized read-only observation and compare active token identities with the canonical registry. Roll back by reverting the scoped source and test changes if that verification finds a mismatch.
