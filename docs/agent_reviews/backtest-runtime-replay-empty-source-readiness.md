# Agent Review Evidence — Empty Runtime Replay Source Readiness

mode: PAPER
candidate_id: fix-empty-runtime-replay-readiness-pr
decision: require-replayable-runtime-rows-for-live-capture-replay
reason: Prevent empty or timestamp-invalid runtime sources from unlocking runtime replay readiness.
timestamp: 2026-06-12T00:30:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/backtest-runtime-replay-empty-source-readiness.md

## Agent Work Contract

This PR is limited to Phase 1.5 readiness classification for runtime replay sources.

Requested paths:

- `core/backtesting/data_catalog.py`
- `core/backtesting/models.py`
- `core/backtesting/data_loader.py`
- `tests/backtesting/test_data_catalog.py`
- `tests/backtesting/test_diagnostics_cli.py`
- `docs/backtesting/historical_data_requirements.md`
- `docs/agent_reviews/backtest-runtime-replay-empty-source-readiness.md`

Allowed paths:

- replay-feasibility classification
- runtime-source warnings
- offline tests
- documentation

Forbidden paths:

- Phase 2 replay/backtest engine
- Phase 3 ranking, confidence, or sizing work
- broker adapters
- live execution gates
- risk gates
- strategy generators

## Scope Guard

In scope:

- distinguish runtime source existence from runtime replay feasibility
- require non-empty, timestamp-usable runtime sources before unlocking `LIVE_CAPTURE_REPLAY`
- keep empty runtime SQLite visible in the catalog without treating it as replay-ready

Out of scope:

- broker/API calls
- live runtime behavior
- order placement
- simulator or strategy changes

## Grill Me Review

Question: Why is file existence not enough?

Answer: A zero-row SQLite file cannot replay anything. Treating it as replay-ready overstates evidence and can falsely unlock downstream work.

Question: Should schema-valid empty runtime files be hidden?

Answer: No. They should stay visible for diagnostics, but they must be marked not replay-feasible.

Question: Does this unlock Phase 2?

Answer: No. This fix removes a false positive. Phase 2 remains blocked for real eight-year edge validation.

## Hermes Review

Architecture choice:

- keep `schema_valid` separate from `replay_ready`
- preserve source discovery and provenance
- make mode feasibility depend on replayable rows plus usable timestamps

Safety property:

- `LIVE_CAPTURE_REPLAY` now requires a source that can actually be replayed

## GSD Review

Implementation:

- added explicit `replay_ready` on historical source records
- runtime sources now emit warnings for empty replay inputs and missing replay timestamps
- runtime replay feasibility and score use `replay_ready`, not mere schema validity

## QA / Safety Review

Tests cover:

- empty runtime SQLite does not unlock replay
- empty runtime SQLite yields score `0` when no other data exists
- runtime CSV without `timestamp` remains invalid
- valid timestamped runtime data still unlocks replay-only readiness
- diagnostics, readiness, and catalog outputs agree on verdict and score

No broker, live gate, risk, or strategy files were touched.

## Acceptance Proof

Commands:

```bash
python -m pytest tests/backtesting -q
rm -f .runtime/reports/backtesting/*latest.json
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
python scripts/import_historical_data.py --config configs/backtest_8y.example.json --dry-run
jq '.data_readiness_verdict,.data_readiness_score,.available_modes,.blocked_modes' .runtime/reports/backtesting/data_readiness_latest.json
jq '.data_readiness_verdict,.data_readiness_score,.available_modes,.blocked_modes' .runtime/reports/backtesting/backtest_data_diagnostics_latest.json
jq '.data_readiness_verdict,.data_readiness_score,.mode_feasibility' .runtime/reports/backtesting/historical_data_catalog_latest.json
```

Expected:

- empty runtime SQLite alone does not unlock replay
- invalid runtime CSV without `timestamp` stays invalid
- verdict stays `NEED_USER_HISTORICAL_DATA` unless replayable rows exist

## Runtime Proof Required After Merge

After merge, regenerate the three backtesting artifacts on `main` and verify they agree on:

- `data_readiness_verdict`
- `data_readiness_score`
- `LIVE_CAPTURE_REPLAY` feasibility

If only empty runtime SQLite and invalid runtime CSV/log files exist, the expected verdict is `NEED_USER_HISTORICAL_DATA`.

## What This PR Does Not Prove

- eight-year strategy edge
- real historical options completeness
- Phase 2 simulator correctness
- Phase 3 ranking quality
- live execution safety beyond existing unchanged gates

## Human Approval

Merge only if:

- backtesting tests pass
- agent review evidence passes
- code-excellence gates pass
- runtime replay no longer unlocks from empty sources


## High-Risk Path Review

N/A
