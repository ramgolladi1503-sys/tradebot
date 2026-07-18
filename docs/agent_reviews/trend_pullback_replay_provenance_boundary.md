# Trend Pullback Replay Provenance Boundary

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Define Trend Pullback replay provenance boundary
- scope: Record decision-critical production inputs, point-in-time provenance status, replay boundary, and next safe integration steps for Trend Pullback.
- requested_paths: `docs/agent_reviews/trend_pullback_replay_provenance_boundary.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check
- acceptance_proof: `TREND_PULLBACK_REPLAY_PROVENANCE_BOUNDARY_DEFINED`

## Scope Guard

This is documentation-only provenance work. It does not run Trend full-corpus replay, modify production strategy code, change runtime wiring, touch profiles, read or mutate broker state, or alter corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: trend_pullback_replay_provenance_boundary
- decision: TREND_PULLBACK_REPLAY_PROVENANCE_BOUNDARY_DEFINED
- reason: Trend Pullback remains fixture-proven only until every candidate-presence, score, and fingerprint-critical input is point-in-time replayable.
- timestamp: 2026-07-19T01:50:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/trend_pullback_replay_provenance_boundary.md

## Grill Me Review

Trend Pullback is not production-faithful replay-ready yet. The current local fixture lane proves prefix-causal behavior only: `FIXTURE_READY`, candidate count `2`, checked count `15`, and fixture candidate hash `1578b7b8c02d923962735d629dade0916871c3c3e52b21c525fadb6819220a19`. Full-corpus replay is blocked because critical inputs are supplied through `StrategyContext` and are not yet proven as exact point-in-time replay artifacts.

## Hermes Review

Decision-critical inputs and provenance status:

| Input | Production Use | Replay Status | Boundary |
|---|---|---|---|
| `completed_bar_history` | Validates exactly the last four completed 1-minute bars and builds setup timestamps. | Exact if sourced from immutable per-session 1-minute bars with monotonic completed timestamps. | Candidate presence and setup identity depend on this; no replay without exact history. |
| `vwap` | Gates trend alignment and trigger/spot qualification. | Missing/external until authoritative point-in-time VWAP source is proven. | Full-corpus replay blocked; synthetic fixtures may supply controlled VWAP only. |
| `nearest_support` / `nearest_resistance` | Anchor pullback and invalidation logic. | Missing/external until anchor owner and timestamp are proven. | Full-corpus replay blocked; synthetic fixtures may supply controlled anchors only. |
| `regime.scores.TREND_UP` / `TREND_DOWN` | Selects CALL/PUT path and minimum trend score gate. | Proxy-limited unless replay reconstructs the exact historical `MovementRegimeResult`. | Candidate presence blocked for production-faithful replay. |
| Runtime profile identity | Supplies `MIN_TREND_SCORE`, `MAX_PULLBACK_DISTANCE_PCT`, `MIN_STRUCTURE_RESUME_PCT`. | Exact if resolved profile id, source, and hash are recorded per replay run. | Must be part of candidate fingerprint. |
| `spot_ltp` / previous close | Used in final qualification and scoring. | Exact if derived only from the causal completed prefix at proposal time. | Acceptable derivation, must be recorded. |
| Side evidence | `option_ltp`, premium change, spread, depth. | Proxy-limited for signal-generation replay; exact only with point-in-time option quote provenance. | Does not block underlying signal presence, but blocks execution/P&L/readiness claims. |
| Production setup identity | Timestamps and direction only. | Partial. Production does not emit deterministic `setup_id` or `history_hash`. | Research identity may add hashes but must stay labeled research-only. |

## GSD Review

Safe integration branch boundary:

- Start from current `origin/main=140025d8fc288c2a1c24351e1b242a54bd6a0576`.
- Bring in only Trend research replay modules and tests after every input owner above is classified.
- Do not run full-corpus Trend ensembles until VWAP, anchor, regime-score, completed-history, profile, and candidate fingerprint inputs are exact or explicitly downgraded to non-certifying fixture/proxy mode.
- Keep production `strategies/movement/trend_pullback.py` untouched.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Local prior fixture evidence remains bounded:

- Trend worktree: `/Users/madhuram/tradebot-trend-pullback-causal-replay`
- Current local fixture boundary: `FIXTURE_READY`
- Focused tests: `24 passed`
- Fixture candidate count: `2`
- Fixture checked count: `15`
- Fixture candidate hash: `1578b7b8c02d923962735d629dade0916871c3c3e52b21c525fadb6819220a19`

This document does not add executable code. Validation for this PR is documentation evidence validation and scoped code-excellence checks only.

## Runtime Proof Required After Merge

Before any Trend full-corpus replay claim, produce a replay input manifest proving exact point-in-time ownership for completed history, VWAP, support/resistance anchors, regime scores, profile identity, and setup fingerprint fields. If any of those remain proxy-limited or missing, the verdict must remain fixture/proxy only.

## What This PR Does Not Prove

This PR does not prove Trend full-corpus replay readiness, strategy profitability, exact option P&L, execution fills, spread realization, latency behavior, slippage, paper readiness, live readiness, broker correctness, capital allocation readiness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
