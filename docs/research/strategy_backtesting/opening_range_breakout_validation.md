# OPENING_RANGE_BREAKOUT validation

Date: 2026-07-13
Worktree: `/Users/madhuram/tradebot-strategy-backtesting`
Branch: `research/strategy-backtesting-validation`
Frozen baseline commit: `8d4a6de390f02ac128ab05091f1a68ea4b56144e`

## Strict replay lane

Trusted backtest engine: `core/option_backtest/engine.py::OptionBacktestEngine`

Trusted WFA engine: `core/option_backtest/wfa.py::run_option_replay_wfa`

Strict-replay verdict: `INVALID_DUE_TO_DATA`

The strict option-replay path remains blocked by the loader contract. The raw replay parquet available in this checkout is tick/depth data, not a strict option-replay file with the contract metadata required by `core/option_backtest/loader.py`.

Strict replay data inspected:

- `/Users/madhuram/tradebot-strategy-backtesting/runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- SHA-256: `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`
- row count: `876127`
- date range: `2026-07-02 10:52:39` to `2026-07-02 17:21:45` UTC
- instruments: `BANKNIFTY`, `NIFTY`

Missing strict-loader fields in that dataset:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `oi`
- `underlying`
- `option_type`
- `strike`
- `expiry`
- `provider`
- `dataset_hash`
- `bar_interval`
- `quote_timestamp`

That failure is separate from the candle-based ORB study below.

## Candle-based historical lane

This lane uses the existing historical-candle breakout implementation:

- candle engine: `core/breakout_candidate_generator.py::build_breakout_candidate_intents`
- data preparation helpers: `scripts/backtest_all_strategies_available_data.py::_prepare_frames`, `scripts/backtest_all_strategies_available_data.py::_market_row`
- walk-forward harness: `core/walk_forward.py::run_walk_forward`

This is a candle-research result, not executable option-fill truth.

### Post-review correction

The original candle run completed, but review found a trade-lifecycle defect in the harness: exit rows could jump across sampled sessions. That invalidates the prior PnL, win-rate, drawdown, friction, regime, WFA, and final-verdict conclusions. The historical numbers below are preserved for traceability only and are now invalidated evidence.

The previous `NO_STRUCTURAL_EDGE` verdict is withdrawn pending a corrected rerun.

## Corrected rerun

The harness was fixed to keep proxy trades session-safe. The corrected rerun used the same sampled 60-session NIFTY corpus, but processed each session independently and refused cross-session exits.

### Dataset

- source root: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
- sampled sessions: 60
- source files: 60
- row count: 22,500
- raw manifest hash: `84439c50a74a7016dc3cef62194a96fc2b68dff05c651a689f340c5f2e3a1c15`
- prepared-input hash: `89b5423b1f003dd729ca90d8e8373479f76ad79527b1aa480230cc300bca8ab7`
- candidate hash: `c4b8375a1312b7ce2f2cf3a18f472392fcdb176183d5b34a68d5b697fd1646b5`
- trade hash: `2122c7512465850a1769ef85abe37fcdf32b8cd47657017ab4097ffe230c3d38`

### Volume eligibility

The harness does not use raw volume as the gating feature for this strategy slice. It computes `vol_z` from ATR-based volatility statistics:

`vol_z = (atr - rolling_mean(atr)) / rolling_std(atr)`

Representative rows from `/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20240530/underlying/NIFTY_20240530.parquet`:

- `2024-05-30T09:15:00`: raw volume `0`, `atr 0.0`, `vol_z 0.0`
- `2024-05-30T09:30:00`: raw volume `0`, `atr 19.474999999999845`, `vol_z -0.28471783249923277`
- `2024-05-30T09:45:00`: raw volume `0`, `atr 14.01071428571439`, `vol_z -0.7211813306145064`

Volume classification: `VOLUME_GATE_BYPASSED`

This is a documented production fallback / proxy lane, not true volume-confirmed ORB.

### Candidate multiplicity and lifecycle

The strategy is stateless in the candle harness:

- one signal can emit on every qualifying candle
- no cooldown or session-level position memory exists in the generator
- repeated entries are allowed when the breakout/retest condition persists

Corrected-session aggregate:

- candidate count: `1628`
- trade count: `1628`
- rejection count: `20872`
- sessions with zero candidates: `3`
- sessions with zero trades: `3`
- max concurrent positions inside a session: `15`
- overlapping trade count inside sessions: `621`
- cross-session trade count: `0`

### Deterministic replay

Two identical corrected runs produced the same hashes:

- candidate hash: `c4b8375a1312b7ce2f2cf3a18f472392fcdb176183d5b34a68d5b697fd1646b5`
- trade hash: `2122c7512465850a1769ef85abe37fcdf32b8cd47657017ab4097ffe230c3d38`

The manifest hash is independent from the candidate and trade hashes.

### Corrected friction sensitivity

Baseline friction used by the candle harness:

- `2.0 bps` round-trip

Adverse and severe scenarios:

- `5.0 bps`
- `10.0 bps`

Results:

- baseline: `1628` trades, `809` wins, `819` losses, net `+655.5181373146523 bps`, average `+0.4026524184979437 bps`, max drawdown `-636.2554489661983 bps`
- adverse: net `-4228.481862685348 bps`
- severe: net `-12368.481862685348 bps`

Increasing friction worsens the result as expected.

### Regime segmentation

Using causally available regime at decision time:

- `RANGE`: `1468` trades, net `+751.2148215652089 bps`
- `TREND`: `160` trades, net `-95.69668425055772 bps`

The edge is concentrated in RANGE and weak/negative in TREND.

### Manual reconciliation

Winning trade:

- session: `2024-05-30`
- signal: `2024-05-30T09:37:00`
- direction: `BUY_PUT`
- entry: `2024-05-30T09:37:00`
- exit: `2024-05-30T09:52:00`
- entry price: `22613.45`
- exit price: `22591.35`
- gross: `+9.772944862460609 bps`
- net: `+7.772944862460609 bps`

Losing trade:

- session: `2024-05-30`
- signal: `2024-05-30T09:41:00`
- direction: `BUY_PUT`
- entry: `2024-05-30T09:41:00`
- exit: `2024-05-30T09:56:00`
- entry price: `22597.15`
- exit price: `22600.25`
- gross: `-1.3718544152685475 bps`
- net: `-3.3718544152685475 bps`

Repeated-breakout example:

- session: `2024-05-30`
- consecutive candidate timestamps: `2024-05-30T09:37:00`, `2024-05-30T09:38:00`

No-trade session:

- `2025-01-17`

Late-session candidate case:

- none observed in the corrected sampled corpus under this strategy contract

Rejected candidate case:

- the strategy returns no explicit rejected-candidate object; no-trade rows are the observable blocker surface

The corrected manual samples stay inside one session.

### WFA

Walk-forward through `core.walk_forward.run_walk_forward` with a session-safe backtest factory is acceptable for this candle lane:

`CANDLE_WFA_PATH_ACCEPTABLE`

Fold metrics:

- window count: `4`
- average return: `0.0010220000000000001`
- average max drawdown: `-0.0036710000000000007`
- average win rate: `0.4958755`
- average R: `0.0037942500000000003`
- average sharpe proxy: `0.5569149999999999`
- total trades: `1126`

WFA hashes:

- window hash: `64b34d6c25523d2d79981fc79b282062983ff9b2df38238c82706c426c38368a`
- fold-trade hash: `06c7eb1849bb08c1c2cba8dada73787ea4fe2ef3970753dca5c589c75eae5e18`

### Negative control

Breaking the opening-range boundary suppresses the strategy as expected:

- signals: `0`
- trades: `0`

### Corrected verdict

`CONDITIONALLY_SUPPORTED`

Reason:

- the corrected session-safe harness is now honest and deterministic
- the strategy shows positive baseline candle evidence and acceptable WFA behavior
- the lane still uses a documented volume proxy fallback instead of true volume-confirmed ORB
- no late-session candidate was observed in the corrected sampled corpus
- the strategy exposes no explicit rejected-candidate object, only no-trade surfaces

### Dataset

Source root:

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`

Sampled immutable dataset:

- 60 evenly spaced NIFTY candle dates spanning 2024-05-30 through 2026-07-10
- file count in the sampled manifest: 521
- row count: 22,500
- instruments: `NIFTY`
- timestamp timezone: UTC on the raw files
- volume quality: zero-volume underlying candles on this corpus
- VWAP treatment: the existing available-data candle harness falls back to a typical-price proxy when volume is zero

Dataset manifest hash:

- `fc12a163c3488cfd6b90ff326c0740f381a9368e7243cdf2f801ce43f0ac7198`

### Strategy implementation

The candle lane is the pure breakout CandidateIntent generator:

- `core/breakout_candidate_generator.py::build_breakout_candidate_intents`

Default behavior from the generator:

- upside breakout: `BUY_CALL` when LTP clears opening range high and volume confirmation passes
- downside breakout: `BUY_PUT` when LTP breaks opening range low and volume confirmation passes
- blocked hypotheses are still emitted visibly as `NO_TRADE` intents with blockers

### Deterministic replay

The same candle pipeline was run twice against the same sampled dataset.

Both passes matched:

- candidate count: `6290`
- 15-minute trade count: `6290`
- rejection count: `16209`
- candidate hash: `fc12a163c3488cfd6b90ff326c0740f381a9368e7243cdf2f801ce43f0ac7198`
- trade hash: `25316dd49c30efb90724fa7ec06b95b51d6a2fcf005dbaf5582a319f45ad2a06`

Blocker distribution in the sampled run:

- `breakout_volume_not_confirmed`: `15981`
- `breakout_no_range_break`: `213`
- `breakout_missing_range`: `15`
- `breakout_invalid_numeric_input`: `15`

### Manual reconciliation

Representative winning trade:

- signal: `2026-06-12T15:14:00`
- entry: `2026-06-12T15:15:00`
- exit: `2026-06-25T09:15:00`
- direction: `BUY_CALL`
- entry price: `23620.95`
- exit price: `24134.20`
- gross: `+217.28592626460764 bps`
- net after baseline friction: `+213.28592626460764 bps`

Representative losing trade:

- signal: `2025-04-07T15:17:00`
- entry: `2025-04-07T15:18:00`
- exit: `2025-04-22T09:18:00`
- direction: `BUY_PUT`
- entry price: `22137.80`
- exit price: `24104.95`
- gross: `-888.5932658168394 bps`
- net after baseline friction: `-892.5932658168394 bps`

The independent recomputation matched the simulated trade rows.

### Friction sensitivity

Round-trip friction scenarios:

- baseline: `4.0 bps`
- adverse: `10.0 bps`
- severe: `18.0 bps`

Baseline scenario:

- trade count: `6290`
- wins: `2149`
- losses: `4141`
- net PnL: `-45558.600028 bps`
- average net PnL per trade: `-7.243021 bps`
- max drawdown: `-45564.816432 bps`

Adverse and severe friction made the result worse, as expected.

### Regime segmentation

Using the regime value available at decision time:

- `RANGE`: 88 trades, `-3.20992 bps` average net PnL
- `TREND`: 6202 trades, `-7.300246 bps` average net PnL

This is not structurally positive in either regime bucket.

### Parameter perturbation

Perturbing the generator’s `min_volume_z` around the default threshold changed trade count but did not create a positive edge:

- `0.4`: 6664 trades, `-7.284022 bps` average net PnL
- `0.5`: 6290 trades, `-7.243021 bps` average net PnL
- `0.6`: 5927 trades, `-7.27502 bps` average net PnL
- `0.8`: 5230 trades, `-7.615579 bps` average net PnL

### Negative controls

Shifting the signal timing by one bar worsened the result:

- shifted trade count: `6290`
- average net PnL: `-7.502522 bps`
- net PnL sum: `-47190.864062 bps`

### WFA

Walk-forward was run through `core.walk_forward.run_walk_forward` with a custom backtest factory over the sampled candle dataset.

WFA result:

- window count: `4`
- average return: `-0.06248875`
- average max drawdown: `-0.0654395`
- average win rate: `0.34071925`
- average R: `-0.02462425`
- average sharpe proxy: `-7.50909525`
- total trades: `3842`

The walk-forward path is not supportive.

## Final verdict

`CONDITIONALLY_SUPPORTED`

The historical candle run remains invalidated because the original harness crossed sampled sessions. The corrected rerun is now the operative candle result and supports the strategy only conditionally because it depends on a documented volume-proxy fallback and does not surface explicit rejected-candidate objects.

## Exact unresolved limitations

- Strict option replay is still blocked by missing contract metadata and strict loader fields.
- The candle validation uses the repo’s existing candle proxy lane, not executable option fills.
- The sampled candle corpus uses zero-volume underlying bars, so VWAP is proxied by the existing candle harness rather than true traded volume.
- The corrected candle rerun is executed and deterministic, but it remains a candle proxy study rather than executable option-fill truth.
