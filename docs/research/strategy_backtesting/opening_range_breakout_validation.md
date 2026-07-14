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

Volume classification: `HARNESS_SEMANTIC_MISMATCH`

This is a harness proxy, not true traded-volume confirmation for ORB.

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

`INVALID_DUE_TO_BACKTEST_HARNESS`

Reason:

- the corrected session-safe harness is deterministic, but it remains a candle proxy rather than executable option-fill truth
- the strategy evidence depends on same-candle-close proxy execution, not a proven production position contract
- the lane still uses an ATR-derived proxy in the field named `volume_z`, which is not true traded-volume confirmation
- the strategy exposes no explicit rejected-candidate object, only no-trade surfaces
- the positive candle numbers are therefore research observations, not a final executable-strategy verdict

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

`INVALID_DUE_TO_BACKTEST_HARNESS`

The historical candle run remains invalidated because the original harness crossed sampled sessions. The corrected rerun is retained only as withdrawn trace evidence; it is not an operative validation result because it depends on a documented volume-proxy fallback, does not surface explicit rejected-candidate objects, and does not represent executable option fills.

Historical note: the previous `CONDITIONALLY_SUPPORTED` wording is withdrawn and retained only as non-operative trace history.

## Exact unresolved limitations

- Strict option replay is still blocked by missing contract metadata and strict loader fields.
- The candle validation uses the repo’s existing candle proxy lane, not executable option fills.
- The sampled candle corpus uses zero-volume underlying bars, so VWAP is proxied by the existing candle harness rather than true traded volume.
- The corrected candle rerun is documented in `/tmp`, but the exact prepared-input provenance is not committed, so the 1628 claim is withdrawn as non-reproducible evidence.


## OHLCV candle research validation

This section is the operative historical-candle research lane for `OPENING_RANGE_BREAKOUT`.

Label: `OHLCV_CANDLE_RESEARCH_ONLY`

It uses historical NIFTY candle data from `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`, the deterministic 60-session source manifest in `docs/research/strategy_backtesting/evidence/orb_ohlcv_source_manifest.json`, the existing ORB movement strategy callable resolved from `strategies/movement/opening_range_breakout.py`, and the existing walk-forward engine in `core/walk_forward.py`.

### Manifest and reproducibility

- canonical manifest hash: `113ce0079e9b5bdd9ff87fc62f327a27bb7feb328418b7ea3519bcc664275220`
- source-manifest file SHA-256: `dc816e2481dc74d833d790a2c90d88ef73860aac12df4efdca793cbef9d5c992`
- source root: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
- session count: `60`
- file count: `60`
- row count: `22500`
- instrument: `NIFTY`
- deterministic selection rule: evenly spaced complete NIFTY sessions with 375 one-minute candles
- reproducibility: run 1 and run 2 matched on manifest hash, prepared-input hash, signal hash, forward-observation hash, accepted-entry hash, rejection hash, trade hash, and metrics hash

### Strategy identity and terminology

- registry key: `OPENING_RANGE_BREAKOUT`
- registry callable advertised: `generate_opening_range_breakout_candidates`
- actual module implementation used: `strategies/movement/opening_range_breakout.py::generate_opening_range_retest_candidates`
- registry compatibility note: `registry_callable_mismatch_resolved_to_existing_function`
- opening-range minimum: `15` minutes
- research entry model: `next_bar_open`
- research overlap policy: `non_overlapping`
- volatility input label: `atr_volatility_z_proxy`
- `atr_volatility_z_proxy` is an ATR-derived volatility proxy, not traded-volume confirmation

### Layer A — raw ORB signals

Raw signal observations are not trades.

- signal count: `1410`
- CALL signals: `841`
- PUT signals: `569`
- sessions with signals: `53`
- sessions without signals: `7`
- signal hash: `cd7b6056edce2fe6816240708b3230ecc71205db46554a51eace7cce1dd53c41`

### Layer B — signal forward-return observations

These are causal close-to-close forward observations, not executable trades.

- observation count: `5640`
- horizons: `5`, `10`, `15`, `30` minutes
- forward-observation hash: `a3dea18f2dcfcced6cd13369081dd5330562e5d4021cf5cddf7b248355d7b4f8`

Per-horizon results:

- `5m`: count `1410`, mean net return `-0.00021014431779570154`, median `-0.00018916543983201733`, win rate `0.3659574468085106`
- `10m`: count `1410`, mean net return `-0.00021011413573357427`, median `-0.000181517096666217`, win rate `0.3964539007092199`
- `15m`: count `1410`, mean net return `-0.00018756469881005405`, median `-0.0001497829640732749`, win rate `0.42836879432624114`
- `30m`: count `1410`, mean net return `-0.00021494380136295572`, median `-0.00010343577267748466`, win rate `0.4716312056737589`

### Layer C — non-overlapping OHLCV research trades

Research policy: `ORB_OHLCV_RESEARCH_POLICY_V1`

- accepted entries: `144`
- completed research trades: `144`
- rejected while active: `1266`
- rejected because no legal next bar exists: `0`
- maximum concurrency: `1`
- overlapping trades: `0`
- cross-session trades: `0`
- accepted-entry hash: `5d8b4da30867f9e77db9e8edbb4470d0c9f82a666426e48ad3fed6fec8247043`
- rejection hash: `4fcde80b12374c8a855e5c573de8ebe16c3c8747d09f93bda9ca26cd46b238ee`
- trade hash: `5d8b4da30867f9e77db9e8edbb4470d0c9f82a666426e48ad3fed6fec8247043`

Directional split:

- BUY_CALL trades: `78`
- BUY_PUT trades: `66`

### Friction sensitivity

Baseline friction is `2.0 bps` round-trip. Increasing friction worsens the result as expected.

- `2.0 bps`: trade count `144`, gross sum `-0.015882359470417162`, net sum `-0.04468235947041717`, avg net `-0.0003102941629890081`, median net `-0.00021371017047524515`, win rate `0.4166666666666667`, avg win `0.0008121650699171036`, avg loss `-0.0011120507579219449`, profit factor `0.5216649536462651`, max drawdown `-0.05040722439678512`
- `5.0 bps`: trade count `144`, gross sum `-0.015882359470417162`, net sum `-0.08788235947041717`, avg net `-0.0006102941629890081`, median net `-0.0005137101704752452`, win rate `0.3125`, avg win `0.0007325025718296005`, avg loss `-0.0012206563151792847`, profit factor `0.27276778101057636`, max drawdown `-0.08926798182920907`
- `10.0 bps`: trade count `144`, gross sum `-0.015882359470417162`, net sum `-0.15988235947041718`, avg net `-0.001110294162989008`, median net `-0.0010137101704752452`, win rate `0.13194444444444445`, avg win `0.0009043465576600714`, avg loss `-0.0014165195525276681`, profit factor `0.09704114321545583`, max drawdown `-0.15999266810499443`

### Manual reconciliation

Winning trade:

- session: `2024-10-28`
- signal: `2024-10-28T10:15:00+05:30`
- direction: `BUY_CALL`
- entry: `2024-10-28T10:16:00+05:30`
- exit: `2024-10-28T10:31:00+05:30`
- entry price: `24304.2`
- exit price: `24382.05`
- gross return: `0.003203150072826899`
- net return: `0.003003150072826899`

Losing trade:

- session: `2024-09-06`
- signal: `2024-09-06T09:31:00+05:30`
- direction: `BUY_CALL`
- entry: `2024-09-06T09:32:00+05:30`
- exit: `2024-09-06T09:47:00+05:30`
- entry price: `25166.25`
- exit price: `25021.35`
- gross return: `-0.005757711220384487`
- net return: `-0.005957711220384487`

### Regime segmentation

Regime is the causally available regime hinted by the candidate scores at decision time.

- RANGE: `132` trades, net sum `-0.0447645933973784`, avg net `-0.000339125707555897`
- TREND_DOWN: `7` trades, net sum `0.00204449908405553`, avg net `0.00029207129772221854`
- TREND_UP: `5` trades, net sum `-0.001962265157094189`, avg net `-0.0003924530314188378`

### WFA

Walk-forward was run through `core.walk_forward.run_walk_forward` using the same candle-research policy and a train/test fold split of `20/10` days with a `10`-day step.

- window count: `4`
- total trades: `102`
- average win rate: `0.440433`
- average R: `-0.00021150000000000002`
- average sharpe proxy: `-1.1082994999999998`
- WFA window hash: `deb3fa129414655837e6ce4fdb7a87ca6b9666943b7030ebb38da3c513bc146a`
- WFA path status: `CANDLE_WFA_PATH_ACCEPTABLE`

Fold summary:

- window 1: `2024-05-30` to `2025-01-24` test `2025-02-06` to `2025-06-16`, trades `30`, win rate `0.466667`, avg R `-0.00021`, sharpe proxy `-0.93266`
- window 2: `2024-10-01` to `2025-06-16` test `2025-06-26` to `2025-10-16`, trades `33`, win rate `0.363636`, avg R `-0.000434`, sharpe proxy `-2.170473`
- window 3: `2025-02-06` to `2025-10-16` test `2025-10-31` to `2026-02-23`, trades `25`, win rate `0.36`, avg R `-0.000335`, sharpe proxy `-1.682015`
- window 4: `2025-06-26` to `2026-02-23` test `2026-03-06` to `2026-07-03`, trades `14`, win rate `0.571429`, avg R `0.000133`, sharpe proxy `0.35195`

### Negative controls

- plus-one-bar entry delay: `137` trades, net sum `-0.04147497356632559`, avg net `-0.0003027370333308437`, win rate `0.38686131386861317`
- plus-two-bar entry delay: `132` trades, net sum `-0.04442352172566812`, avg net `-0.0003365418312550615`, win rate `0.3787878787878788`
- signal-bar-close proxy sensitivity: `148` trades, net sum `-0.03940109056058176`, avg net `-0.0002662235848687957`, win rate `0.4594594594594595`
- broken opening-range boundary test: `0` signals, `0` trades

### Final verdicts

Signal-level verdict: `ORB_SIGNAL_EDGE_NOT_SUPPORTED`

OHLCV research-policy verdict: `NO_STRUCTURAL_EDGE`

This is an OHLCV candle-research result only. It does not claim executable option fills, broker truth, or strict option-replay certification.
