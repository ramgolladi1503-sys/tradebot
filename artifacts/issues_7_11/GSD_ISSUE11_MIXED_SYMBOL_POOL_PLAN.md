# GSD Plan — Issue 11 mixed-symbol candidate-pool guard

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Keep symbol-scoped feed proof bound to a homogeneous score set
**scope:** `docs/agent_reviews/issues_7_11_hermes_issue11_mixed_symbol_pool_contract.md`

## Baseline / reproduction

Repository trace shows `candidate_pool.symbol` is the context symbol, while scoring consumes all generator outputs. Candidate symbols are not validated against the pool symbol. Add a deterministic mixed-symbol integration case with NIFTY context, NIFTY and BANKNIFTY candidates, explicit symbol-aggregate feed truth with BANKNIFTY stale, and verify that the report remains aggregate-held before applying the fix.

## Execution

- `core/ranking_orchestrator.py`: pass a symbol to the bounded feed-hold isolator only for a nonempty score report whose every record has a canonical uppercase symbol exactly equal to the canonical uppercase pool symbol; do not normalize trust-boundary identities.
- `tests/test_ranking_orchestrator.py`: reproduce mixed-symbol over-scope; retain canonical homogeneous symbol-scope positive behavior and prove empty, malformed, blank, noncanonical, and mismatched scores cannot scope.
- `artifacts/issues_7_11/defect_graph_issue11_replay_addendum.json`, `defect_graph.md`, `attack_ledger.jsonl`, `repair_ledger.jsonl`, and `FINAL_VERDICT.json`: record bounded proof and preserve open Issue 11/campaign verdict.
- Run targeted tests first, then the adjacent feed recovery, candidate dependency, execution-safety, runtime snapshot, and token-coverage regression; run the Issue 11 mutation harness after the guard is final.

## Forbidden changes

No candidate filtering/rewriting, strategy or ranking policy changes, feed threshold/latch changes, subscriptions, token-universe edits, config, broker/order/risk/execution changes, live calls, or authority changes.

## Acceptance

The mixed-symbol regression must fail before the guard and pass after; homogeneous NIFTY isolation remains; aggregate blockers remain fail-closed; tests and mutation evidence match the exact final source. This is a bounded offline hardening only. Exact dynamic contract dependency identity, captured/live parity, and full Issue 11/campaign acceptance remain open.

## Safety and rollout

Read-only ranking only. No new config keys or migrations. No runtime rollout authorization. Roll back only the homogeneous-symbol condition and associated tests/artifacts while retaining aggregate feed holds.

## Execution record

The mixed-symbol regression was run before the guard and failed with two candidates ranked under NIFTY scope. After the guard, `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_ranking_orchestrator.py` passed (12 passed, 1 warning). The isolated `trust_pool_symbol_without_score_identity_check` mutant was killed; source/test hashes remained unchanged. Broader adjacent regression is in progress.
