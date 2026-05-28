# Tradebot EDGE TODO

This file is the living TODO list for the current backtest/walk-forward and elite-hardening roadmap.

Rule: when a PR is raised, remove that item from this list in the same PR branch so the file always shows remaining work.

## Current active PR

- Issue #320 — EDGE-99 Replay Clock and No-Future-Leak Guard, is implemented by the current PR branch and is therefore removed from the remaining TODO list below.

## Recently completed

- EDGE-69 — CandidateIntent Contract
- EDGE-70 — Candidate Pool and Validator, adapted to CandidateIntent
- EDGE-71 — Convert Existing Strategies to Candidate Generators
- EDGE-72 — Breakout Strategy Rebuild
- EDGE-73 — VWAP Strategy Rebuild
- EDGE-74 — Mean Reversion Strategy Rebuild
- EDGE-75 — Zero Hero Expiry Strategy Rebuild
- EDGE-76 — Option Chain Confirmation Layer
- EDGE-77 — Strategy-Specific Exit Models
- EDGE-78 — Strategy Parameter Robustness Tests
- EDGE-79 — Strategy Conflict and Consensus Engine
- HOTFIX/EDGE-79A — Live Indicator Readiness Diagnostics
- HOTFIX/EDGE-79B — Market Close Feed State Classifier
- EDGE-80 — NoTradeOracle
- EDGE-81 — NoTrade Evidence in Review Queue/UI
- EDGE-82 — Final Executable Trade Quality Gate
- EDGE-83 — Paper Truth Journal
- EDGE-84 — Outcome Reducer
- EDGE-85 — Strategy Expectancy by Regime
- EDGE-86 — Slippage and Cost Truth
- EDGE-87 — Strategy Family Kill/Keep Report
- EDGE-88 — Strategy Lifecycle States
- EDGE-89 — Strategy Promotion Gate
- EDGE-90 — Strategy Suspension and Retirement Rules
- EDGE-91 — Regime Replay Scenarios
- EDGE-91A — Session Path Replay Analytics
- EDGE-92 — Feed Fault Replay Scenarios
- EDGE-93 — Strategy Replay Proof Pack
- EDGE-94 — End-to-End Edge Acceptance Suite
- EDGE-95 — Paper-Only Edge Gate
- EDGE-96 — Live-Pilot Risk Throttle
- EDGE-97 — Final Edge Readiness Report
- TEST-STAB-04 — Fix websocket restart compatibility regressions
- TEST-STAB-04A — Restore websocket test fixture compatibility
- EDGE-98 — Historical Dataset Contract
- EDGE-99 — Replay Clock and No-Future-Leak Guard

## Remaining TODO

### Backtest / walk-forward foundation

- [ ] Issue #321 — EDGE-100 — Next roadmap card after EDGE-99
- [ ] Issue #322 — EDGE-101 — Next roadmap card after EDGE-100
- [ ] Issue #323 — EDGE-102 — Next roadmap card after EDGE-101
- [ ] Issue #324 — EDGE-103 — Next roadmap card after EDGE-102
- [ ] Issue #325 — EDGE-104 — Next roadmap card after EDGE-103
- [ ] Issue #326 — EDGE-105 — Next roadmap card after EDGE-104
- [ ] Issue #327 — EDGE-106 — Next roadmap card after EDGE-105
- [ ] Issue #328 — EDGE-107 — Next roadmap card after EDGE-106
- [ ] Issue #329 — EDGE-108 — Next roadmap card after EDGE-107
- [ ] Issue #330 — EDGE-109 — Next roadmap card after EDGE-108
- [ ] Issue #331 — EDGE-110 — Next roadmap card after EDGE-109
- [ ] Issue #332 — EDGE-111 — Next roadmap card after EDGE-110
- [ ] Issue #333 — EDGE-112 — Next roadmap card after EDGE-111
- [ ] Issue #334 — EDGE-113 — Next roadmap card after EDGE-112

### TB-ELITE hardening

- [ ] TB-ELITE-01 through TB-ELITE-21 remain locked behind their individual GitHub Project issue cards.

## Non-negotiable sequencing

1. Finish issue #320 / EDGE-99 first and merge it green.
2. Do not start issue #321 / EDGE-100 before #320 is merged green and explicitly confirmed.
3. One issue equals one PR.
4. Keep every PR narrow, tested, documented, and reviewed.
