# Real Opportunity Engine Bible

## Status

This document is the implementation scope for turning Tradebot from a signal/output viewer into a real opportunity engine.

It starts after:

- PR #55 — Ranking/opportunity-engine diagnostics
- PR #56 — Opportunity diagnostics evidence capture

Those PRs made the problem measurable. This document defines the build direction.

## Brutal premise

More strategies alone will not fix the bot.

A bot with ten noisy strategies is worse than a bot with three honest strategies.

The goal is not to create more rows. The goal is to create fewer, better, explainable, rankable opportunities.

## Target outcome

Tradebot should move from this:

```text
Strategy emits row
Dashboard displays row
Executable toggle filters row
User guesses whether it is real
```

To this:

```text
Market state is classified
Multiple movement strategies generate candidates
Candidates are confirmed against option premium, liquidity, freshness, and blockers
Candidate pool ranks opportunities
UI separates ranked opportunities from raw/debug/advisory rows
Execution gate only sees validated executable truth
```

## Non-goals

The opportunity engine must not:

- loosen execution gates to create trades;
- treat fallback quotes as executable truth;
- hide stale option LTP;
- bypass contract resolution;
- call broker/order APIs from strategy code;
- directly mutate depth subscriptions;
- add random indicator wrappers without movement rationale;
- introduce ML ranking before deterministic ranking works;
- turn dashboard rows into trades without candidate validation.

## Architecture

```text
MarketSnapshot
  -> MovementRegimeClassifier
  -> MovementStrategyRegistry
  -> StrategyCandidate[]
  -> OptionConfirmationLayer
  -> LiquidityFreshnessBlockerLayer
  -> CandidatePool
  -> OpportunityRanker
  -> Dashboard / Evidence / Execution Gate
```

## Key design rule

Every strategy returns a candidate, not a trade.

A candidate can become:

```text
RAW_CANDIDATE
VALIDATED_CANDIDATE
BLOCKED_CANDIDATE
RANKED_OPPORTUNITY
NO_TRADE
```

Only later layers decide whether the candidate is executable, queue-only, advisory-only, or no-trade.

## Candidate contract

Add a common candidate object before adding new strategies.

Suggested module:

```text
core/movement_contract.py
```

Suggested fields:

```text
schema_version
strategy_id
movement_type
symbol
direction
status
raw_score
confidence_score
price_structure_score
option_confirmation_score
liquidity_score
freshness_score
volatility_score
regime_alignment_score
entry_trigger
invalid_if
rank_reason
blockers
warnings
evidence
```

### Direction values

```text
BUY_CALL
BUY_PUT
NO_TRADE
```

### Status values

```text
RAW_CANDIDATE
VALIDATED_CANDIDATE
BLOCKED_CANDIDATE
RANKED_OPPORTUNITY
NO_TRADE
```

## Strategy context contract

Strategies should not receive random loose dictionaries forever. Use a shared context.

Suggested fields:

```text
symbol
ts_epoch
spot_ltp
vwap
day_high
day_low
orb_high
orb_low
prev_day_high
prev_day_low
atr
atr_short
atr_long
range_width_pct
volume_z
volatility_state
regime_hint
option_ce_ltp
option_pe_ltp
ce_premium_change
pe_premium_change
ce_spread_pct
pe_spread_pct
ce_depth
pe_depth
option_ltp_age_sec
quote_source
time_of_day
minutes_since_open
minutes_to_close
expiry_context
```

Missing fields must not crash strategies. Missing required evidence should create blockers or warnings.

## Movement regime classifier

The regime classifier should output probabilities or scores, not just one label.

Suggested states:

```text
TREND_UP
TREND_DOWN
RANGE
CHOP
COMPRESSION
VOLATILITY_EXPANSION
TRAP_RISK
EXHAUSTION_RISK
EXPIRY_CONTEXT
```

Example output:

```json
{
  "primary_regime": "COMPRESSION",
  "scores": {
    "TREND_UP": 0.22,
    "RANGE": 0.51,
    "COMPRESSION": 0.74,
    "VOLATILITY_EXPANSION": 0.33,
    "TRAP_RISK": 0.18
  },
  "warnings": []
}
```

Reason: real markets are mixed. A single hard regime label is too crude.

## Strategy pack

The target is 10+ movement strategies. These are movement archetypes, not random indicators.

### 1. Opening Drive

Purpose: capture strong directional movement immediately after open.

Activates when:

- first 5 to 20 minutes;
- spot expands away from open;
- VWAP supports direction;
- option premium confirms;
- spread and freshness are sane.

Rejects when:

- option LTP is stale;
- quote source is fallback only;
- spread is wide;
- move is already too stretched;
- premium does not confirm.

Example candidates:

```text
NIFTY breaks opening high + CE premium expands -> BUY_CALL
BANKNIFTY breaks opening low + PE premium expands -> BUY_PUT
```

### 2. Opening Range Breakout Retest

Purpose: avoid chasing the first breakout; enter after retest confirms.

Activates when:

- ORB high/low breaks;
- price retests breakout level;
- level holds;
- option premium resumes expansion.

Rejects when:

- price returns inside range;
- retest lacks premium confirmation;
- breakout is into obvious support/resistance.

### 3. Compression Breakout

Purpose: catch expansion after quiet compression.

Activates when:

- tight range for 20 to 45 minutes;
- ATR/range contraction;
- price near VWAP or range midpoint;
- breakout comes with volume and option premium expansion.

Rejects when:

- breakout lacks option premium;
- spread widens during breakout;
- option quote is stale;
- breakout occurs in dead volume.

### 4. Trend Pullback Continuation

Purpose: join a trend after pullback instead of chasing the initial move.

Activates when:

- trend is established;
- pullback holds VWAP/EMA/structure;
- premium resumes in trend direction;
- invalidation level is clear.

Rejects when:

- pullback breaks structure;
- option premium does not recover;
- trap risk rises.

### 5. VWAP Reclaim / VWAP Rejection

Purpose: trade reclaim/rejection around VWAP, not just price above/below VWAP.

Activates when:

- price loses and reclaims VWAP with force; or
- price tests VWAP and rejects;
- option premium confirms direction;
- VWAP behavior is not choppy.

Rejects when:

- price crosses VWAP repeatedly;
- premium is flat;
- VWAP slope/context is unclear.

### 6. Failed Breakout / Trap

Purpose: detect bull traps and bear traps.

Activates when:

- price breaks ORB/day high/low;
- fails to hold;
- returns inside range;
- opposite premium starts expanding.

Rejects when:

- opposite premium does not confirm;
- re-entry is weak;
- quote quality is bad.

This strategy can also suppress opposite breakout candidates.

### 7. Exhaustion Reversal

Purpose: catch stretched moves losing power.

Activates when:

- price is far from VWAP/range mean;
- trend-side premium stops expanding;
- momentum slows;
- reversal structure appears.

Rejects when:

- trend is still accelerating;
- premium still expands in trend direction;
- reversal lacks structure.

### 8. Mean Reversion Extension

Purpose: trade extreme deviation back toward mean in range conditions.

Activates when:

- range/chop regime dominates;
- price extends beyond range/VWAP band;
- continuation premium weakens;
- reversal evidence appears.

Rejects when:

- volatility expansion supports breakout;
- trend regime dominates;
- option premium continues expanding away from mean.

### 9. Event / Volatility Expansion

Purpose: capture sudden large moves caused by volatility expansion.

Activates when:

- ATR/candle range expands quickly;
- option premium expands fast;
- volume/velocity confirms;
- spread remains sane.

Rejects when:

- spread explodes;
- quote freshness is bad;
- move is late/exhausted;
- fallback data is involved.

### 10. Option Pressure Confirmation

Purpose: confirm whether options agree with spot direction.

This can be a strategy and a confirmation layer.

Promotes when:

- spot bullish + CE premium rising + PE premium weakening + CE spread tight;
- spot bearish + PE premium rising + CE premium weakening + PE spread tight.

Demotes when:

- spot moves but option premium does not;
- spread is too wide;
- depth is poor;
- quote is stale;
- quote source is fallback only.

### 11. Late-Day Momentum

Purpose: capture final-session directional movement.

Activates when:

- after afternoon consolidation;
- clear break occurs late day;
- premium still expands;
- expiry decay does not dominate.

Rejects when:

- premium is dead;
- spread widens;
- market is choppy;
- move is too late to enter safely.

### 12. No-Trade Chop Detector

Purpose: block bad trading environments.

This is not optional.

Activates when:

- price crosses VWAP repeatedly;
- breakouts fail repeatedly;
- range is too narrow;
- option premiums decay;
- spreads are wide;
- no volatility expansion exists.

Output:

```text
NO_TRADE_CHOP
NO_TRADE_LIQUIDITY
NO_TRADE_STALE_FEED
```

## Candidate blockers

### Hard blockers

Hard blockers prevent executable status.

```text
STALE_OPTION_LTP
WIDE_SPREAD
MISSING_DEPTH
FALLBACK_QUOTE_ONLY
UNRESOLVED_CONTRACT
CONFLICTING_TRAP_SIGNAL
NO_TRADE_CHOP
BROKER_UNAVAILABLE
MARKET_CLOSED
```

### Soft blockers

Soft blockers reduce rank.

```text
BIAS_CONFLICT
LATE_ENTRY
NEAR_RESISTANCE
NEAR_SUPPORT
LOW_VOLUME_CONFIRMATION
WEAK_OPTION_CONFIRMATION
LOW_VOLATILITY
MIXED_REGIME
```

## Candidate pool

Suggested module:

```text
core/candidate_pool.py
```

Responsibilities:

- run active strategies;
- collect candidates;
- normalize candidate fields;
- deduplicate candidates by symbol/direction/setup;
- apply hard and soft blockers;
- preserve raw evidence;
- output candidate pool summary.

Candidate pool must not call broker/order APIs.

## Ranking engine v1

Suggested module:

```text
core/opportunity_ranker.py
```

Start deterministic. Do not add ML yet.

Suggested formula:

```text
rank_score =
  0.25 * price_structure_score
+ 0.25 * option_confirmation_score
+ 0.20 * liquidity_score
+ 0.15 * freshness_score
+ 0.10 * volatility_score
+ 0.05 * regime_alignment_score
- blocker_penalties
```

Rules:

- fallback quote cannot become executable truth;
- stale option LTP cannot be executable;
- wide spread cannot be executable;
- no-trade candidate can suppress weak candidates;
- rank reason must explain why a candidate is above another candidate.

## UI direction

Dashboard must separate these views:

```text
Top Ranked Opportunities
Validated Candidates
Blocked Candidates
Raw Strategy Candidates
No-Trade Explanation
Diagnostics / Evidence
```

Do not show raw emitted rows as if they are opportunities.

## Evidence direction

The existing diagnostic scripts should continue to work.

Future evidence should include:

```text
candidate_count
validated_candidate_count
blocked_candidate_count
ranked_opportunity_count
no_trade_reason
strategy_activation_counts
strategy_suppression_counts
top_rank_reasons
top_blockers
fallback_candidate_count
stale_candidate_count
```

## Implementation roadmap

### PR #57 — Opportunity Engine Scope Bible

Add this document.

No code changes.

Acceptance:

- scope is documented;
- PR sequence is clear;
- no runtime behavior changes.

### PR #58 — Movement Candidate Contract

Add:

```text
core/movement_contract.py
tests/test_movement_contract.py
```

Acceptance:

- candidate dataclass exists;
- validation catches missing strategy id, invalid score, invalid direction, invalid status;
- candidate is JSON-serializable;
- no broker/order/depth changes.

### PR #59 — Movement Regime Classifier v1

Add:

```text
core/movement_regime.py
tests/test_movement_regime.py
```

Acceptance:

- deterministic snapshots classify trend up, trend down, range, chop, compression, volatility expansion, trap risk;
- missing data produces safe inconclusive regime;
- no strategy execution changes.

### PR #60 — Strategy Registry and Candidate Pool Shell

Add:

```text
core/movement_registry.py
core/candidate_pool.py
strategies/movement/__init__.py
tests/test_movement_registry.py
tests/test_candidate_pool.py
```

Acceptance:

- registry can run multiple strategies;
- empty registry returns empty candidate list safely;
- candidate pool can deduplicate and summarize;
- no execution connection.

### PR #61 — Opening Drive and ORB Retest

Add:

```text
strategies/movement/opening_drive.py
strategies/movement/opening_range_breakout.py
```

Acceptance:

- CALL and PUT candidates covered by tests;
- stale/fallback/wide-spread cases blocked;
- no broker/order calls.

### PR #62 — Compression Breakout and Trend Pullback

Add:

```text
strategies/movement/compression_breakout.py
strategies/movement/trend_pullback.py
```

Acceptance:

- compression requires range/ATR contraction;
- trend pullback requires established trend and valid pullback;
- late chase is rejected.

### PR #63 — VWAP Reclaim and Failed Breakout Trap

Add:

```text
strategies/movement/vwap_reclaim.py
strategies/movement/failed_breakout_trap.py
```

Acceptance:

- VWAP reclaim does not trigger in chop;
- failed breakout detects re-entry into range;
- trap candidate can suppress opposite weak breakout candidate.

### PR #64 — Exhaustion and Mean Reversion Extension

Add:

```text
strategies/movement/exhaustion_reversal.py
strategies/movement/mean_reversion_extension.py
```

Acceptance:

- exhaustion requires stretched move plus premium stall;
- mean reversion only works in range/chop conditions;
- strong trend continuation is not faded blindly.

### PR #65 — Event Volatility and Late-Day Momentum

Add:

```text
strategies/movement/event_volatility_expansion.py
strategies/movement/late_day_momentum.py
```

Acceptance:

- event strategy blocks spread explosion;
- late-day strategy is time-aware;
- expiry decay risk is visible.

### PR #66 — Option Pressure Confirmation

Add:

```text
core/option_confirmation.py
strategies/movement/option_pressure.py
```

Acceptance:

- CE/PE premium confirmation promotes/demotes candidates;
- missing OI does not break logic;
- stale/fallback data cannot promote executable status.

### PR #67 — No-Trade Engine

Add:

```text
core/no_trade_engine.py
strategies/movement/no_trade_chop.py
```

Acceptance:

- chop/liquidity/staleness no-trade states are explainable;
- no-trade can suppress weak candidates;
- diagnostics still show suppressed candidates.

### PR #68 — Opportunity Ranker v1

Add:

```text
core/opportunity_ranker.py
tests/test_opportunity_ranker.py
```

Acceptance:

- ranker produces stable ordering;
- hard-blocked candidates cannot be executable;
- rank reason is present;
- fallback/stale/wide-spread candidates rank low or advisory only.

### PR #69 — Evidence and CLI Integration

Add/update:

```text
scripts/capture_movement_candidates.py
scripts/capture_opportunity_diagnostics_evidence.py
```

Acceptance:

- evidence captures strategy activation counts;
- evidence captures candidate pool summary;
- evidence captures ranker output;
- no broker/order calls.

### PR #70 — Dashboard Separation

Add UI panels:

```text
Top Ranked Opportunities
Validated Candidates
Blocked Candidates
Raw Candidates
No-Trade Explanation
```

Acceptance:

- UI no longer makes raw rows look like ranked opportunities;
- rank reason and blockers are visible;
- executable-only toggle is clearly a filter, not intelligence.

## Test strategy

Every movement strategy needs tests for:

```text
CALL candidate
PUT candidate
missing data
stale option LTP
fallback quote
wide spread
wrong regime
no-trade case
rank/evidence fields
```

## Safety gates

Before merging any implementation PR:

```text
full pytest must pass
Portfolio CI must pass
CodeQL must pass
no broker/order calls from strategy modules
no execution gate relaxation
no fallback-to-executable path
```

## Final operating principle

The real opportunity engine is not 10+ strategies.

It is:

```text
10+ movement strategies
+ regime probabilities
+ candidate contract
+ candidate pool
+ option confirmation
+ liquidity/freshness blockers
+ no-trade engine
+ deterministic ranker
+ dashboard separation
+ evidence capture
```

Build it in that order.

Do not chase trades.

Build truth first, then ranking, then execution eligibility.
