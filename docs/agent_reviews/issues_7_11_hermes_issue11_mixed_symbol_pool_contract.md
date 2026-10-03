# Hermes Stage 1 — Issue 11 mixed-symbol candidate-pool scope

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Prevent symbol-scoped feed truth from authorizing mixed-symbol score sets
**scope:** Narrow follow-up to the bounded cross-symbol ranking hold in `issues_7_11_hermes_issue11_candidate_isolation_contract.md`.

## MAP finding

`core/ranking_orchestrator.py::build_ranked_opportunity_report()` passes `candidate_pool.symbol` to `_rank_with_feed_hold()`. The score report is built from every candidate returned by each generator. `core/candidate_pool_orchestrator.py` records the context symbol on the pool but does not reject a candidate whose own `symbol` differs. Therefore an explicit healthy scope for the context symbol could be applied to a mixed-symbol score set. This is a fail-open scope mismatch.

## Contract

Symbol-scoped feed isolation is allowed only when the nonempty scoring report contains exclusively records whose symbol is a canonical uppercase string exactly equal to the canonical uppercase pool symbol. Do not trim, case-fold, stringify, or otherwise canonicalize either identity at this trust boundary. An empty score set, absent/blank/noncanonical symbol, malformed score record, or any mismatch must pass `symbol=None` to the existing feed hold gate, preserving the aggregate decision. Do not silently drop or rewrite candidates as part of this repair.

The guard does not establish exact candidate option/futures contract health. It only prevents a symbol-scoped underlying/feed-health proof from being applied to scores belonging to another symbol. All global, transport, auth, recovery, persisted-snapshot, freshness, risk, and execution gates remain unchanged.

## Invariants

- Ranking symbols are derived from actual `OpportunityScoreRecord.symbol` values, not just `CandidatePoolReport.symbol`.
- A mixed, empty, malformed, blank, or noncanonical score set cannot obtain explicit-symbol isolation.
- Homogeneous matching pools retain the existing bounded behavior.
- No candidate is removed, promoted, rewritten, or made executable by this guard.
- Read-only/no-order/no-broker authority remains closed.
- Exact dynamic contract identity and full Issue 11 acceptance remain UNKNOWN.

## Acceptance proof

1. A mixed NIFTY/BANKNIFTY pool with local BANKNIFTY degradation remains aggregate-held; no NIFTY row is used to scope the combined report.
2. A homogeneous NIFTY pool retains the bounded healthy-NIFTY ranking behavior.
3. Empty, malformed, blank, lowercase, or padded scored identities cannot obtain symbol-scoped behavior.
4. Existing global-blocker and recovery tests remain blocked.
5. A mutation that removes the homogeneous-symbol check is caught by the mixed-pool regression.
6. Adjacent ranking, feed recovery, candidate dependency, execution-safety, and token-universe tests pass.

## GSD verification update

Direct helper tests now cover canonical matching plus empty, blank, malformed/non-string, mixed, lower-case, padded, and mismatched pool/score identities. All noncanonical identities preserve aggregate gating. Exact current source broad offline regression: 8735 passed, 9 skipped, 29 deselected, 1474 warnings; focused ranking/heritage/feed-hold suite: 93 passed. These are offline proofs only.

## Blast radius

Expected change surface: `core/ranking_orchestrator.py`, its read-only tests, and Issue 11 graph/ledger/verdict artifacts. The only decision change is that heterogeneous/empty score reports retain the prior aggregate hold. Strategy semantics, candidate construction, ranking weights/order, feed thresholds, subscriptions, recovery latches, current token universe, config, risk, execution, broker, and order paths are outside scope.

Rollback: revert only the symbol-homogeneity guard, its tests, and its evidence entries. Preserve the existing aggregate hold and the preceding target-symbol identity checks.

## Explicit limit

This contract does not solve candidate-to-exact-option/futures dependency identity. Do not report Issue 11 or campaign acceptance as complete from this bounded repair.
