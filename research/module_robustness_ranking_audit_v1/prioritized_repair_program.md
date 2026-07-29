# Prioritized Repair Program

1. Lifecycle identity and trace contract: add stable market_event_id through reconciliation_id, read-only first.
2. Feed freshness/sequence truth: certify disconnect, reconnect, stale-connected, duplicate and out-of-order ticks.
3. Market-state snapshot atomicity: freeze timestamp and completed-bar contracts.
4. Strategy and signal contract normalization: certify every active movement generator with CE/PE direction semantics.
5. TradeBuilder correctness: fixture valid/reject/stale/fallback/exception outcomes.
6. Phase 1/Phase 2 gate authority and reasons: preserve hard reject, soft downgrade, fallback permissions.
7. Candidate-pool dedupe and lifecycle expiry: reconcile counts by producer and economic identity.
8. Centralized fallback/degraded authority: one policy consumed by scoring/ranking/UI/executable truth.
9. Risk/executable-truth fail-closed guarantees: missing/contradictory inputs block actionability.
10. Orchestration transactionality and error isolation: stage atomic snapshots and no stale reuse.
11. Score naming/calibration semantics: setup score unless calibration metadata exists.
12. Ranked-snapshot identity and determinism: stable snapshot hash and contiguous rank invariants.
13. UI/approval binding: actionable controls require ranked snapshot identity and current authority.
14. Order-intent idempotency and revalidation: mock broker timeout/rejection/ambiguous outcome.
15. Broker update/reconciliation recovery: partial fill/out-of-order/restart fixtures.
16. Observability and fault-injection regression suite: run deterministic scenario pack in CI.


## Vertical Slice Certification V1 Follow-up

- Promote `compression_breakout_v1` from audit harness to production-fixture certification only after TradeBuilder, broker timeout/retry, and restart reconciliation use real local fixtures.
- Fix UI fallback actionability in a narrow PR before considering approval certification complete.
