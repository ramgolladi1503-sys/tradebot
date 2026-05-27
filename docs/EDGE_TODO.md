# Tradebot EDGE TODO

This file is the living TODO list for the current opportunity-engine roadmap.

Rule: when a PR is raised, remove that item from this list in the same PR branch so the file always shows remaining work.

## Current active PR

- EDGE-87 — Strategy Family Kill/Keep Report, is implemented by the current PR branch and is therefore removed from the remaining TODO list below.

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

## Remaining TODO

### Live evidence stabilization

- [ ] LIVE-TRUTH-01 — Top Opportunities Executable Truth Alignment
- [ ] LIVE-TRUTH-02 — Latest Artifact Non-Empty Preservation
- [ ] LIVE-TRUTH-03 — Stale Candidate Hygiene Guard
- [ ] LIVE-TRUTH-04 — Latency Guard Oscillation Evidence
- [ ] LIVE-TRUTH-05 — SENSEX Reject Calibration Evidence
- [ ] LIVE-TRUTH-06 — Runtime Health Artifact Consistency
- [ ] LIVE-TRUTH-07 — Strategy Perf Shadow Fallback Evidence

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

1. Finish EDGE-87 first and merge it green.
2. Do not start LIVE-TRUTH-01 until EDGE-87 is merged.
3. Finish the LIVE-TRUTH stabilization block before EDGE-88 lifecycle governance.
4. Do not start pilot readiness before paper truth, replay proof, cost truth, live evidence stabilization, and lifecycle gates exist.

## Why LIVE-TRUTH comes before lifecycle governance

The 2026-05-27 live run exposed runtime evidence issues that can pollute promotion and suspension decisions if ignored.

Lifecycle rules should only be built after these are stabilized:

- top-opportunity truth mismatch
- latest artifact empty-cycle overwrite risk
- stale candidate hygiene
- latency guard oscillation evidence
- SENSEX reject calibration evidence
- runtime health artifact consistency
- strategy performance shadow fallback evidence

## Scope guard

- Keep each PR narrow and evidence-backed.
- Do not mix LIVE-TRUTH fixes into EDGE-87.
- Do not start EDGE-88 until EDGE-87 and the LIVE-TRUTH block are complete.
- No adapter integration unless a later PR explicitly scopes pilot behavior.
- No state-changing integration in this roadmap until readiness gates explicitly allow it.
- No fake scoring, cosmetic dashboard work, or PR-loop progress.
- No weakening fallback, stale-feed, quote-truth, or executable-quality protections to make the UI look better.
- Every PR must include focused tests, docs, and agent-review evidence.
- Every PR must keep non-action metadata explicit where applicable, including read-only and no-append guarantees.
