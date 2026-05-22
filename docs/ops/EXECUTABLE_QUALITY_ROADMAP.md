# Executable Quality Roadmap

This roadmap is the ordered TODO list for fixing Tradebot's executable trade quality before adding more strategy complexity.

Current constraint for EDGE-31: market is closed, so this PR proves deterministic guard behavior only. No live feed validation is claimed here.

## Non-negotiable rule

Do not add new strategies, broker live placement, ML ranker changes, dashboard redesign, auto-tuning, or capital allocator expansion until executable truth is locked.

## Roadmap

### EDGE-31 — Executable Trade Truth Firebreak

Goal: make fallback, recovered, synthetic, stale, degraded, planning, advisory, debug, and low-confidence data impossible to treat as executable.

Acceptance proof:
- Fallback candidate cannot pass execution quality.
- Recovered fallback candidate cannot pass execution quality.
- Degraded advisory data cannot pass execution quality even in PAPER/SIM.
- Stale quote cannot pass execution quality.
- Missing or unverified spread cannot pass execution quality.
- Clean fresh candidate remains allowed by the pure truth classifier.

### EDGE-32 — Candidate Quote Freshness Contract

Goal: every executable candidate must carry per-candidate freshness proof, not just broad feed health.

Required candidate fields:
- ltp_age_sec
- bid_age_sec
- ask_age_sec
- quote_age_sec
- chain_snapshot_age_sec
- option_token
- last_option_tick_epoch
- option_feed_block_reason

### EDGE-33 — Option Bid/Ask and Spread Truth Gate

Goal: make LTP-only option trades impossible.

Required checks:
- bid > 0
- ask > 0
- ask >= bid
- spread_pct <= MAX_SPREAD_PCT
- quote_completeness == FULL
- spread_source is not fallback

### EDGE-34 — Execution-First Scoring Reweight

Goal: make execution quality dominate executable selection.

Execution priority should favor:
- execution_quality_score
- data_confidence
- freshness_quality
- liquidity_quality
- spread_quality
- signal_score only after execution truth passes

### EDGE-35 — Strategy Signal Quality Contract

Goal: force every strategy candidate to expose setup, trigger, regime, entry quality, invalidation distance, and reason-for/against entry evidence.

### EDGE-36 — Feed Staleness Recovery Evidence

Goal: prove stale feed handling deterministically, including connected websocket with stale option ticks and failed recovery after resubscribe.

### EDGE-37 — Executable Trade Quality Report

Goal: produce runtime/reports/executable_trade_quality_latest.json with real executable counts, blockers, fallback contamination, stale quote counts, and selected trade quality breakdown.

### EDGE-38 — UI Split by Trade Truth

Goal: split dashboard rows into Real Executable, Near Executable, Advisory/Watchlist, and Blocked/Debug.

### EDGE-39 — Paper Outcome Journal

Goal: record outcome truth for every executable candidate: decision quote, entry, spread, slippage estimate, MFE, MAE, PnL, result, and strategy family.

### EDGE-40 — Strategy Expectancy Review Gate

Goal: disable, demote, or restrict strategies with negative expectancy after enough paper samples.
