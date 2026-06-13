# Agent Review Evidence — Runtime Replay Readiness Verdict

mode: PAPER
candidate_id: fix-backtest-runtime-replay-readiness-verdict-pr558
decision: classify-runtime-replay-readiness-separately
reason: Prevent runtime-replay-only evidence from being mislabeled as EOD or proxy backtest readiness.
timestamp: 2026-06-11T14:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/backtest-runtime-replay-readiness-verdict.md

## Agent Work Contract

This PR is a small fix-only patch for the Phase 1.5 backtesting readiness classifier.

The work contract is limited to correcting the readiness verdict when only runtime replay data is feasible.

The PR must not implement Phase 2 replay/backtesting, Phase 3 strategy remediation, broker calls, live execution changes, risk gate changes, or strategy generator changes.

## Scope Guard

In scope:

- Add a distinct runtime-replay-only readiness verdict.
- Prevent runtime replay feasibility from being mislabeled as EOD/proxy readiness.
- Update tests for readiness classification.
- Update backtesting readiness documentation.

Out of scope:

- Phase 2 replay/backtest engine.
- Phase 3 ranking/confidence/sizing remediation.
- Strategy generator changes.
- Broker/API integrations.
- Live feed, live order, execution, or risk gate changes.
- Historical data acquisition.

## Grill Me Review

Question: Why is this patch needed?

Answer: The previous classifier could report `READY_FOR_EOD_OR_PROXY_ONLY` when neither `OPTIONS_EOD` nor `UNDERLYING_SIGNAL_WITH_OPTION_PROXY` was feasible and only `LIVE_CAPTURE_REPLAY` was feasible. That overstated the evidence level.

Question: Why not proceed to Phase 2 now?

Answer: Phase 2 remains blocked for real eight-year intraday options validation until historical intraday options data exists. Runtime replay can validate pipeline behavior, but it cannot prove eight-year strategy edge.

Question: Does this PR make the strategy better?

Answer: No. It only makes the data-readiness verdict more honest.

Question: Does this PR unlock true intraday options backtesting?

Answer: No. `TRUE_OPTIONS_INTRADAY` still requires valid historical intraday option contract data.

## Hermes Review

Traceability:

- Problem: runtime-replay-only feasibility was grouped under EOD/proxy readiness.
- Fix: introduce and use `READY_FOR_RUNTIME_REPLAY_ONLY`.
- Safety property: the classifier no longer overstates available historical evidence.
- Verification: tests cover true intraday, EOD/proxy, runtime replay only, invalid schema, and no-data cases.

## GSD Review

Changed files:

- `core/backtesting/models.py`
- `core/backtesting/data_catalog.py`
- `docs/backtesting/historical_data_requirements.md`
- `docs/backtesting/eight_year_strategy_validation.md`
- `docs/backtesting/data_vendor_checklist.md`
- `tests/backtesting/test_data_catalog.py`
- `tests/backtesting/test_diagnostics_cli.py`

Implementation:

- Added `READY_FOR_RUNTIME_REPLAY_ONLY`.
- Tightened readiness classification order:
  1. `TRUE_OPTIONS_INTRADAY` feasible -> `READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST`
  2. `OPTIONS_EOD` or `UNDERLYING_SIGNAL_WITH_OPTION_PROXY` feasible -> `READY_FOR_EOD_OR_PROXY_ONLY`
  3. `LIVE_CAPTURE_REPLAY` feasible -> `READY_FOR_RUNTIME_REPLAY_ONLY`
  4. invalid-only sources -> `BLOCKED_BY_SCHEMA`
  5. otherwise -> `NEED_USER_HISTORICAL_DATA`

## QA / Safety Review

Safety checks:

- No broker/API calls added.
- No live execution gates changed.
- No risk gates changed.
- No strategy generators changed.
- No Phase 2 implementation added.
- No Phase 3 implementation added.
- No generated runtime reports staged.

The patch is fail-closed because it prevents runtime replay from being reported as a stronger EOD/proxy readiness state.

## Acceptance Proof

Commands run:

```bash
python -m pytest tests/backtesting -q
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
```

Observed result:

```text
26 passed
phase_one_verdict: NEED_USER_HISTORICAL_DATA
data_readiness_verdict: NEED_USER_HISTORICAL_DATA
data_readiness_score: 0
```

Runtime-replay-only behavior is covered by tests and returns:

```text
data_readiness_verdict: READY_FOR_RUNTIME_REPLAY_ONLY
data_readiness_score: 20
```

## Runtime Proof Required After Merge

After merge to `main`, run:

```bash
git fetch origin
git switch main
git pull origin main

python -m pytest tests/backtesting -q
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
```

Expected result:

- If no qualifying data exists: `NEED_USER_HISTORICAL_DATA`
- If only runtime replay exists: `READY_FOR_RUNTIME_REPLAY_ONLY`
- It must not report `READY_FOR_EOD_OR_PROXY_ONLY` unless EOD or underlying proxy mode is actually feasible.

## What This PR Does Not Prove

This PR does not prove:

- strategy edge
- eight-year profitability
- intraday options execution realism
- ranking quality
- confidence calibration quality
- slippage/fill realism
- backtest profitability
- historical data completeness

It only proves that readiness classification is more precise.

## Human Approval

Human approval is required before merge because this PR changes readiness classification semantics used to decide whether Phase 2 backtesting is allowed.

Reviewer should confirm:

- runtime replay only is classified as `READY_FOR_RUNTIME_REPLAY_ONLY`
- EOD/proxy readiness is not reported unless EOD/proxy modes are feasible
- no live trading or broker path was touched
- no Phase 2/Phase 3 scope slipped into this patch
