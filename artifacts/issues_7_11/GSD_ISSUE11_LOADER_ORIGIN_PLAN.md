# GSD Plan — Issue 11 canonical loader-origin repair

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Preserve canonical feed-truth artifact origin through ranking
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue11_loader_origin.md`.

## Files

- `core/orchestrator.py`: tag loader origin by the canonical filename; overwrite untrusted same-named payload metadata; preserve existing freeze behavior.
- `core/feed_health_truth.py`: recognize trusted loader-origin metadata as requiring the versioned snapshot contract.
- `tests/test_feed_truth_snapshot_ranking_contract.py`: add marker-stripping plus injected-legacy regression through the actual loader and ranking gate.
- `scripts/verify_issues_7_11_issue11_loader_origin_mutations.py`: isolate and mutate the loader-origin assignment; require the regression test to fail.
- `artifacts/issues_7_11/defect_graph.json`, `attack_ledger.jsonl`, `repair_ledger.jsonl`, and result/verdict records: add the new bypass, repair, mutation result, and bounded status.

## Execution

1. Reproduce the independent attack against the current checkout and record the pre-fix nonzero rank.
2. Add the regression first and confirm it fails before the repair.
3. Add only the loader-origin marker and classifier recognition required by the Hermes contract.
4. Run the regression plus stale/healthy file-loader tests, legacy compatibility, feed-health, ranking, and runtime-integrity tests.
5. Run the isolated loader-origin mutation harness; reject import, collection, timeout, or unrelated failures as invalid mutation results.
6. Re-run independent adversarial verification and record exact source/test hashes and focused command results.

## Invariants

- Missing, unsupported, stale, malformed, or contradictory canonical snapshot truth fails closed.
- Loader-origin metadata never claims payload authenticity and never repairs payload fields.
- Explicit legacy compatibility remains limited to existing recognized evidence.
- Candidate-level isolation remains UNKNOWN; do not infer strategy dependencies from symbol names.
- No broker/order/risk/live authority, strategy semantics, feed producer, or configured universe changes.

## Acceptance

The marker-stripping attack cannot produce ranks through the canonical loader; healthy and stale canonical v1 behavior and legacy caller compatibility remain covered; the mutation harness kills removal of the origin assignment; independent verifier finds no bypass within this offline boundary.
