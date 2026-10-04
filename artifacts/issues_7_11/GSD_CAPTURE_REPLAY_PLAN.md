# GSD Stage 2 plan — historical replay health authority

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Stop parquet replay from inventing feed health
**scope:** execute `docs/agent_reviews/issues_7_11_hermes_capture_replay.md` only
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Files in scope

- `core/replay/governed_market_replay.py`
  - Historical tick/bar sources emit unknown transport/session health without source evidence.
  - Remove the fixed option-age value from OHLCV bar replay.
  - Preserve recorded receive timestamps and event/availability causality.
  - Preserve manually constructed `ReplayEvent` fixtures.
- `tests/replay/test_replay_fidelity_hardening.py`
  - Assert missing receive/health evidence stays unknown.
  - Assert a valid recorded receipt time does not imply websocket or global feed health.
  - Assert malformed or non-authoritative input cannot produce healthy defaults.
  - Assert bar replay does not create option tick-age or health evidence.
- `tests/replay/test_governed_market_replay.py` only if existing source compatibility coverage needs updating.
- `artifacts/issues_7_11/` for exact attack/replay results and final status.

## Forbidden paths

Live feed/runtime producers, candidate and execution safety, strategy evaluator logic or thresholds, ranking, risk/order/broker modules, credentials, token-universe configuration, and runtime wiring.

## Baseline and blast radius

The Hermes probe on the hash-pinned Oct. 1 capture observed that the parquet lacks receive-time and transport-health fields while the source emits `feed_ok=true`, `websocket_ok=true`, and `NORMAL`. The latest broad regression recorded in `FINAL_VERDICT.json` is 8,608 passed, 9 skipped, 29 deselected with three documented exclusions. This targeted patch changes only historical parquet replay metadata and may cause replay strategy-shadow consumers to report unknown/degraded health where they previously received an invented healthy value. No live feed or execution consumer is in scope.

## Execution

1. Add failing tests for tick parquet with absent receipt and health fields.
2. Add a recorded-receipt case and prove transport health remains unknown.
3. Add a bar parquet case and prove event availability remains bar-start plus 60 seconds while option quote age and transport/session health remain unknown.
4. Implement the smallest source-only change; leave the `ReplayEvent` defaults for deliberately constructed scenarios unchanged.
5. Run focused replay fidelity and governed replay tests.
6. Re-run the Oct. 1 100-event capture probe; record source hash, event count, unknown health, no observations under missing T-1, and closed authority flags.
7. Independently inspect diff and run `git diff --check`; confirm no live, strategy, risk, token, broker, or order path changed.

## Acceptance

`UpstoxTickReplaySource` and `ParquetBarReplaySource` do not claim transport/session health without recorded authority. A valid source receipt timestamp can establish event availability/latency only. Bar rows cannot pass as fresh option quotes. Causality and captured event ordering remain intact. Replay continues read-only with zero broker/order authority. Live correctness and Issues 7/8/11 remain unclaimed.
