# Compression Breakout Replay Preparation Boundary

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Define Compression Breakout replay preparation boundary
- scope: Read-only production-contract and corpus-suitability analysis for the next Compression Breakout causal replay implementation task.
- requested_paths: `docs/agent_reviews/compression_breakout_replay_preparation_boundary.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: agent-review evidence validation, scoped CE gate, diff check
- acceptance_proof: `COMPRESSION_BREAKOUT_REPLAY_PREP_BOUNDARY_DEFINED`

## Scope Guard

This is read-only preparation. It does not modify Compression production code, run Compression full-corpus replay, change shared replay architecture, touch runtime wiring, or mutate corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_REVIEW
- candidate_id: compression_breakout_replay_preparation_boundary
- decision: COMPRESSION_BREAKOUT_REPLAY_PREP_BOUNDARY_DEFINED
- reason: Compression Breakout requires exact point-in-time VWAP, ATR, range-width, regime-score, and anchor provenance before causal replay implementation can certify production-faithful behavior.
- timestamp: 2026-07-19T01:50:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/compression_breakout_replay_preparation_boundary.md

## Grill Me Review

Compression Breakout is snapshot-driven today. Its production generator consumes `spot_ltp`, `vwap`, `range_width_pct`, `atr_short`, `atr_long`, `regime.scores.COMPRESSION`, and directional anchors from `StrategyContext`; the strategy itself does not prove where those values came from or whether they are point-in-time causal.

## Hermes Review

Decision-critical inputs and next-task requirements:

| Input | Production Use | Required Replay Proof |
|---|---|---|
| `spot_ltp` | Breakout side and distance. | Exact causal underlying price at evaluation timestamp. |
| `vwap` | Required field and directional alignment gate. | Exact point-in-time VWAP through evaluation bar. |
| `range_width_pct` | Compression score component. | Exact causal range-width owner and window. |
| `atr_short` / `atr_long` | ATR compression ratio. | Exact causal ATR windows and warmup rules. |
| `regime.scores.COMPRESSION` | Compression score component and gate. | Exact historical `MovementRegimeResult` reconstruction. |
| `nearest_resistance` / `orb_high` / `day_high` | CALL anchor precedence. | Exact anchor owner, timestamp, and no future leakage. |
| `nearest_support` / `orb_low` / `day_low` | PUT anchor precedence. | Exact anchor owner, timestamp, and no future leakage. |
| Side evidence | Option premium, spread, depth. | Required for execution/P&L claims, not enough for signal-generation certification without underlying inputs. |

## GSD Review

Next causal-replay implementation task:

- Build a strategy-local Compression replay contract and oracle only after each input owner is mapped.
- Oracle must reject missing history, short history, cross-session history, duplicate or non-monotonic timestamps, incomplete bars, absent anchors, non-causal VWAP, and non-causal ATR/range windows.
- The first implementation should remain fixture/provenance only unless the replay manifest proves exact input ownership.
- Do not modify `strategies/movement/compression_breakout.py`.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Read-only findings:

- Production Compression code is read-only candidate generation.
- Required snapshot inputs are externally supplied through `StrategyContext`.
- Existing preparation commit `8dab1e9dc523f491138c894e3b671b6f53c3291d` is research/doc/test prep only and does not prove full-corpus replay readiness.
- No Compression full-corpus replay was run in this task.

## Runtime Proof Required After Merge

Before Compression replay certification, produce a manifest proving exact point-in-time VWAP, ATR, range-width, compression regime score, directional anchor, profile, and side-evidence provenance. If any are missing or proxy-limited, certification must remain fixture/proxy only.

## What This PR Does Not Prove

This PR does not prove Compression full-corpus replay readiness, structural trading edge, profitability, exact option P&L, execution fills, spread realization, latency behavior, slippage, paper readiness, live readiness, broker correctness, capital allocation readiness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
