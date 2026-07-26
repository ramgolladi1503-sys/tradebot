mode: RESEARCH_ONLY_OPTION_CANDLE_CAMPAIGN
candidate_id: compression_breakout_option_campaign_v1
decision: IMPLEMENTATION_READY_RUNTIME_DATA_REQUIRED
reason: The campaign now calls the real Compression Breakout strategy owner, emits a causal pre-outcome signal ledger, and connects selected signals to conservative CE/PE candle economics without reading sealed holdout option outcomes.
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: production strategy owner plus option_candle_backtest_v1

# Compression Breakout Option Campaign V1

## Agent Work Contract

Implement the first real strategy-specific historical CE/PE campaign after the
generic candle engine became available. Use `compression_breakout_v1`, the
highest-priority strategy with a concrete production candidate-generator owner.
Do not use the prior placeholder historical audit or replay scripts.

## Scope Guard

Changed scope is limited to:

- `research/option_e2e_recertification_v4/compression_breakout_option_campaign_v1/`
- `scripts/run_compression_breakout_option_campaign.py`
- focused research tests
- this review

No production strategy formula, profile threshold, broker, order, risk, feed,
candidate-pool runtime, dashboard, paper or live configuration is changed.

## Grill Me Review

The campaign imports and calls
`generate_compression_breakout_candidates`; it does not reproduce the strategy
formula. Context features are constructed causally by session. The breakout bar
cannot influence the frozen pre-breakout 15-bar resistance, support, range width
or ATR inputs. Future-bar mutation controls preserve earlier signal identity.

The signal ledger contains no option outcomes or P&L. It records the real
parameter hash, raw strategy score, confidence score, strategy-only rank score,
feature cutoff and earliest-entry time. Execution-quality ownership remains
unset.

## Hermes Review

The implementation follows the intended owner sequence:

```text
underlying completed bars
→ canonical causal context
→ movement regime
→ Compression Breakout candidate
→ bullish CE / bearish PE research signal
→ deterministic contract selection
→ conservative option-candle economics
```

Historical candle rank is explicitly strategy-only. Quote freshness, spread,
depth and exact fill authority remain outside this lane.

## GSD Review

The campaign adds a one-command runner that can stop after signal generation or
continue through development/validation option candles. It emits compact
hash-bound JSON/CSV evidence, a chronological split manifest, cost sensitivity,
direction-flip control and delayed-entry control.

## QA / Safety Review

Fail-closed controls cover:

- duplicate underlying timestamps;
- invalid OHLC geometry;
- missing causal warmup;
- zero-volume VWAP proxy disclosure;
- optional rejection of VWAP proxy sessions;
- deterministic signal identities;
- no outcome/P&L columns in the signal ledger;
- chronological non-overlapping splits;
- sealed holdout option data rejection;
- CE/PE option-candle integration;
- repeated-run determinism.

Safety remains:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `executable_option_pnl_certified=false`

## Acceptance Proof

Publication requires:

- focused campaign tests;
- existing option-E2E tests;
- option-candle backtest tests;
- Code Excellence;
- Agent Review Evidence Gate;
- CodeQL;
- strategy registry verification;
- repository CI.

Runtime outcome evidence is not committed by this implementation-only step.

## Runtime Proof Required After Merge

Run the campaign on the Mac-local historical underlying, session contract
catalogue and option OHLCV corpus. Development and validation runs must use
separate date-bound option inputs. Do not supply or open holdout option outcomes
until the campaign contract and negative controls are frozen.

## What This PR Does Not Prove

This implementation does not prove that Compression Breakout is profitable,
that a 60% win rate exists, that option candles equal bid/ask execution, or that
paper/live trading is ready. It establishes a truthful executable research path
to answer those questions with local data.

## Human Approval

Human approval is not required for this read-only research implementation.
Human action is required only when the Mac-local corpus must be supplied or
executed and later before any holdout, paper or live promotion.
