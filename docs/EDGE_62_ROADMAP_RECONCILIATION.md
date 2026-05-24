# EDGE-62 — Roadmap Reconciliation: EDGE + FEED + Strategy

## Purpose

EDGE-62 locks the current roadmap after the recent UI-ranking, fallback, feed-truth, top-opportunity, direction-bias, and capital-selection work.

This is a documentation-only reconciliation PR. It does not change runtime behavior, strategy behavior, scoring, ranking, dashboard rendering, feed handling, or broker boundaries.

## Current verified base

Latest completed PRs:

- EDGE-38 — Runtime Evidence Capture Guard
- EDGE-42 — Quote Truth Single Source of Truth
- EDGE-43 — Feed Health Split-Brain Fix
- EDGE-45 — Symbol-Level Execution Safety Gate
- EDGE-46 — Soft Reject Separation
- EDGE-47 — Candidate Status Contract Cleanup
- EDGE-48 — Scoring Truth Hardening
- EDGE-49 — Opportunity Selector Evidence Upgrade
- EDGE-50 — Latest Artifact Freshness Guard
- EDGE-51 — Latest Artifact Freshness Runtime Wiring
- EDGE-52 — Dashboard Freshness Visibility
- EDGE-53 — Streamlit Freshness Panel Rendering
- EDGE-54 — Home Page Freshness Panel Placement
- EDGE-55 — Tiny Runtime Home Freshness Panel Call
- EDGE-56 — Home Freshness Failure Visibility
- EDGE-57 — Fallback Advisory-Only Entry Contract
- EDGE-58 — Top Opportunity Executable Truth Contract
- EDGE-59 — Top Opportunity Truth Reader Wiring
- EDGE-60 — BUY/PE/CE Directional Bias Audit
- EDGE-61 — Capital Allocation / Selection Policy Contract

## What these PRs solved

### Truth and safety foundation

The product now has read-only contracts for quote truth, feed truth, symbol-level execution safety, candidate state, candidate status, score truth, top-opportunity truth, directional-bias evidence, and capital-selection explanation.

### Dashboard visibility foundation

Freshness visibility exists from artifact freshness through dashboard reader and Home placement. Top-opportunity truth is wired at the reader boundary so display-only or fallback-backed rows are demoted before UI/runtime consumers treat them as top executable rows.

### Evidence foundation

The system has evidence contracts that explain why rows are selected, rejected, capped, skipped, stale, advisory-only, fallback-only, or directionally concentrated.

## What is still not solved

### Strategy edge is not proven

The current contracts prevent false confidence. They do not prove alpha, expectancy, or profitable setups.

### Feed recovery is not fully finished

Feed truth exists, but the full FEED roadmap still needs hold gates, warmup gates, token freshness gates, runtime snapshot wiring, candidate integration, ranking suppression, policy separation, config hardening, and replay tests.

### Strategy architecture is still ahead

MarketState, regime state machine, StrategySpec registry, CandidateIntent, candidate pool, strategy rebuilds, option-chain confirmation, exit models, conflict/consensus, NoTradeOracle, and paper-truth proof still remain.

### Runtime selection is not activated

EDGE-61 is a read-only policy contract. It does not wire live or paper runtime allocation.

## Canonical next order

Do not skip ahead. Work one PR at a time. A PR is complete only when it is merged and CI is green.

### Phase A — Feed hardening before strategy intelligence

1. PR-FEED-01 — Feed Architecture Audit and Contract Lock
2. PR-FEED-02R — Canonical Feed Health Contract Reconciliation
3. PR-FEED-03 — Feed Hold Gate
4. PR-FEED-04 — Feed Recovery Warmup Gate
5. PR-FEED-05 — Exact Option Token Freshness Gate
6. PR-FEED-12 — Wire Canonical Feed Decision Into Runtime Snapshots
7. PR-FEED-13 — Candidate Pipeline Feed Block Integration
8. PR-FEED-14 — Ranking Suppression for Feed-Risky Candidates
9. PR-FEED-15 — Live/Paper Feed Policy Separation
10. PR-FEED-16 — Feed Config Hardening
11. PR-FEED-20 — End-to-End Feed Fault Replay Tests

### Phase B — Strategy intelligence contracts

12. EDGE-63 — MarketState Model
13. EDGE-64 — Regime State Machine
14. EDGE-65 — StrategySpec Registry
15. EDGE-66 — Strategy Quality Audit
16. EDGE-67 — Strategy Hypothesis Contracts
17. EDGE-68 — Replace Hardcoded Strategy Eligibility
18. EDGE-69 — CandidateIntent Contract
19. EDGE-70 — Candidate Pool and Validator
20. EDGE-71 — Convert Existing Strategies to Candidate Generators
21. EDGE-72 — Breakout Strategy Rebuild
22. EDGE-73 — VWAP Strategy Rebuild
23. EDGE-74 — Mean Reversion Strategy Rebuild
24. EDGE-75 — Zero Hero Expiry Strategy Rebuild
25. EDGE-76 — Option Chain Confirmation Layer
26. EDGE-77 — Strategy-Specific Exit Models
27. EDGE-78 — Strategy Parameter Robustness Tests
28. EDGE-79 — Strategy Conflict and Consensus Engine
29. EDGE-80 — NoTradeOracle
30. EDGE-81 — NoTrade Evidence in Review Queue/UI
31. EDGE-82 — Final Executable Trade Quality Gate

### Phase C — Paper truth and strategy lifecycle

32. EDGE-83 — Paper Truth Journal
33. EDGE-84 — Outcome Reducer
34. EDGE-85 — Strategy Expectancy by Regime
35. EDGE-86 — Slippage and Cost Truth
36. EDGE-87 — Strategy Family Kill/Keep Report
37. EDGE-88 — Strategy Lifecycle States
38. EDGE-89 — Strategy Promotion Gate
39. EDGE-90 — Strategy Suspension and Retirement Rules

### Phase D — Feed internals cleanup after behavior contracts

40. PR-FEED-08 — Extract Pure Tick Utility Helpers
41. PR-FEED-09 — Extract Reconnect Decision Policy
42. PR-FEED-10 — Extract Subscription Budget Policy
43. PR-FEED-11 — Extract Runtime Snapshot Builder
44. PR-FEED-17 — Extract Token Resolution Read Model
45. PR-FEED-18 — Extract WebSocket Lifecycle Shell
46. PR-FEED-19 — Callback Thin-Wiring Refactor

### Phase E — Replay and readiness proof

47. EDGE-91 — Regime Replay Scenarios
48. EDGE-92 — Feed Fault Replay Scenarios
49. EDGE-93 — Strategy Replay Proof Pack
50. EDGE-94 — End-to-End Edge Acceptance Suite
51. EDGE-95 — Paper-Only Edge Gate
52. EDGE-96 — Live-Pilot Risk Throttle
53. EDGE-97 — Final Edge Readiness Report

## Hard boundary rules

- No broker behavior in roadmap docs.
- No live execution changes unless a future scoped PR explicitly allows it.
- No dashboard work unless scoped.
- No strategy tuning hidden inside feed work.
- No feed refactor hidden inside strategy work.
- No runtime allocation wiring hidden inside documentation work.
- No deleting or weakening tests to make CI pass.
- No broad cleanup PRs unless they are explicitly listed and scoped.

## Immediate next PR

After EDGE-62 is merged and CI is green, start:

```text
PR-FEED-01 — Feed Architecture Audit and Contract Lock
```

PR-FEED-01 must be audit/contract-lock only. It should identify current feed owners, current feed-health contracts, duplicate paths, known stale/fallback pathways, runtime consumers, dashboard consumers, and the exact FEED contract owner before implementing behavioral feed gates.

## Acceptance criteria for EDGE-62

- Roadmap order is documented.
- Completed PRs are separated from remaining work.
- FEED work is placed before strategy rebuilds.
- Strategy rebuilds are not started prematurely.
- Runtime selection/allocation is not activated.
- Docs explain what has been solved and what has not been solved.
- Agent review evidence exists.
- CI is green.
