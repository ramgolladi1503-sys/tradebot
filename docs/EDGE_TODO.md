# Tradebot EDGE TODO

This file is the living TODO list for the current opportunity-engine roadmap.

Rule: when a PR is raised, remove that item from this list in the same PR branch so the file always shows remaining work.

## Current active PR

- PR #297 — LIVE-TRUTH-03 Runtime Snapshot Freshness Guard, is implemented by the current PR branch and is therefore removed from the remaining TODO list below.

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

- [ ] PR #298 — LIVE-TRUTH-04 Feed Runtime Writer Liveness / WebSocket Recovery Evidence
- [ ] PR #299 — LIVE-TRUTH-05 Market Close State Consistency / Off-Hours Quiescence
- [ ] PR #300 — LIVE-TRUTH-06 Stale Candidate Hygiene Guard
- [ ] PR #301 — LIVE-TRUTH-07 Latency / SLO Guard Oscillation Evidence
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

## LIVE-TRUTH-03 acceptance subtasks

LIVE-TRUTH-03 must prove latest runtime snapshots are fresh enough to trust before later runtime-health or lifecycle decisions consume them.

In scope:

- Evaluate runtime evidence snapshots by artifact name.
- Accept numeric epoch and ISO timestamp fields.
- Detect missing timestamps.
- Detect stale timestamps by max-age threshold.
- Detect future timestamps beyond tolerance.
- Support per-artifact max-age overrides.
- Emit read-only freshness evidence.

Out of scope:

- Refreshing feeds.
- Reconnecting WebSockets.
- Market-close quiescence; that belongs to LIVE-TRUTH-05.
- Candidate generation changes.
- Dashboard changes.
- Runtime wiring unless a later PR explicitly scopes it.

## LIVE-TRUTH-05 close-state scope and acceptance

LIVE-TRUTH-05 exists because final close evidence must not look like normal intraday no-trade behavior.

Scope:

- Ensure `feed_runtime`, `market_snapshot`, `top_opportunities`, and runtime health agree on `market_open`.
- After market close, move runtime evidence to `OFFHOURS` / `MARKET_CLOSED` state.
- Stop expensive candidate scanning after close unless replay/off-hours analysis is explicitly enabled.
- Top opportunities should show `MARKET_CLOSED` or `OFFHOURS_BLOCKED`, not normal `NO_TRADE`.
- CPU should drop in off-hours mode.
- WebSocket down plus market closed must not continue high-frequency SLO loops.

Acceptance:

Given `market_snapshot.market_open=false`:

- `feed_runtime` must not report `market_open=true` without a freshness warning.
- `top_opportunities` must include `market_state=MARKET_CLOSED/OFFHOURS`.
- `source_candidate_count` should be `0` unless off-hours planning is explicitly enabled.
- `executable_count` must be `0`.
- No live execution action.
- Runtime health must show quiet/off-hours mode.

## Non-negotiable sequencing

1. Finish PR #297 / LIVE-TRUTH-03 first and merge it green.
2. Do not start LIVE-TRUTH-04 until LIVE-TRUTH-03 is merged.
3. Finish the LIVE-TRUTH stabilization block before EDGE-88 lifecycle governance.
4. Do not start feed refactors before LIVE-TRUTH evidence cleanup proves the runtime truth contracts.
5. Do not start pilot readiness before paper truth, replay proof, cost truth, live evidence stabilization, and lifecycle gates exist.

## Dependency order

```text
EDGE-86 / EDGE-87 paper truth
  -> LIVE-TRUTH runtime evidence cleanup
  -> EDGE-88/89/90 strategy lifecycle
  -> PR-FEED refactors
  -> Replay/readiness
```

## Why LIVE-TRUTH comes before lifecycle governance

The 2026-05-27 live run exposed runtime evidence issues that can pollute promotion and suspension decisions if ignored.

Lifecycle rules should only be built after these are stabilized:

- top-opportunity truth mismatch
- top executable trace missing entry, target, stop loss, risk-reward, rank, quote-age, and signal quote fields
- latest artifact empty-cycle overwrite risk
- frozen feed runtime and market snapshot artifacts
- WebSocket disconnect / subscribe-failed recovery visibility
- market-close state inconsistency and off-hours loop noise
- stale candidate hygiene
- latency / SLO guard oscillation evidence
- SENSEX reject calibration evidence
- runtime health artifact consistency
- strategy performance shadow fallback evidence

## Scope guard

- Keep each PR narrow and evidence-backed.
- Do not mix LIVE-TRUTH-04 or later fixes into LIVE-TRUTH-03.
- Do not start EDGE-88 until EDGE-87 and the LIVE-TRUTH block are complete.
- Do not put feed refactor work before runtime truth evidence cleanup.
- No adapter integration unless a later PR explicitly scopes pilot behavior.
- No state-changing integration in this roadmap until readiness gates explicitly allow it.
- No fake scoring, cosmetic dashboard work, or PR-loop progress.
- No weakening fallback, stale-feed, quote-truth, or executable-quality protections to make the UI look better.
- Every PR must include focused tests, docs, and agent-review evidence.
- Every PR must keep non-action metadata explicit where applicable, including read-only and no-append guarantees.
