# Compression Breakout Replay Provenance Closure

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Classify Compression Breakout replay provenance
- scope: Replace the prior preparation note with owner-backed provenance classification and conditional replay gate decision.
- requested_paths: `docs/agent_reviews/compression_breakout_replay_preparation_boundary.md`, `docs/agent_reviews/compression_breakout_input_provenance_v1.json`, `docs/agent_reviews/compression_breakout_input_provenance_v1.json.sha256`, `docs/agent_reviews/compression_breakout_absent_truth_capture_plan.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check, JSON sidecar verification
- acceptance_proof: `COMPRESSION_INSUFFICIENT_REQUIRED_TRUTH`

## Scope Guard

This is documentation and bounded JSON evidence only. It does not modify production Compression code, run Compression full-corpus replay, change shared replay architecture, touch runtime wiring, or mutate corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: compression_breakout_input_provenance_v1
- decision: COMPRESSION_INSUFFICIENT_REQUIRED_TRUTH
- reason: Compression candidate presence and score require exact VWAP, ATR, range-width, regime, directional-anchor, and option-side evidence; approved corpus inspection proves underlying OHLCV availability but not exact option-side truth or canonical runtime anchor/ATR/VWAP ownership for every candidate.
- timestamp: 2026-07-19T02:52:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/compression_breakout_input_provenance_v1.json

## Grill Me Review

The prior decision `COMPRESSION_BREAKOUT_REPLAY_PREP_BOUNDARY_DEFINED` is superseded. Compression Breakout is not cleared for causal replay implementation because the exact-context gate did not pass. Research/offline code can derive range width and ATR surrogates from candles, but the production callable consumes `StrategyContext` values. The inspected approved roots do not certify exact as-of option-side joins, canonical runtime support/resistance owner state, or exact runtime VWAP/ATR/range provenance per candidate.

## Hermes Review

Primary owner paths inspected:

- `strategies/movement/compression_breakout.py`: production callable, compression score, breakout levels, candidate evidence.
- `core/movement_contract.py`: `StrategyContext` field contract.
- `core/movement_regime.py`: `COMPRESSION` score construction.
- `core/session_bar_history.py`: range-width helper and completed-history constraints.
- `core/indicators_live.py`: live indicator VWAP/ATR owner.
- `core/strategy_parameter_profiles.py`: requested/resolved profile identity and parameter hash.
- `strategies/movement/_utils.py`: side evidence, score composition, lineage payload.
- `core/runtime_snapshot_producer.py`: runtime snapshot-to-`StrategyContext` adapter.
- `core/orb_ohlcv_validation.py` and `scripts/backtest_all_strategies_available_data.py`: research/offline surrogate construction paths.

Corpus evidence inspected:

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`: 2341 non-`.DS_Store` files; underlying 1-minute parquet schema supports OHLC timestamp reconstruction but index volume is zero in inspected samples, making exact volume VWAP unavailable.
- `/Users/madhuram/tradebot/.runtime/market_data`: 65 files; tick parquet schema has quote/tick columns, but no frozen deterministic candidate-level option-side join manifest was found in this task.

## GSD Review

Final Compression verdict: `COMPRESSION_INSUFFICIENT_REQUIRED_TRUTH`.

Conditional implementation gate: closed. Do not create or run `/Users/madhuram/tradebot-compression-breakout-causal-replay` until an independent reviewer can accept `COMPRESSION_EXACT_CONTEXT_REPLAYABLE`.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Machine-readable matrix: `docs/agent_reviews/compression_breakout_input_provenance_v1.json`.

Hash sidecar: `docs/agent_reviews/compression_breakout_input_provenance_v1.json.sha256`.

Absent-truth plan: `docs/agent_reviews/compression_breakout_absent_truth_capture_plan.md`.

The Compression matrix uses only the approved provenance classifications and records the gate reason for blocking implementation.

## Runtime Proof Required After Merge

Before Compression replay certification, persist exact point-in-time VWAP, ATR short/long, range-width, `COMPRESSION` regime-score inputs, directional anchor provenance, profile identity, option-side evidence, candidate fingerprint inputs, and replay record identifiers. Absent or surrogate-limited fields keep the lane non-certifying.

## What This PR Does Not Prove

This PR does not certify Compression full-corpus replay readiness, structural edge, profitability, exact option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
