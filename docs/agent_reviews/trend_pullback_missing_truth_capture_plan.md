# Trend Pullback Absent-Truth Capture Plan

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Specify absent truth capture for Trend Pullback replay certification
- scope: Future implementation specification only; no production instrumentation is added in this PR.
- requested_paths: `docs/agent_reviews/trend_pullback_absent_truth_capture_plan.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check
- acceptance_proof: `TREND_MISSING_TRUTH_CAPTURE_PLAN_DEFINED`

## Scope Guard

This document is read-only planning. It does not modify runtime code, does not persist new live data, does not call brokers, and does not run full-corpus Trend replay.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: trend_pullback_absent_truth_capture_plan
- decision: TREND_MISSING_TRUTH_CAPTURE_PLAN_DEFINED
- reason: `TREND_INSUFFICIENT_REQUIRED_TRUTH` requires future capture of exact candidate-critical fields before exact replay certification.
- timestamp: 2026-07-19T02:52:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/trend_pullback_absent_truth_capture_plan.md

## Grill Me Review

Historical reconstruction is not enough for fields whose production owner is a runtime snapshot, live quote, or structure-anchor state not stored in the approved historical corpus. Any future implementation must fail closed when these fields are absent instead of silently substituting OHLC surrogates.

## Hermes Review

Absent or limited fields and required capture:

| Field Group | Runtime Owner To Instrument | Exact Fields To Persist | Required Timestamp | Historical Reconstruction |
|---|---|---|---|---|
| structure anchors | canonical `StrategyContext` construction owner after it is assigned | `nearest_support`, `nearest_resistance`, owner name, lookback/window, source bars, tie-break rule | proposal `ts_epoch`, anchor update timestamp, receipt timestamp | not reconstructable for exact production owner from current corpus |
| option-side evidence | option quote summary owner feeding `StrategyContext` | CE/PE instrument id, `option_ltp`, prior quote used for premium change, `premium_change`, bid, ask, `spread_pct`, bid qty, ask qty, `depth`, quote source, fallback flag, age | quote exchange timestamp, receipt timestamp, proposal timestamp | not reconstructable without exact quote join |
| runtime spot/VWAP | market snapshot/indicator owner | spot source type, spot value, candle/tick id, VWAP formula id, VWAP window, volume basis, fallback fields | source event timestamp and proposal timestamp | limited; underlying candles can surrogate but not certify runtime fallback state |
| regime scores | `MovementRegimeClassifier.classify` caller | full `MovementRegimeResult`, upstream context hash, classifier code hash | proposal timestamp | limited by upstream fields |
| candidate fingerprint | candidate/replay artifact owner | canonical candidate JSON, source session key, proposal timestamp, history hash, profile hash, setup identity | candidate emission timestamp | unavailable until replay artifact exists |

## GSD Review

Future implementation specification:

- Storage location: append-only research/runtime evidence path chosen in a future approved PR; do not write into authoritative corpus roots in this docs PR.
- Deterministic hash: SHA-256 over canonical JSON with sorted keys and ASCII separators.
- Retention period: at least 60 trading sessions before replay certification.
- Expected daily size: bounded by emitted candidate count and quote snapshot count; exact estimate must be measured in the implementation PR.
- Privacy/security concerns: no credentials, tokens, account ids, or broker order identifiers; instrument ids and market quotes only.
- Fail-closed behavior: if any exact field is absent, stale, fallback-only, or hash-mismatched, Trend replay status remains non-certifying.
- Minimum sessions before certification: 60 complete regular sessions with all required fields present and hash-verifiable.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

This plan is required because the Trend provenance matrix records absent candidate-critical truth.

## Runtime Proof Required After Merge

A future PR must add instrumentation and tests proving the captured event is point-in-time, immutable, hash-verifiable, and rejected when stale or incomplete.

## What This PR Does Not Prove

This PR does not certify historical Trend replay readiness, profitability, paper readiness, live readiness, execution readiness, option P&L, slippage, or broker correctness.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
