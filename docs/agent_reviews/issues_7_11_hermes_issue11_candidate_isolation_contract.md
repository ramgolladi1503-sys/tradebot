# Hermes Contract — Issue 11 candidate dependency isolation

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Preserve unrelated evaluation only when exact candidate feed dependencies are proven
**inspected SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Scope

Continue Issue 11 beyond the already repaired aggregate persisted-feed ranking boundary. Determine whether an exact candidate dependency can be isolated from stale unrelated instruments without weakening shared transport, recovery, runtime-safety, or execution gates. This is offline/read-only scope. It does not authorize orders, broker calls, paper/live access, subscriptions, strategy changes, or changes to the configured token universe.

## Repository evidence

1. `core/kite_depth_ws.py` tracks last normalized receipt and source timestamps by numeric token. `market_event_graph_subscription_evidence_for_tokens()` also emits exact token keyed lifecycle evidence with feed session, epoch, reconnect generation, receipt/source times, and subscription state when called with an explicit token map. `_load_option_token_meta` reads current instrument rows but retains only strike and instrument type; `_option_runtime_state` exports symbol aggregates and a bounded sample. `_TOKEN_TO_SYMBOL` maps derivative tokens to underlyings; it is not an exact option-contract identity source. Thus lifecycle identity evidence exists in an existing helper, while full token-to-contract identity is discarded before health publication.
2. `core/runtime_feed_truth_snapshot.py` persists aggregate freshness. It does not persist a complete token/contract identity map or same-cycle identity-health map, and the snapshot producer does not call the token-lifecycle helper for the active subscription universe.
3. `core/candidate_feed_dependencies.py` requires exact domain/identity coverage but intentionally leaves dynamic futures/options identities unresolved in candidate declarations.
4. `core/symbol_execution_safety.py` accepts caller-injected `feed_health_by_identity`, but no production caller supplies an authoritative dynamic mapping. Its current execution-time check is not a candidate-ranking isolation proof.
5. `core/ranking_orchestrator.py` applies aggregate feed hold after scoring. It has no verified per-candidate dependency binding.
6. The captured October 1 parquet lacks receive-time, transport-health, subscription-transition, and source-event identity fields. It cannot prove candidate isolation or original initiating cause.

## Invariant contract

- Missing, ambiguous, stale, future-dated, malformed, or mismatched identity evidence is `UNKNOWN` and remains blocked for any candidate that depends on it.
- Per-candidate health is usable only when the evidence binds, in the same runtime cycle, the exact canonical candidate dependency to a positive instrument token, domain/role, canonical symbol/contract identity, active feed session/epoch/reconnect generation, receipt timestamp, source timestamp where required by the consumer contract, and an explicit configured SLA.
- Do not infer option/futures identity from underlying symbol, strike proximity, a truncated sample, aggregate minimum/maximum age, candidate score, or a stale-reason string.
- A candidate may continue through read-only evaluation only when every declared required dependency is explicitly healthy. Unknown or partial dependency declarations remain blocked. No candidate becomes executable from this contract.
- Shared transport down, authentication failure, unsafe runtime, recovery/restart latch, or global feed block remains a global blocker for dependent streams. A local stale instrument cannot clear or override these gates.
- Feed recovery keeps current hysteresis/confirmation behavior. This change does not modify thresholds or recovery rules.
- Output remains `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false` where applicable.

## Design decision

The current producer-consumer contracts do not carry enough authoritative identity evidence end to end to implement generic dynamic option/futures isolation safely. Do not wire the aggregate snapshot or `_TOKEN_TO_SYMBOL` into candidate dependency resolution. The existing token lifecycle helper is the preferred receipt/session authority; the existing instrument rows are the preferred contract authority. The consumer-side candidate dependency key is still absent, and runtime snapshot production does not bind these existing values into a same-cycle identity-health map.

A bounded repair is authorized for the already reproducible cross-symbol ranking hold: when the ranking report is for one symbol, it may use that symbol's row from the existing `FeedHealthTruthDecision` only if the decision certifies `feed_ok_scope=symbol_aggregate`, `global_feed_blocked=false`, websocket connected, safe runtime/feed states, a present healthy target-symbol option row, and an exact same-cycle healthy underlying identity row. The underlying row must bind a positive token and canonical symbol/domain to current feed session/epoch/reconnect generation, active subscription evidence, finite receipt age, and the existing LTP SLA. The producer will derive this from `_UNDERLYING_TOKEN_TO_SYMBOL`, `_LAST_MSG_TS_BY_TOKEN`, and `market_event_graph_subscription_evidence_for_tokens()`; missing or contradictory evidence blocks. All other symbol rows are irrelevant only under those conditions. Unknown scope, absent target row, any global/transport/recovery/auth/depth/LTP blocker, or stale/invalid persisted feed snapshot preserves the aggregate hold. This does not provide same-symbol dynamic option-contract isolation and must not be reported as closure of the full Issue 11 acceptance.

No runtime patch is accepted under this contract until its precise producer and candidate join key are demonstrated from current repository code and a deterministic fixture. If these prerequisites are absent, the accepted result is a documented, tested blocker and a request for source-authority/runtime evidence, not a simulated PASS.

## Must not change

- `core/kite_depth_ws.py`, `core/feed*`, `core/orchestrator.py`, ranking, candidate, execution, risk, order, broker, config, strategy, or token-universe behavior without a path-specific Hermes contract and GSD plan.
- Strategy thresholds, candidate ranking policy, fallback quote semantics, recovery/auth latches, subscription topology, or SIM/PAPER/LIVE authority.
- The established Issue 11 aggregate persisted-truth contract and its stale/malformed/global blocker behavior.
- Issues 1–6 changes or concurrent 123-token universe work.

## Acceptance proof — bounded cross-symbol repair

1. A healthy NIFTY row continues ranking when a separate BANKNIFTY row is stale and all explicit symbol-scope/global invariants above pass, with NIFTY underlying token, session, epoch, reconnect generation, active subscription, receipt age, and SLA validated.
2. The stale BANKNIFTY report remains held.
3. websocket down, `global_feed_blocked=true`, unsafe runtime/recovery/auth state, stale global LTP/depth, persisted snapshot stale/unknown, missing/unknown target row, absent/stale/mismatched underlying token evidence, and opaque/no-scope payloads remain held.
4. The actual runtime snapshot producer → serialized cycle context → per-symbol ranking path is tested.
5. Ranking outputs remain read-only and grant no execution/broker/order authority.

## Remaining full Issue 11 acceptance proof

A code repair can pass only if tests prove all of the following through the actual existing producer and consumer:

1. One exact stale secondary option blocks candidates requiring that identity while a candidate with an independently declared healthy dependency can continue read-only evaluation.
2. Stale required underlying blocks every dependent candidate.
3. A shared transport/auth/recovery/global blocker blocks all dependent candidates, including when local rows appear fresh.
4. Missing/ambiguous/dynamic identity, token mismatch, wrong session/epoch, stale receipt, missing SLA, future timestamp, malformed age, and candidate dependency omission fail closed.
5. Configured universe is preserved dynamically; no hard-coded 53 and no reduction from the configured universe.
6. Candidate decision is deterministic and carries explicit health validity/reasons; no implicit global-boolean interpretation.
7. Existing ranking, execution, risk, recovery, Issues 1–6, and token-universe regressions pass.
8. Mutation attacks that suppress stale state, misclassify an underlying, drop a dependency, or clear global transport block are killed.
9. Independent verification attacks at least one unseen mismatch (e.g. token correct but reconnect generation stale).
10. No broker/order/live/paper authority is introduced.

Same-symbol secondary-option, exact candidate token/contract dependency, dynamic futures identity, and recovery/flapping scenario requirements remain open until authoritative candidate dependency fields and same-cycle token/contract health evidence are joined. Keep `candidate_isolation_status=PARTIAL` and do not mark Issue 11 or campaign acceptance green until every requirement is proven. If current source authority remains insufficient, record the exact missing evidence and keep it `UNKNOWN`.

## Rollback

Revert only the exact candidate-level producer/consumer patch and associated tests/artifacts introduced under a later GSD plan. Preserve the pre-existing global feed and persisted-snapshot blockers. A rollback must never restore aggregate-health-based selective unholding.

## Agent Work Contract

Campaign issue contract; see `issues_7_11_campaign_review.md` for the PR-level Hermes/GSD scope and actions.

## Scope Guard

Issue-level design boundary and restrictions are defined above; the consolidated review records the full campaign boundary.

## Grill Me Review

Campaign risk critique and unresolved proof limits are recorded in `issues_7_11_campaign_review.md`.

## Hermes Review

This file is the issue-specific Hermes contract. The consolidated review records the cross-issue architecture review.

## GSD Review

Execution evidence and test limits are recorded in `issues_7_11_campaign_review.md`; this contract alone is not implementation proof.

## QA / Safety Review

Safety boundary and verification limits are recorded in `issues_7_11_campaign_review.md`.

## High-Risk Path Review

See `issues_7_11_campaign_review.md` for the cross-cutting review of feed and orchestrator high-risk paths. This issue contract does not authorize runtime or broker actions.

## Acceptance Proof

Issue-specific acceptance criteria are defined above. Cross-issue executed proof and its limitations are recorded in `issues_7_11_campaign_review.md`.

## Runtime Proof Required After Merge

Runtime proof requirements are recorded in `issues_7_11_campaign_review.md`; offline contract text does not establish runtime parity.

## What This PR Does Not Prove

See the consolidated review for campaign-level limitations. This issue contract does not independently claim live verification.

## Human Approval

This design contract does not represent human approval. The PR remains subject to human review as described in `issues_7_11_campaign_review.md`.
