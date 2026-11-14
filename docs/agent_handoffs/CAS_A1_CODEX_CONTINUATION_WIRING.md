# TradeBot CAS-A1 — Codex Continuation / Wiring Handoff

## Authority
Repository: `ramgolladi1503-sys/tradebot`
Analytics PR: `#790 — Analytics: add Aixion trade intelligence evidence kernel`
Verified branch at handoff creation: `agent/aixion-trade-intelligence-evidence-kernel-v1`
Verified exact head at handoff creation: `45bf2bc680b87b72cdf567f89fac6113719e64b9`
PR state: open, draft, unmerged.

Before execution, fetch the remote and report the current exact SHA. If the head changed, inspect and continue from the latest PR790 state. Do not reset history to this handoff SHA.

## Objective
Finish wiring the existing frozen CAS-A1 research/evidence architecture so that Codex can take over from repository state and complete the read-only source path:

`governed capture -> frozen 15:10/15:14 bars -> authoritative FINAL_CAS -> futures marks -> source bundle -> post-close evaluator -> PR790 canonical events -> immutable prospective result -> daily/cumulative analytics`

Do not restart CAS research, invent a new strategy, refit the formula, or weaken causal/data gates.

## Frozen CAS-A1 contract
Development sample: `2026-08-03` through `2026-08-14`, 10 CAS sessions.

```text
expected_CAS_adjustment_bps
= 15.5350561749
+ 2.9081599522 * equal_weight_constituent_return_1510_1514_bps

realized_CAS_adjustment_bps
= (NIFTY_final_CAS_index / NIFTY_1514_index - 1) * 10000

auction_surprise_bps
= realized_CAS_adjustment_bps - expected_CAS_adjustment_bps

surprise > 0  => predict NIFTY future UP
surprise < 0  => predict NIFTY future DOWN
surprise == 0 => NO_PREDICTION

frozen target = NIFTY futures 15:29 -> 15:39
```

No coefficient refit. No threshold/dead-band optimization. No feature additions/substitution. Any semantic change creates a new hypothesis/version and must not mutate CAS-A1.

Development observation: `9/10`, unadjusted exact randomization `p ~= 0.0238`.

This is selection-contaminated development evidence only:

```text
HISTORICAL_EDGE_SUPPORTED=false
OUT_OF_SAMPLE_SUPPORTED=false
EXECUTION_VIABLE=false
PROSPECTIVE_SUPPORTED=false
STRUCTURAL_EDGE_CERTIFIED=false
```

## Market replay already performed
The existing 10-session replay reproduced the frozen calculation:

```text
raw reproduction = 9/10
strict causally distinguishable sessions = 5/10
strict correct = 4/5
same-minute ordering unresolved = 5/10
```

Reason: on five sessions the first post-15:15 NIFTY change appears in 15:29, so minute data cannot prove whether FINAL_CAS became available before the futures 15:29 mark.

Controlled replay verdict: `CAS_A1_MARKET_REPLAY_PARTIAL`.

Do not interpret 4/5 as new OOS evidence; these are the same development sessions.

## Existing PR790 CAS surface
Inspect current branch before trusting this list. Expected files include:

```text
aixion_trade_intelligence/cas_a1.py
aixion_trade_intelligence/cas_a1_source_adapter.py
aixion_trade_intelligence/cas_a1_meg_source.py
aixion_trade_intelligence/cas_a1_capture_identity.py
aixion_trade_intelligence/cas_a1_tick_points.py
aixion_trade_intelligence/cas_a1_finalization_replay.py

scripts/finalize_cas_a1_intelligence_session.py
scripts/build_cas_a1_postclose_observation.py
scripts/build_cas_a1_meg_completed_bundle.py
scripts/build_cas_a1_capture_identity.py
scripts/build_cas_a1_futures_point_marks.py
scripts/assemble_cas_a1_source_bundle.py
scripts/run_cas_a1_postclose_daily.sh
scripts/replay_cas_a1_finalization_ticks.py

tests/test_aixion_cas_a1.py
tests/test_aixion_cas_a1_source_adapter.py
tests/test_aixion_cas_a1_meg_source.py
tests/test_aixion_cas_a1_capture_identity.py
tests/test_aixion_cas_a1_tick_points.py
tests/test_aixion_cas_a1_finalization_replay.py
```

CAS events remain PR790-native:

```text
CAS_A1_EXPECTATION_FROZEN
CAS_FINAL_PRICE_OBSERVED
CAS_A1_SURPRISE_OBSERVED
CAS_A1_PREDICTION_FROZEN
CAS_A1_OUTCOME_OBSERVED
CAS_A1_SESSION_BLOCKED
```

Prediction payload must never depend on outcome.

## Frozen constituent complication
The original development universe is a frozen 49-stock basket. Normalize `MANDM -> M&M`.

It includes `HEROMOTOCO` and `INDUSINDBK`.

The current governed NIFTY50 live universe instead includes current names such as `INDIGO`, `MAXHEALTH`, `TMPV`.

Therefore CAS-A1 must preserve:

```text
47 frozen names from current MEG universe
+ HEROMOTOCO supplemental read-only capture
+ INDUSINDBK supplemental read-only capture
= exact frozen 49
```

Do not silently substitute current NIFTY50 membership. Resolve exact supplemental Kite tokens from the actual broker instrument master. Do not hardcode or guess tokens.

## Completed-minute source already available
The read-only runtime already has:

```text
core/market_event_graph_live_ohlc_buffer.py
core/ohlc_buffer.py
core/market_event_graph_live_source.py
core/kite_read_only_observation_runtime.py
```

The CAS bridge must consume already-completed live 1-minute bars from governed evidence.

Required:

```text
each frozen constituent: 15:10 and 15:14 completed close
NIFTY index:             15:14 completed close
```

No tick approximation, forward fill, MISSING->ZERO, cross-session carry, or instrument substitution.

## Futures point extraction
The CAS tick-point extractor is intended to open the persisted tick DB read-only and bind exact first ticks within:

```text
15:29:00 <= tick < 15:30:00
15:39:00 <= tick < 15:40:00
```

Missing exact checkpoint => block. Exact NIFTY futures instrument/token must be bound for the session.

## Smallest unresolved blocker: FINAL_CAS semantics
Do NOT define FINAL_CAS as “whichever NIFTY tick happens around 15:29”.

Need repository/runtime evidence proving either:
1. an explicit exchange/broker final-CAS field/event; or
2. a deterministic source rule independently verified to represent official final CAS publication.

Allowed findings:

```text
FINAL_CAS_PRIMITIVE_VERIFIED
FINAL_CAS_PRIMITIVE_PROXY_ONLY
FINAL_CAS_PRIMITIVE_BLOCKED
```

If semantics remain unproven, prospective scoring must fail closed.

## Aug-3 sub-minute replay
Local runtime evidence from prior work may exist at:

`.runtime/research/cas_h3b0_aug03_raw/ticks_*.parquet`

Known option keys:
`24600 CE = NSE_FO|65871`
`24600 PE = NSE_FO|65872`

Known raw fields include:
`ts,instrument_key,ltp,bid_price,ask_price,delta,theta,gamma,vega,iv,volume,oi`.

Use `scripts/replay_cas_a1_finalization_ticks.py` to identify the candidate index discontinuity and exact ordering. Label it `REPLAY_PROXY_FROM_INDEX_DISCONTINUITY`, never `FINAL_CAS_VERIFIED` unless separately proven.

First inventory all `instrument_key` values in the raw files. Do not guess the NIFTY futures key. If present, bind exact key and include it. If absent, record futures tick evidence unavailable.

Output must include input paths, SHA-256s, row counts, exact candidate timestamp, pre/post index values, first final-index value timestamp, first CE/PE quote after event, futures first post-event tick if available, and controlled verdict.

## Workspace safety
The user's `/Users/madhuram/tradebot` workspace was observed to contain a large amount of modified/untracked work. A checkout already failed because Git correctly protected it.

Do not run:

```text
git reset --hard
git clean -fd
git stash -u
force checkout
delete unknown worktrees
overwrite runtime evidence
```

First run:

```bash
git worktree list --porcelain
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin
git rev-parse origin/agent/aixion-trade-intelligence-evidence-kernel-v1
```

Reuse an existing safe clean PR790 worktree if present. Otherwise inspect before creating any isolated exact-SHA replay worktree. Prior suggested path was `/Users/madhuram/tradebot-cas-a1-replay`; verify it does not already exist.

Runtime evidence should be referenced/symlinked. Do not move or delete originals.

## Codex execution sequence
1. Perform repository/worktree archaeology and choose a safe exact authority.
2. Inspect all current CAS files and branch drift.
3. Run:
```bash
python -m compileall -q aixion_trade_intelligence scripts tests
PYTHONPATH=. pytest -q -o addopts='' \
  tests/test_aixion_cas_a1.py \
  tests/test_aixion_cas_a1_source_adapter.py \
  tests/test_aixion_cas_a1_meg_source.py \
  tests/test_aixion_cas_a1_capture_identity.py \
  tests/test_aixion_cas_a1_tick_points.py \
  tests/test_aixion_cas_a1_finalization_replay.py
PYTHONPATH=. pytest -q -o addopts='' tests/test_aixion_*.py
```
4. Locate local CAS runtime evidence: `cas_h3b0_aug03_raw`, `cas_2week_raw`, `cas_panel_v1`, `captured_metadata.jsonl`, tick DB, futures identity evidence.
5. Execute the Aug-3 sub-minute replay if inputs exist. Hash all inputs.
6. Resolve exact HEROMOTOCO/INDUSINDBK tokens through actual Kite instrument master. Test generated capture identity. No hardcoding.
7. Determine whether supplemental capture-only tokens can be wired to the read-only evidence observer without affecting strategy universe, candidate generation, ranking, risk, execution, or production market-data owners.
8. Attack FINAL_CAS semantics from Kite/NSE payloads, exchange timestamps, runtime logs, and code.
9. Wire the 15:50 post-close chain only if required primitives are proven. If FINAL_CAS remains unproven, keep automation fail-closed.

## Preferred supplemental capture architecture
Capture-only subscription owned by the read-only evidence lane. It must not propagate supplemental symbols into strategy-facing state.

If isolation requires modifying protected production code, stop and report the smallest exact change rather than implementing it automatically.

## Safety contract
Always preserve:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```

No orders, paper fills, execution authority, strategy/ranking/risk changes.

## Allowed modification scope
Prefer:

```text
aixion_trade_intelligence/**
scripts/*cas_a1*
tests/test_aixion_cas_a1*
docs/runbooks/aixion_trade_intelligence_cas_a1*
docs/agent_handoffs/**
research/cas_closing_auction_shadow_v1/**
```

Inspect production/read-only feed code as needed, but protected/no-touch by default:

```text
core/orchestrator*
core/market_data*
core/kite_depth_ws*
core/feed/**
core/broker*
core/order*
core/risk*
core/execution*
strategies/**
dashboard/**
config/**
run_live.sh
```

If a protected edit is genuinely required, stop and report the minimal blocker.

## Research governance
Do not optimize CAS-A1 further. Prior search already included pre-CAS cash pressure, early futures, expiry, option convergence, incremental model, phase splits, cross-market confirmation, equal/weighted breadth, auction gap, auction surprise, and timing reframing. Fresh future sessions are required for prospective evidence.

## Required final Codex verdict
Return exactly one implementation verdict:

```text
CAS_A1_CODEX_WIRING_IMPLEMENTATION_VALID
CAS_A1_CODEX_WIRING_REPAIR_REQUIRED
CAS_A1_CODEX_WIRING_BLOCKED
CAS_A1_CODEX_WIRING_INVALID
```

Then separately:

```text
FINAL_CAS_PRIMITIVE_VERIFIED=<true|false>
FROZEN_49_CAPTURE_VERIFIED=<true|false>
POSTCLOSE_AUTOMATION_READY=<true|false>
PROSPECTIVE_SUPPORTED=false
EXECUTION_VIABLE=false
STRUCTURAL_EDGE_CERTIFIED=false
```

Final response must include exact starting/final SHA, worktree, dirty status before/after, evidence paths and hashes, tests and counts, replay outputs, FINAL_CAS finding, supplemental constituent identity result, files changed, protected-surface status, CI state, blockers/unknowns, controlled verdict, and `no merge`.

Repository artifacts and reproducible evidence outrank this handoff if they conflict.
