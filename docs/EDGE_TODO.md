# Tradebot EDGE TODO

This file is the living TODO list for the EDGE 37–56 remediation roadmap.

Rule: when an EDGE PR is completed and merged, remove that item from this list in the next PR branch. The list should only show remaining work.

## Remaining EDGE PRs

- [ ] EDGE-38 — Runtime Evidence Capture Guard
- [ ] EDGE-39 — Expired Contract Token Resolution Guard
- [ ] EDGE-40 — Quote Timestamp/Age Consistency Guard
- [ ] EDGE-41 — Fallback Execution Firewall
- [ ] EDGE-42 — Quote Truth Single Source of Truth
- [ ] EDGE-43 — Feed Health Split-Brain Fix
- [ ] EDGE-44 — Feed Recovery Runtime Wiring
- [ ] EDGE-45 — Symbol-Level Execution Safety Gate
- [ ] EDGE-46 — Soft Reject Separation
- [ ] EDGE-47 — Candidate Status Contract Cleanup
- [ ] EDGE-48 — Scoring Truth Hardening
- [ ] EDGE-49 — Opportunity Selector Evidence Upgrade
- [ ] EDGE-50 — Latest Artifact Freshness Guard
- [ ] EDGE-51 — Runtime Evidence Dashboard Contract
- [ ] EDGE-52 — Strategy Outcome Journal
- [ ] EDGE-53 — Replay-Based Strategy Validation
- [ ] EDGE-54 — Strategy Family Kill/Keep Report
- [ ] EDGE-55 — Executable Trade Quality Gate
- [ ] EDGE-56 — Paper Trading Truth Acceptance Gate

## Non-negotiable sequencing

Do not start strategy tuning before market truth is fixed.

Immediate priority order:

1. EDGE-39 — Expired Contract Token Resolution Guard
2. EDGE-40 — Quote Timestamp/Age Consistency Guard
3. EDGE-41 — Fallback Execution Firewall
4. EDGE-44 — Feed Recovery Runtime Wiring
5. EDGE-38 — Runtime Evidence Capture Guard

## Scope guard

- No broker calls unless a scoped PR explicitly requires broker-boundary proof.
- No live order behavior in these remediation PRs.
- No dashboard polish before truth/reporting fixes.
- No strategy rewrite before evidence replay and quote/token truth guards.
- Every PR must include tests and acceptance proof.
