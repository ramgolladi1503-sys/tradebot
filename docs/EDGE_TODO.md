# Tradebot EDGE TODO

This file is the living TODO list for the current opportunity-engine roadmap.

Rule: when a PR is raised, remove that item from this list in the same PR branch so the file always shows remaining work.

## Current active PR

- PR #301 — LIVE-TRUTH-07 Latency / SLO Guard Oscillation Evidence, is implemented by the current PR branch and is therefore removed from the remaining TODO list below.

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
- LIVE-TRUTH-01 — Top Opportunities Executable Truth Alignment
- LIVE-TRUTH-02 — Latest Artifact Non-Empty Preservation
- LIVE-TRUTH-03 — Runtime Snapshot Freshness Guard
- LIVE-TRUTH-04 — Feed Runtime Writer Liveness / WebSocket Recovery Evidence
- LIVE-TRUTH-05 — Market Close State Consistency / Off-Hours Quiescence
- LIVE-TRUTH-06 — Stale Candidate Hygiene Guard

## Locked LIVE-TRUTH stabilization block

- PR #295 — LIVE-TRUTH-01 Top Opportunities Executable Truth Alignment
- PR #296 — LIVE-TRUTH-02 Latest Artifact Non-Empty Preservation
- PR #297 — LIVE-TRUTH-03 Runtime Snapshot Freshness Guard
- PR #298 — LIVE-TRUTH-04 Feed Runtime Writer Liveness / WebSocket Recovery Evidence
- PR #299 — LIVE-TRUTH-05 Market Close State Consistency / Off-Hours Quiescence
- PR #300 — LIVE-TRUTH-06 Stale Candidate Hygiene Guard
- PR #301 — LIVE-TRUTH-07 Latency / SLO Guard Oscillation Evidence
- PR #302 — LIVE-TRUTH-08 SENSEX Reject Calibration Evidence
- PR #303 — LIVE-TRUTH-09 Runtime Health Artifact Consistency
- PR #304 — LIVE-TRUTH-10 Strategy Perf Shadow Fallback Evidence

## Remaining TODO

### Live evidence stabilization

- [ ] PR #302 — LIVE-TRUTH-08 SENSEX Reject Calibration Evidence
- [ ] PR #303 — LIVE-TRUTH-09 Runtime Health Artifact Consistency
- [ ] PR #304 — LIVE-TRUTH-10 Strategy Perf Shadow Fallback Evidence

### Strategy lifecycle governance

- [ ] PR #305 — EDGE-88 Strategy Lifecycle States
- [ ] PR #306 — EDGE-89 Strategy Promotion Gate
- [ ] PR #307 — EDGE-90 Strategy Suspension and Retirement Rules

### Feed extraction/refactor work

- [ ] PR #308 — PR-FEED-08 Extract Pure Tick Utility Helpers
- [ ] PR #309 — PR-FEED-09 Extract Reconnect Decision Policy
- [ ] PR #310 — PR-FEED-10 Extract Subscription Budget Policy
- [ ] PR #311 — PR-FEED-11 Extract Runtime Snapshot Builder
- [ ] PR #312 — PR-FEED-17 Extract Token Resolution Read Model
- [ ] PR #313 — PR-FEED-18 Extract WebSocket Lifecycle Shell
- [ ] PR #314 — PR-FEED-19 Callback Thin-Wiring Refactor

### Replay, edge proof, and readiness

- [ ] PR #315 — EDGE-91 Regime Replay Scenarios
- [ ] PR #316 — EDGE-92 Feed Fault Replay Scenarios
- [ ] PR #317 — EDGE-93 Strategy Replay Proof Pack
- [ ] PR #318 — EDGE-94 End-to-End Edge Acceptance Suite
- [ ] PR #319 — EDGE-95 Paper-Only Edge Gate
- [ ] PR #320 — EDGE-96 Live-Pilot Risk Throttle
- [ ] PR #321 — EDGE-97 Final Edge Readiness Report

## Non-negotiable sequencing

1. Finish PR #301 / LIVE-TRUTH-07 first and merge it green.
2. Do not start LIVE-TRUTH-08 until LIVE-TRUTH-07 is merged.
3. Finish the LIVE-TRUTH stabilization block before EDGE-88 lifecycle governance.
4. Do not start feed refactors before LIVE-TRUTH evidence cleanup proves the runtime truth contracts.
5. Keep every PR narrow, tested, documented, and reviewed.
