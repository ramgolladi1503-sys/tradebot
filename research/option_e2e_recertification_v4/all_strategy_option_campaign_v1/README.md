# All-Strategy Option Campaign V1

This package prevents TradeBot's historical CE/PE analytics from silently
narrowing to a small hand-picked strategy list.

## What is inventoried

The universe builder reconciles:

- every Python file under `strategies/`;
- the canonical strategy registry;
- the alias graph;
- the historical strategy inventory;
- the merged authority-priority strategy and hypothesis lanes;
- frozen-hypothesis evidence files.

Every discovered item receives one explicit action:

```text
RUN_CE_PE_CANDLE_CAMPAIGN
RUN_IF_FROZEN_SIGNAL_ADAPTER_EXISTS
RUN_NO_TRADE_FILTER_AUDIT
DEFER_UNTIL_CHILD_CAMPAIGNS_COMPLETE
BLOCK_MISSING_IMPLEMENTATION
COLLAPSE_INTO_CANONICAL_RUN
EXCLUDE_SUPPORT_ENTITY
BLOCK_PENDING_CLASSIFICATION
```

The workflow fails when an active strategy file, historical identity or authority
lane has no classification.

## Current queue

### Canonical CE/PE campaigns

```text
COMPRESSION_BREAKOUT
EVENT_VOLATILITY_EXPANSION
EXHAUSTION_REVERSAL
FAILED_BREAKOUT_TRAP
LATE_DAY_MOMENTUM
MEAN_REVERSION_EXTENSION
OPENING_DRIVE
OPENING_RANGE_BREAKOUT
OPTION_PRESSURE
SIMPLE_ORB
TREND_PULLBACK
VWAP_RECLAIM
```

### Frozen research-hypothesis campaigns

```text
CONSTITUENT_BREADTH
CONSTITUENT_LEAD_LAG
CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY
FIVE_MINUTE_GOVERNED_DISCOVERY
ML_STRATEGY_DISCOVERY
OPENING_RANGE_RETEST
OPENING_STATE_MOMENTUM
RESIDUAL_MEAN_REVERSION
RSI2_MEAN_REVERSION
STRUCTURAL_PATTERN_SUITE
STRUCTURAL_STATE_DISCOVERY
```

### Special rows

- `NO_TRADE_CHOP` receives filter/rejection analytics rather than ordinary PF ranking.
- `ENSEMBLE` and `PRO_STRATEGY_ENGINE` run after child strategies have comparable results.
- `HTF_OPENING_DRIVE_CONT` remains blocked until its declared implementation exists.
- aliases collapse into canonical rows and are never double-counted.
- helper modules, registries and fixtures remain inventoried but unranked.

## Master analytics

The analytics output contains one row for every relevant strategy or hypothesis,
including blocked and deferred rows. Completed campaigns populate:

```text
sessions
trades
wins / losses / win rate
gross P&L / costs / net P&L
profit factor
expectancy
maximum drawdown
CE and PE trade counts and PF
50-bps and 100-bps stressed PF
direction-flip and delayed-entry PF
validation and holdout PF
ranking eligibility
```

A strategy is ranking-eligible only when its campaign is completed, its frozen
minimum trade count is met, validation PF is above 1, and PF remains above 1 at
50 bps adverse slippage per side.

## Commands

Build only the exhaustive universe:

```bash
PYTHONPATH=. python scripts/run_all_strategy_option_universe.py \
  --repo-root . \
  --output-dir /tmp/all-strategy-universe
```

Build the universe plus master analytics skeleton:

```bash
PYTHONPATH=. python scripts/run_all_strategy_option_analytics.py \
  --repo-root . \
  --output-dir /tmp/all-strategy-analytics \
  --require-complete-universe
```

Completed campaign result files can be added later with repeated
`--result-json /path/to/result.json` arguments.

## Evidence boundary

The current analytics skeleton contains statuses, not fabricated performance.
Real PF, expectancy and drawdown require causal adapters and usable historical
option OHLCV or positive LTP data. Bid/ask certification remains a separate
forward execution gate.

This package is research-only, read-only and cannot place orders.
