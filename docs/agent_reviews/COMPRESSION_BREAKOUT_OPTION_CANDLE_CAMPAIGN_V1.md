mode: RESEARCH_ONLY_OPTION_CANDLE_CAMPAIGN
candidate_id: compression_breakout_option_campaign_v1
decision: IMPLEMENTATION_READY_RUNTIME_DATA_REQUIRED
reason: The campaign calls the canonical Compression Breakout owner and now publishes an exhaustive all-strategy and hypothesis analytics queue, but real profit-factor rows still require Mac-local historical option data and completed causal adapters.
timestamp: 2026-07-26T20:50:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: strategies/movement/compression_breakout.py; research/option_e2e_recertification_v4/compression_breakout_option_campaign_v1/; research/option_e2e_recertification_v4/option_candle_backtest_v1/; research/option_e2e_recertification_v4/all_strategy_option_campaign_v1/

# Compression Breakout and All-Strategy Option Campaign V1

## Agent Work Contract

Implement the first strategy-specific historical CE/PE campaign after the
generic candle engine became available. Use `compression_breakout_v1`, the
highest-priority strategy with a concrete canonical candidate-generator owner.
Do not use the prior placeholder historical audit or replay scripts.

Extend that work with an exhaustive strategy and hypothesis universe so later
analytics cannot silently narrow to four familiar strategies.

## Scope Guard

Changed scope is limited to:

- `research/option_e2e_recertification_v4/compression_breakout_option_campaign_v1/`
- `research/option_e2e_recertification_v4/all_strategy_option_campaign_v1/`
- `scripts/run_compression_breakout_option_campaign.py`
- `scripts/run_all_strategy_option_universe.py`
- `scripts/run_all_strategy_option_analytics.py`
- `.github/workflows/compression-breakout-archive-smoke.yml`
- `.github/workflows/all-strategy-option-universe.yml`
- this review

No production strategy formula, profile threshold, broker, order, risk, feed,
candidate-pool runtime, dashboard, paper or live configuration is changed.

## Grill Me Review

The Compression campaign imports and calls
`generate_compression_breakout_candidates`; it does not reproduce the strategy
formula. Context features are constructed by session. The breakout bar is
separated from the pre-breakout 15-bar resistance, support and range-width
window. ATR values are taken from the preceding completed bar.

The signal ledger contains no option outcomes or P&L. It records the parameter
hash, raw strategy score, confidence score, strategy-only rank score, feature
cutoff and earliest-entry time. Execution-quality ownership remains unset.

Synthetic market fixtures are not accepted as campaign-performance proof by the
publication gate. Runtime campaign acceptance therefore remains explicitly
dependent on the Mac-local historical corpus and its emitted hash-bound evidence.

## All-Strategy Coverage Review

The exhaustive universe reconciles:

- 31 Python files under `strategies/`;
- 29 canonical registry entries;
- 16 authority strategy/hypothesis lanes;
- 10 explicit aliases;
- 33 historical entities and 18 historical strategies claimed by inventory v4.1.

It publishes 54 classified universe rows with zero hard gaps and one explicit
action per row. The analytics skeleton contains 27 relevant rows:

- 12 canonical CE/PE candle campaigns;
- 11 frozen research-hypothesis campaigns;
- 1 no-trade filter audit;
- 2 deferred aggregate or ensemble owners;
- 1 missing implementation blocker.

Ten aliases are collapsed into canonical runs, preventing duplicated trades and
profit factors. Helpers, registries and fixtures remain visible as explicit
non-strategy exclusions.

The canonical CE/PE queue is:

- COMPRESSION_BREAKOUT;
- EVENT_VOLATILITY_EXPANSION;
- EXHAUSTION_REVERSAL;
- FAILED_BREAKOUT_TRAP;
- LATE_DAY_MOMENTUM;
- MEAN_REVERSION_EXTENSION;
- OPENING_DRIVE;
- OPENING_RANGE_BREAKOUT;
- OPTION_PRESSURE;
- SIMPLE_ORB;
- TREND_PULLBACK;
- VWAP_RECLAIM.

The frozen research queue is:

- CONSTITUENT_BREADTH;
- CONSTITUENT_LEAD_LAG;
- CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY;
- FIVE_MINUTE_GOVERNED_DISCOVERY;
- ML_STRATEGY_DISCOVERY;
- OPENING_RANGE_RETEST;
- OPENING_STATE_MOMENTUM;
- RESIDUAL_MEAN_REVERSION;
- RSI2_MEAN_REVERSION;
- STRUCTURAL_PATTERN_SUITE;
- STRUCTURAL_STATE_DISCOVERY.

No strategy or hypothesis receives a profit factor unless it produces causal
CE/PE trades through the common protocol. Blocked and negative lanes remain in
the table with truthful reasons instead of disappearing.

## Hermes Review

The implementation follows the intended owner sequence:

```text
underlying completed bars
→ canonical pre-outcome strategy or frozen hypothesis signal
→ bullish CE / bearish PE research signal
→ deterministic contract selection
→ conservative option-candle economics
→ cost and control analytics
→ validation and later sealed holdout
```

Historical candle rank is explicitly strategy-only. Quote freshness, spread,
depth and exact fill authority remain outside this lane.

## Master Analytics Contract

The all-strategy master table includes:

- sessions, trades, wins, losses and win rate;
- gross P&L, total costs and net P&L;
- profit factor, expectancy and maximum drawdown;
- CE and PE trade counts and profit factors;
- 50-bps and 100-bps-per-side stressed profit factors;
- direction-flip and delayed-entry controls;
- validation and holdout profit factors;
- ranking eligibility and exact blocker reason.

A row may be ranked only after a completed campaign, minimum sample size,
validation PF above 1 and 50-bps-per-side PF above 1. Development-only PF,
headline win rate, aliases, filters, helpers, aggregates and blocked hypotheses
are never ranked as winners.

## GSD Review

The campaign provides one-command runners for:

- Compression signal and option-candle execution;
- exhaustive repository strategy/hypothesis classification;
- master analytics generation with optional completed-result JSON inputs.

The analytics skeleton is complete as a status artifact, not as a performance
claim. At the current implementation-only stage it reports zero completed
strategy results and zero ranking-eligible strategies.

## QA / Safety Review

The implementation contains fail-closed guards for:

- duplicate underlying timestamps;
- invalid OHLC geometry;
- missing pre-signal warmup;
- zero-volume VWAP proxy disclosure;
- optional rejection of VWAP proxy sessions;
- duplicate signal identities;
- chronological split overlap;
- supplied holdout option data;
- duplicate option contract timestamps;
- unknown completed-result strategy IDs;
- duplicate completed-result IDs;
- unclassified strategy files;
- uncovered historical identities;
- duplicate active strategy identities;
- incomplete repository-universe coverage.

Safety remains:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`
- `executable_option_pnl_certified=false`

## Acceptance Proof

Implementation publication requires:

- existing canonical Compression Breakout strategy tests;
- existing option-candle backtest tests;
- existing option-E2E tests;
- exhaustive all-strategy universe workflow;
- master analytics skeleton generation;
- Code Excellence;
- Agent Review Evidence Gate;
- CodeQL;
- strategy registry verification;
- repository CI.

Exact-head all-strategy evidence before this review consolidation:

- workflow run: `30207440509`;
- job: `exhaustive-universe`;
- conclusion: `success`;
- artifact ID: `8633474085`;
- artifact digest:
  `sha256:b41c708435749979730d2fd23f2afe0438c920bfb77eeee001136aa6e50043ee`;
- universe rows: 54;
- analytics rows: 27;
- hard gaps: 0;
- completed strategy results: 0;
- ranking-eligible strategies: 0.

Campaign-result publication additionally requires successful Mac-local runs,
portable artifact hashes, session counts, signal counts, rejection reasons,
contract-selection coverage, cost sensitivity and negative-control evidence.

## Runtime Proof Required After Merge

Run each eligible campaign on Mac-local historical underlying, session contract
catalogue and option OHLCV/LTP corpus. Development and validation runs must use
separate date-bound option inputs. Do not supply or open holdout option outcomes
until each campaign contract and its negative controls are frozen.

## What This PR Does Not Prove

This implementation does not prove that Compression Breakout or any other
strategy is profitable, that a 60% win rate exists, that option candles equal
bid/ask execution, or that paper/live trading is ready. It establishes a
complete, non-silent research queue and a common analytics destination.

## Human Approval

Human approval is not required for this read-only research implementation.
Human action is required only when the Mac-local corpus must be supplied or
executed and later before any holdout, paper or live promotion.
