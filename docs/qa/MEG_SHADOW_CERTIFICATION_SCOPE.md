# TradeBot MEG Shadow Certification Scope

## Target

The certification target is one supervised, read-only Market Event Graph shadow path:

```text
authenticated startup
→ exact feed and subscription truth
→ durable packet/depth/runtime persistence
→ completed NIFTY constituent bars
→ Market Event Graph observation
→ canonical EXECUTABLE / ADVISORY_ONLY / BLOCKED authority
→ operator UI partitions
→ manual-approval and broker-write firewall
→ clean shutdown, restart, reconciliation, and sealed evidence
→ post-market reliability certificate
```

The target is advisory-only. It does not grant paper or live execution authority.

## Required offline gates

All eight gates must execute and pass on one immutable repository SHA:

1. `AUTHENTICATION_AND_STARTUP`
2. `FEED_AND_SUBSCRIPTION_TRUTH`
3. `PERSISTENCE_AND_SHUTDOWN`
4. `MARKET_EVENT_GRAPH_OBSERVATION`
5. `AUTHORITY_RANKING_AND_UI`
6. `MANUAL_APPROVAL_AND_BROKER_FIREWALL`
7. `RESTART_AND_RECONCILIATION`
8. `AI_RELIABILITY_AND_EVIDENCE_INTEGRITY`

A missing test file, skipped gate group, timeout, nonzero return code, malformed report, or semantic-hash mismatch fails closed.

## Required live gate

Offline success is not the final certificate. A fresh governed PR #763 market session must produce a sealed PR #772 post-market reliability certificate proving:

- actual post-mode FULL NIFTY packet delivery;
- exact read-only subscription and constituent coverage;
- completed constituent bars;
- required Market Event Graph traversal;
- canonical executable/advisory/blocked operator partitions;
- fallback, synthetic, stale, unknown, or contradictory rows receive no executable selection score or capital;
- no broker-write or order authority;
- complete persistence drain, shutdown, restart evidence, and immutable sealing.

Until this certificate passes, the strongest allowed system verdict is:

`IMPLEMENTATION_COMPLETE_LIVE_EVIDENCE_PENDING`

## Final passing verdict

The assembler may emit:

`MEG_SHADOW_SYSTEM_CERTIFIED_READ_ONLY`

only when both conditions are true:

- all eight offline gates pass on the final SHA;
- PR #772 emits `PASS_READ_ONLY_POST_MARKET_RELIABILITY` from one fresh PR #763 evidence root.

## Explicit exclusions

This certification does not prove or authorize:

- strategy profitability or structural edge;
- expected returns, hit rate, or drawdown quality;
- historical executable bid/ask fills;
- broker connectivity or real fill quality;
- paper trading or live trading;
- order placement, modification, cancellation, or exit;
- unattended autonomous operation;
- legacy multi-strategy certification.

## Merge boundary

The certification PR remains stacked after PR #763, PR #771, and PR #772. It must not be merged into PR #763 or `main` before the fresh PR #763 live proof, final-head CI, evidence review, and explicit human approval.