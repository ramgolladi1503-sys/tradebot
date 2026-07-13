# ORB candle-validation handoff

Source worktree: `/Users/madhuram/tradebot-strategy-backtesting`
Source branch: `research/strategy-backtesting-validation`
Source HEAD at handoff creation: `d9c34187bd0146dc5bb4a034434d4e89efd7259c`

## Objective

Validate `OPENING_RANGE_BREAKOUT` honestly using the existing historical candle lane. Do not claim executable option-replay certification from the candle proxy path. Keep the strict option-replay lane separate.

## Current status

- Strict option-replay verdict remains `INVALID_DUE_TO_DATA`.
- The first candle run is invalidated because the harness allowed exits to bridge sampled sessions.
- The previous `NO_STRUCTURAL_EDGE` conclusion has been withdrawn.
- A session-safe harness correction has already been implemented and regression-tested.
- Corrected-run claims still require full review and should not be treated as final until separately verified.

## Root cause

The original proxy candle harness used `_proxy_trade_rows` with global concatenated-frame indexing for exits. That let late-session trades jump into the next sampled session and invalidated the earlier PnL, win-rate, drawdown, friction, regime, WFA, and verdict conclusions.

## Harness correction already implemented

- `_proxy_trade_rows` now limits exits to the same trading session.
- Late-session signals either exit on the last legal candle in-session or produce no trade if there are no later same-session candles.
- Regression tests were added to prove the cross-session failure and the corrected same-session behavior.

## Files changed in the source worktree

- `scripts/backtest_all_strategies_available_data.py`
- `tests/test_backtest_all_strategies_available_data.py`
- `docs/research/strategy_backtesting/opening_range_breakout_validation.md`
- `docs/research/strategy_backtesting/opening_range_breakout_results.json`

## Tests already run

Focused validation passed:

```text
pytest -q tests/test_backtest_all_strategies_available_data.py tests/test_opening_movement_strategies.py tests/test_edge_72_breakout_candidate_generator.py tests/option_backtest/test_loader.py tests/option_backtest/test_engine.py tests/option_backtest/test_wfa.py
```

Result:

```text
67 passed in 18.09s
```

## Corrected-run evidence captured so far

The corrected candle rerun is session-safe and deterministic on the sampled 60-session NIFTY corpus.

Known corrected-run facts captured in the evidence files:

- sample sessions: 60
- source files: 60
- rows: 22,500
- raw manifest hash: `84439c50a74a7016dc3cef62194a96fc2b68dff05c651a689f340c5f2e3a1c15`
- prepared-input hash: `89b5423b1f003dd729ca90d8e8373479f76ad79527b1aa480230cc300bca8ab7`
- candidate hash: `c4b8375a1312b7ce2f2cf3a18f472392fcdb176183d5b34a68d5b697fd1646b5`
- trade hash: `2122c7512465850a1769ef85abe37fcdf32b8cd47657017ab4097ffe230c3d38`
- candidate count: 1,628
- trade count: 1,628
- rejection count: 20,872
- cross-session trade count: 0
- max concurrent positions inside a session: 15
- overlapping trade count inside sessions: 621

## Volume semantics

The candle lane does not use true traded-volume confirmation.
It computes `vol_z` from ATR statistics, so this is a documented volume-proxy fallback lane.

Do not describe it as true volume-confirmed ORB.

## Pending verification

Do not treat the following as final until re-reviewed:

- whether the corrected rerun should remain `CONDITIONALLY_SUPPORTED`
- whether the candle WFA path is acceptable for the final report
- whether manual reconciliation and negative-control claims are sufficiently strong for the report text
- whether the corrected evidence files need one more tightening pass before final commit

## Deliberately unchanged

- strict option-replay loader contract
- live feed code
- ranking / UI logic
- broker integrations
- strategy thresholds
- unrelated strategies

## Read-only corpus dependency

The historical Upstox candle corpus under `/Users/madhuram/tradebot/runtime/upstox_candidate_replay` is consumed read-only. Do not write generated results back into that source tree.

## Handoff guidance

Continue the ORB correctness task from this point only after migrating into the standardized Codex worktree and verifying the checkpoint branch.
