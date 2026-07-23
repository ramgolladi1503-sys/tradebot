# Trend Pullback Replay Provenance Closure

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Classify Trend Pullback replay provenance
- scope: Replace the prior boundary note with owner-backed provenance classification for exact-context replay readiness.
- requested_paths: `docs/agent_reviews/trend_pullback_replay_provenance_boundary.md`, `docs/agent_reviews/trend_pullback_input_provenance_v1.json`, `docs/agent_reviews/trend_pullback_input_provenance_v1.json.sha256`, `docs/agent_reviews/trend_pullback_absent_truth_capture_plan.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check, JSON sidecar verification
- acceptance_proof: `TREND_INSUFFICIENT_REQUIRED_TRUTH`

## Scope Guard

This is documentation and bounded JSON evidence only. It does not modify production strategy code, change runtime context construction, mutate corpus roots, run Trend full-corpus replay, call brokers, or claim execution readiness.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: trend_pullback_input_provenance_v1
- decision: TREND_INSUFFICIENT_REQUIRED_TRUTH
- reason: Candidate-critical option-side truth and production runtime structure-anchor ownership are absent or surrogate-only in the approved historical corpus, so exact production-context replay is not certifiable.
- timestamp: 2026-07-19T02:52:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/trend_pullback_input_provenance_v1.json

## Grill Me Review

The prior verdict `TREND_PULLBACK_REPLAY_PROVENANCE_BOUNDARY_DEFINED` is not a final Strategy Truth verdict and is superseded. Exact replay cannot be certified by reusing fixture assumptions because production `generate_trend_pullback_candidates` now requires a validated four-bar temporal context, support/resistance anchors, profile resolution, movement-regime scores, and option-side evidence. The approved underlying-candle corpus can reconstruct some underlying fields, but it does not provide exact option LTP, premium change, spread, depth, or the canonical runtime owner for support/resistance anchors.

## Hermes Review

Primary owner paths inspected:

- `strategies/movement/trend_pullback.py`: production callable, temporal contract, setup identity, price-structure score, candidate evidence.
- `core/movement_contract.py`: `StrategyContext` field contract.
- `core/session_bar_history.py`: completed-history state builder, cutoff, duplicate/order handling, history hash.
- `core/movement_regime.py`: `TREND_UP` and `TREND_DOWN` score construction from context inputs.
- `core/strategy_parameter_profiles.py`: requested/resolved profile identity and parameter hash.
- `strategies/movement/_utils.py`: side evidence, score composition, lineage payload.
- `core/runtime_snapshot_producer.py`: runtime snapshot-to-`StrategyContext` adapter.
- `core/orb_ohlcv_validation.py` and `scripts/backtest_all_strategies_available_data.py`: research/offline context construction paths.

Corpus evidence inspected:

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`: 2341 non-`.DS_Store` files, underlying 1-minute parquet samples include `timestamp`, `symbol`, `open`, `high`, `low`, `close`, `volume`, `oi`, provider/fetch metadata. Sample row count observed: 375 rows per full session file. Volume for index underlying samples is zero, so volume-based exact VWAP is not available from this root.
- `/Users/madhuram/tradebot/.runtime/market_data`: 65 files, tick parquet samples include `ts`, `token`, `symbol`, `ltp`, `bid`, `ask`, `vol`, `oi`. This root is live-capture style data, not a frozen session-complete candidate universe with deterministic per-candidate option-side joins.

## GSD Review

Final Trend verdict: `TREND_INSUFFICIENT_REQUIRED_TRUTH`.

Compression/Trend provenance work continues as documentation and capture-specification work only. Trend full-corpus replay remains prohibited until absent option-side and anchor provenance are captured or a reviewed replay contract explicitly downgrades the lane to non-certifying surrogate mode.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Machine-readable matrix: `docs/agent_reviews/trend_pullback_input_provenance_v1.json`.

Hash sidecar: `docs/agent_reviews/trend_pullback_input_provenance_v1.json.sha256`.

Absent-truth plan: `docs/agent_reviews/trend_pullback_absent_truth_capture_plan.md`.

The matrix contains one row for every required field in the stage contract and uses only the approved classifications:

- `EXACT_STORED_TRUTH`
- `EXACT_OWNER_RECONSTRUCTABLE`
- `PROVENANCE_LIMITED_PROXY`
- `MISSING_REQUIRED_TRUTH`

## Runtime Proof Required After Merge

Before any exact Trend replay claim, persist per-candidate production context provenance for support/resistance anchors, option-side evidence, profile identity, completed-history hash, regime inputs and scores, candidate fingerprint inputs, and replay record identifiers. Historical reconstruction is not reconstructable for the absent option-side and runtime-anchor fields unless a frozen artifact already contains the exact as-of values.

## What This PR Does Not Prove

This PR does not certify Trend full-corpus replay readiness, structural edge, profitability, exact option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
