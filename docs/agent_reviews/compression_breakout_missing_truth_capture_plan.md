# Compression Breakout Absent-Truth Capture Plan

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Specify absent truth capture for Compression Breakout replay certification
- scope: Future implementation specification only; no production instrumentation is added in this PR.
- requested_paths: `docs/agent_reviews/compression_breakout_absent_truth_capture_plan.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check
- acceptance_proof: `COMPRESSION_MISSING_TRUTH_CAPTURE_PLAN_DEFINED`

## Scope Guard

This document is read-only planning. It does not modify Compression production code, does not create a replay implementation branch, and does not run Compression full-corpus replay.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: compression_breakout_absent_truth_capture_plan
- decision: COMPRESSION_MISSING_TRUTH_CAPTURE_PLAN_DEFINED
- reason: `COMPRESSION_INSUFFICIENT_REQUIRED_TRUTH` blocks causal replay implementation until exact context fields are captured.
- timestamp: 2026-07-19T02:52:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/compression_breakout_absent_truth_capture_plan.md

## Grill Me Review

Compression cannot be certified by deriving a clean research snapshot from candles if production consumes live/runtime `StrategyContext` fields. The future capture must record exact context values and owner provenance, not just sufficient OHLCV to build approximations.

## Hermes Review

Absent or limited fields and required capture:

| Field Group | Runtime Owner To Instrument | Exact Fields To Persist | Required Timestamp | Historical Reconstruction |
|---|---|---|---|---|
| VWAP | live indicator/market snapshot owner | VWAP value, formula id, window, volume basis, input bar ids, fallback flag | last input bar timestamp, proposal timestamp, receipt timestamp | limited because index-candle volume is zero and fallback state is not frozen |
| ATR/range | indicator/context owner | `atr_short`, `atr_long`, true-range window ids, `range_width_pct`, day high/low source, denominator | last completed bar timestamp and proposal timestamp | limited unless owner/cutoff is captured |
| compression regime | `MovementRegimeClassifier.classify` caller | full `MovementRegimeResult`, upstream context hash, classifier code hash | proposal timestamp | limited by upstream fields |
| directional anchors | canonical anchor owner | `nearest_support`, `nearest_resistance`, `orb_high`, `orb_low`, `day_high`, `day_low`, precedence winner, owner, update time | anchor update timestamp and proposal timestamp | exact ORB/day levels can be reconstructed; nearest support/resistance owner is absent |
| option-side evidence | option quote summary owner feeding `StrategyContext` | CE/PE instrument id, `option_ltp`, prior quote, `premium_change`, bid, ask, `spread_pct`, bid qty, ask qty, `depth`, quote source, fallback flag, age | quote exchange timestamp, receipt timestamp, proposal timestamp | not reconstructable without exact option quote join |
| candidate fingerprint | candidate/replay artifact owner | canonical candidate JSON, source session key, proposal timestamp, context hash, profile hash | candidate emission timestamp | unavailable until replay artifact exists |

## GSD Review

Future implementation specification:

- Storage location: append-only research/runtime evidence path chosen in a future approved PR; do not write into authoritative corpus roots in this docs PR.
- Deterministic hash: SHA-256 over canonical JSON with sorted keys and ASCII separators.
- Retention period: at least 60 trading sessions before exact replay certification.
- Expected daily size: bounded by context snapshots and candidate emissions; exact estimate must be measured in the implementation PR.
- Privacy/security concerns: no credentials, tokens, account ids, or broker order identifiers.
- Fail-closed behavior: if any exact field is absent, stale, fallback-only, or hash-mismatched, Compression replay status remains non-certifying.
- Minimum sessions before certification: 60 complete regular sessions with all required fields present and hash-verifiable.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

This plan is required because the Compression provenance matrix records absent candidate-critical truth; therefore the conditional Compression implementation gate is closed.

## Runtime Proof Required After Merge

A future PR must add instrumentation and tests proving point-in-time capture, immutable hashes, no future leakage, and fail-closed behavior for absent or fallback-only context.

## What This PR Does Not Prove

This PR does not certify Compression replay readiness, profitability, paper readiness, live readiness, execution readiness, option P&L, slippage, or broker correctness.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
