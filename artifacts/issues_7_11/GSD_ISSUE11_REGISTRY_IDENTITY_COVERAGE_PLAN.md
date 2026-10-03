# GSD Plan — Issue 11 candidate dependency domain coverage

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Fail closed when required candidate domains lack identity declarations
**scope:** Execute the Hermes contract at `docs/agent_reviews/issues_7_11_hermes_issue11_registry_identity_coverage.md`
**requested_paths:** `core/candidate_feed_dependencies.py`, `tests/test_candidate_feed_dependencies.py`, `scripts/verify_issues_7_11_issue11_registry_identity_mutation.py`, and the listed Issues 7–11 evidence records.
**allowed_paths:** Those paths only.
**forbidden_paths:** Feed/runtime wiring, strategy semantics, risk, broker/order code, credentials, live paths, token-universe policy, and unrelated cleanup.
**expected_tests:** `tests/test_candidate_feed_dependencies.py`, `tests/test_edge45_symbol_execution_safety.py`, `tests/paper_shadow/test_issue11_scenarios_cd.py`, and `tests/test_feed_truth_snapshot_ranking_contract.py`; isolated mutation runner.
**acceptance_proof:** Missing-domain, empty, whitespace-only, and padded identities are rejected by validator, resolver, and/or eligibility; all current registry entries validate; current candidate authority statuses stay unchanged; temporary-copy mutants removing validator and eligibility checks are killed only by their named assertion sentinels; source/test hashes remain unchanged by the mutants.

## Execution steps

1. Preserve the reproduced pre-fix case: `INDEX_OPTIONS` required, no identity rows, empty health map yielded `execution_eligible=True`.
2. Add exact domain coverage and canonical identity-value invariants shared by registry validation and the eligibility property. Treat `(domain, None)` as declared but unresolved; keep it ineligible.
3. Add resolver-level regression using temporary test registry entries and source-digest stubs. Assert invalid registry status and reason, not only dataclass shape.
4. Add a mutation runner that removes the validator and eligibility checks in separate temporary source copies; require each named assertion sentinel to fail, so unrelated test failures cannot count as killed mutants.
5. Run the focused dependency, safety, isolation, and ranking regressions; run the mutation runner; verify compile and diff checks.
6. Record bounded evidence in the campaign graph and ledgers. Leave overall acceptance false and all external authority/live parity gaps open.

## Invariants

- No missing required domain is considered healthy by vacuous iteration.
- Extra undeclared identity domains also invalidate the registry.
- Empty, whitespace-only, and padded identity strings are invalid; dynamic `None` remains unresolved.
- Existing partial/dynamic identities remain blocked.
- No change to candidate ranking, strategy calculations, feed producer, freshness thresholds, or execution authority.
- Safety fields remain read-only; no order or broker calls.

## Configuration and rollout

No new configuration key or data migration. Rollout requires the focused regression and mutation proof, then the repository's applicable CI and review gates on a later PR. This local worktree change does not create, push, or merge a PR.

## Execution result

Implemented in `core/candidate_feed_dependencies.py`. Registry validation and
the `execution_eligible` property now require exact required-domain coverage by
identity declarations. Resolver validation explicitly inspects the current
`REGISTRY_ENTRIES` tuple.

- Focused command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_candidate_feed_dependencies.py tests/test_edge45_symbol_execution_safety.py tests/paper_shadow/test_issue11_scenarios_cd.py tests/test_feed_truth_snapshot_ranking_contract.py`
- Result after adding blank/whitespace/padded identity attacks: **61 passed, 1 warning in 12.70s**.
- Mutation command: `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue11_registry_identity_mutation.py`
- Mutation result: **2/2 killed** (`remove_registry_validator_coverage_check`, `remove_execution_eligibility_coverage_check`). Each mutant must fail its named assertion sentinel; unrelated failures are invalid. Source SHA-256 `07de4dafa4e79d40b269d479ec806154ae9d8cef2072bac579bb490d64e23014`, test SHA-256 `4bdef3f55db6ff7f949670d90bca894bc21b57ada6a13fb4812a18e28b092799`; checkout files unchanged by the temporary mutations.
- No new config key or migration. No current candidate was promoted; no broker/order/live behavior changed.
- Remaining Issue 11 gaps: runtime does not produce exact health evidence for dynamic futures/options identities; live/captured parity and the initiating captured auth/transport cause remain UNKNOWN.
- Campaign verdict remains `implementation_valid=false`, `issues_7_11_offline_repair_verified=false`, and `live_verified=false`.
