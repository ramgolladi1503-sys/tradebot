# GSD Plan — Issue 11 candidate dependency isolation

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Prove exact candidate feed dependencies before local health isolation
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue11_candidate_isolation_contract.md`.

## Current execution disposition

**Bounded cross-symbol implementation is complete offline; full Issue 11 closure remains unproven.** Repository trace found the existing `market_event_graph_subscription_evidence_for_tokens()` helper, which emits per-token receipt/source timestamps and session/epoch/reconnect identity for an explicit token map. The option resolver also reads instrument rows, but retains only strike/type in runtime metadata. The feed-health producer does not call the token lifecycle helper, discards full contract identity, and has no production injection of `feed_health_by_identity` or proven join from candidate dependencies to token evidence. Published feed-health inputs are aggregate or symbol-scoped; candidate registry declarations for dynamic futures/options remain unresolved. The bounded patch uses only explicit per-symbol rows already present in the serialized `FeedHealthTruthDecision`, after validating same-cycle underlying token/session/epoch/reconnect/subscription/receipt-age/SLA evidence and retaining all global blockers. The focused producer/classifier/gate/serialized-ranking regression passed (87 passed, 1 warning); the forced-all-symbols-healthy mutant was killed with source/test hashes unchanged. Same-symbol dynamic contract isolation still requires a separate proven token/contract join.

## Hermes contract implementation scope

- `core/kite_depth_ws.py`: emit complete per-underlying token-health rows from existing subscription/token/feed-generation state; do not change subscriptions or health thresholds.
- `core/feed_health_truth.py`: preserve the exact per-symbol underlying evidence on the existing symbol truth row.
- `core/ranking_orchestrator.py`: pass the report symbol to the read-only feed hold gate.
- `core/feed_hold_gate.py`: scope only certified symbol-aggregate decisions to the requested symbol after validating exact target underlying token/session/epoch/reconnect/subscription/receipt-age/SLA evidence. Unknown or global conditions retain whole-report hold.
- `tests/test_kite_read_only_observation_runtime.py`, `tests/test_edge43_feed_health_truth.py`, `tests/test_pr_feed_03_feed_hold_gate.py`, and `tests/test_ranking_orchestrator.py`: cover producer, classifier, direct gate, and actual serialized cycle-context ranking.
- Add/extend a focused mutation harness for removal of target-symbol health validation or global-block preservation.
- Update `artifacts/issues_7_11/defect_graph_issue11_replay_addendum.json`, `defect_graph.md`, `attack_ledger.jsonl`, `repair_ledger.jsonl`, and `FINAL_VERDICT.json` with exact evidence and keep full acceptance false.

## Required MAP / RED steps before any same-symbol identity patch

1. Trace the existing instrument rows through option-token resolution and identify the fields currently discarded; preserve the raw source and prove token uniqueness before using it as contract identity.
2. Trace candidate fields through pool, normalization, ranking, evaluation, and execution safety. Prove whether an exact required token/contract identity already exists in the candidate input; do not derive it from symbol, score, strike approximation, or quote age.
3. Trace the complete active subscription universe into `market_event_graph_subscription_evidence_for_tokens()` and prove the evidence is same-cycle, non-truncated, and bound to current session/epoch/reconnect generation.
4. Only if both the exact candidate dependency and feed identity evidence join are proven, define a narrowly scoped producer-to-consumer patch and add positive, negative, global-blocker, recovery, and mutation tests. Otherwise stop runtime implementation and retain `UNKNOWN`, with a concrete missing-field/source report.

## Conditional implementation files for any same-symbol identity patch

The bounded cross-symbol patch above is completed. Do not make additional same-symbol identity changes in these files until the MAP proof above exists and is attached to the implementation review:

- `core/kite_depth_ws.py`: only if it already owns canonical token/contract metadata and can emit complete same-cycle identity rows without subscription or behavior changes.
- `core/runtime_feed_truth_snapshot.py`: only if adding a versioned, read-only identity-health field is compatible with current consumers and does not omit rows.
- `core/runtime_cycle_context.py` or the existing candidate bridge: only to pass an immutable evidence snapshot to candidate evaluation; no global mutable state.
- `core/candidate_feed_dependencies.py` / `core/symbol_execution_safety.py` / `core/ranking_orchestrator.py`: only to consume exact, declared dependencies and preserve global hard blockers.
- Add focused tests adjacent to the selected producer and consumers, plus mutation harness and evidence graph updates. For this bounded cross-symbol patch, see the recorded producer/classifier/gate/serialized-ranking suite and `scripts/verify_issues_7_11_issue11_symbol_scope_mutation.py`.

## Forbidden files/behavior absent a separate exact scope

`main.py`, `run_live.sh`, config/credentials/environment, broker/order/risk/strategy code, subscription topology, token-universe configuration, and any behavior granting paper/live execution. No external calls, live process changes, order actions, strategy threshold changes, synthetic identity fallback, or aggregate-to-local health inference.

## Expected tests if prerequisites are proven

- Exact configured-token mapping and complete coverage (no sample truncation).
- Same-cycle session/epoch/reconnect binding and finite receipt-age SLA.
- Stale secondary option blocks only exact dependents; independent declared healthy spot path continues in read-only evaluation.
- Stale required underlying and shared transport/auth/recovery/global failures remain blocking.
- Wrong/missing/ambiguous token, contract, domain, source time, receipt time, session, epoch, reconnect generation, and dependency declaration fail closed.
- Dynamic configured-universe scale without hard-coded historical counts or universe changes.
- Existing feed aggregate, recovery, ranking, execution safety, token universe, and Issues 1–6 regression suites.
- Mutation/sabotage tests and an independent unseen identity mismatch attack.

## Acceptance proof

- Record exact baseline/final SHA, changed paths, test commands/results, mutation results, configured universe count/hash, authority flags, and independent review.
- If source identity authority remains absent, record the precise missing fields/source and leave Issue 11/campaign acceptance false. A fail-closed blocker is not a completed isolation repair.
- Never claim live parity based on offline fixtures.

## Rollback and rollout

No runtime rollout under this plan. Any future offline code change must be reversible by reverting only its scoped producer/consumer change while retaining global gates. A live rollout requires separate explicit human review of measured snapshot cadence, full identity coverage, and same-generation binding; this plan does not grant it.
