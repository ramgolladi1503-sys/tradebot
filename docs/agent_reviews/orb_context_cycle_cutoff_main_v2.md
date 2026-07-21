# ORB Context Cycle Cutoff Main V2

## Scope

- Branch: `fix/orb-cycle-cutoff-main-v2`
- Base: `origin/main` at `a48176fc245375f15e316493364915ec37439e29`
- Worktree: `/Users/madhuram/tradebot-orb-cycle-cutoff-main-v2`
- Purpose: integrate the verified ORB runtime repair into current main without merging historical worktree history.

## Change

- Replaced the undefined ORB context timestamp argument `now_dt=now` with the frozen per-cycle `cycle_cutoff`.
- Removed unused local/import symbols in `core/market_data.py` so the required scoped `ruff` gate passes without weakening runtime behavior.

## Safety Boundaries

- Broker APIs called: `NO`
- Order actions placed/modified/cancelled: `NO`
- Runtime live configuration changed: `NO`
- Strategy thresholds changed: `NO`
- WFA, parameter search, or production strategy execution run: `NO`
- Audit worktree runtime files touched: `NO`
- Research data or runtime parquet artifacts staged: `NO`

## Evidence

- `pytest -q tests/core/test_orb_context_cycle_cutoff.py`: `1 passed`
- `pytest -q tests/core/test_canonical_strategy_input_truth.py`: `21 passed`
- `python3 -m py_compile core/market_data.py tests/core/test_orb_context_cycle_cutoff.py`: passed
- `ruff check core/market_data.py tests/core/test_orb_context_cycle_cutoff.py`: passed
- `git diff --check`: passed

## Regression Proof

`tests/core/test_orb_context_cycle_cutoff.py` verifies `fetch_live_market_data()` passes the exact frozen `cycle_cutoff` from `now_ist()` into `_orb_state_from_candles()` and that the returned ORB state propagates into the market-data row.
