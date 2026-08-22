# Raj Arora External-Seeded Proxy V1 — Prior-Evidence Reconciliation

This file was added before any V1 development outcome was accessed.

## Overlap discovered

The repository already contains canonical/repaired strategy contracts materially related to this external-seeded family:

- `opening_range_retest_v1`: ordered opening-range breakout / retest / continuation semantics have already been repaired and causally specified in the repository.
- `trend_pullback_v1`: controlled pullback and resume semantics already exist as a canonical TradeBot strategy family.
- `failed_breakout_trap_v1`: failed structural breakout / reversal semantics already exist as a canonical TradeBot family.

Prior research also records that generic/proxy strategy runners must not be treated as evidence about the production strategies. A previous historical proxy runner was invalidated because it implemented simplified local formulas rather than invoking canonical production generators.

## Consequence for this V1

`RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1` is therefore **not** a replacement certification of any canonical TradeBot strategy. Its purpose is narrower:

1. test whether a small externally seeded opening-auction interpretation exhibits a directional underlying effect on the frozen NIFTY corpus;
2. use the result as hypothesis evidence only;
3. if a proxy survives, reconcile its exact event semantics against the canonical strategy callable before making any TradeBot integration claim;
4. if the proxy fails, close this external-seeded family without extending the grid.

Existing canonical strategy evidence remains authoritative for canonical strategy behavior.

## Important prior signal

Repository reconstruction records that ORB produced strongly negative historical results. That is adverse prior evidence for the opening-range continuation interpretation. It is not automatically a terminal verdict on the V1 proxies because the event definitions and target semantics are not guaranteed identical, but it materially lowers the prior probability that a simple ORB interpretation is the missing edge.

## No post-result expansion

The V1 freeze remains unchanged. This reconciliation does not authorize a broader sweep, a new threshold search, or validation/holdout access. Any later materially different hypothesis must receive a new generation identity and count as a new multiple-testing family.
