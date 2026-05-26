# Tradebot EDGE TODO

This file is the living TODO list for the current opportunity-engine roadmap.

Rule: when a PR is raised, remove that item from this list in the same PR branch so the file always shows remaining work.

## Current active PR

- EDGE-84 — Outcome Reducer, is implemented by the current PR branch and is therefore removed from the remaining TODO list below.

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

## Remaining TODO

### Paper truth and expectancy

- [ ] EDGE-85 — Strategy Expectancy by Regime
- [ ] EDGE-86 — Slippage and Cost Truth
- [ ] EDGE-87 — Strategy Family Kill/Keep Report

### Strategy lifecycle governance

- [ ] EDGE-88 — Strategy Lifecycle States
- [ ] EDGE-89 — Strategy Promotion Gate
- [ ] EDGE-90 — Strategy Suspension and Retirement Rules

### Feed extraction/refactor work

- [ ] PR-FEED-08 — Extract Pure Tick Utility Helpers
- [ ] PR-FEED-09 — Extract Reconnect Decision Policy
- [ ] PR-FEED-10 — Extract Subscription Budget Policy
- [ ] PR-FEED-11 — Extract Runtime Snapshot Builder
- [ ] PR-FEED-17 — Extract Token Resolution Read Model
- [ ] PR-FEED-18 — Extract WebSocket Lifecycle Shell
- [ ] PR-FEED-19 — Callback Thin-Wiring Refactor

### Replay, edge proof, and readiness

- [ ] EDGE-91 — Regime Replay Scenarios
- [ ] EDGE-92 — Feed Fault Replay Scenarios
- [ ] EDGE-93 — Strategy Replay Proof Pack
- [ ] EDGE-94 — End-to-End Edge Acceptance Suite
- [ ] EDGE-95 — Paper-Only Edge Gate
- [ ] EDGE-96 — Live-Pilot Risk Throttle
- [ ] EDGE-97 — Final Edge Readiness Report

## Non-negotiable sequencing

1. Finish EDGE-84 first and merge it green.
2. Do not start EDGE-85 until EDGE-84 is merged.
3. Do not treat reduced paper outcomes as expectancy until EDGE-85 derives regime-level statistics.
4. Do not start live-pilot readiness before paper truth, replay proof, slippage/cost truth, and strategy lifecycle gates exist.

## Scope guard

- Keep each PR narrow and evidence-backed.
- No external execution-adapter integration unless a later PR explicitly scopes live-pilot behavior.
- No broker-state changes in this roadmap until readiness gates explicitly allow them.
- No fake scoring, cosmetic dashboard work, or PR-loop progress.
- No weakening fallback, stale-feed, quote-truth, or executable-quality protections to make the UI look better.
- Every PR must include focused tests, docs, and agent-review evidence.
- Every PR must keep non-action metadata explicit where applicable, including read-only and no-append guarantees.
