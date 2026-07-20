# Three-Year Structural Edge Discovery Blocker

Verdict: `BLOCKED_INSUFFICIENT_HISTORICAL_DATA`

Base `origin/main`: `a48176fc245375f15e316493364915ec37439e29`
Worktree HEAD: `a48176fc245375f15e316493364915ec37439e29`
Worktree: `/Users/madhuram/tradebot-structural-edge-treasure-hunt-3y`

## Data Gate

Required: latest complete trading session back through the preceding 36 calendar months.

Available canonical replay root inspected read-only: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`

Observed coverage: `20240530` through `20260716` (777 calendar days), 526 session folders. This is less than the required approximate 1095-day / 36-month horizon.

Files: 1676 parquet files, 1550 underlying-like OHLCV files, 126 option-named OHLC files. The option-named files do not establish bid/ask top-of-book certification data.

## Trusted Replay Authority

Current repo evidence keeps strict option replay in `core/option_backtest/engine.py` and `core/option_backtest/wfa.py`. Legacy/vectorized paths remain proxy or non-certifying.

## Safety Flags

- read_only=true
- is_order_action=false
- broker_api_called=false
- execution_eligibility=false
- allowed_for_live_execution=false
- append=false

## Decision

No hypotheses were generated, screened, or validated. Opening discovery/screen/holdout partitions on a sub-three-year corpus would violate the task contract and risk fake research progress.
