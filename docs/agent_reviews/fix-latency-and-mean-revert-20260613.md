source_agent: antigravity
action: PLAN_PR
title: Fix Latency Guards and Boost Mean Revert Confidence
scope: Tuning constants for execution readiness
requested_paths:
  - config/config.py
  - strategies/trade_builder.py
allowed_paths:
  - config/config.py
  - strategies/trade_builder.py
forbidden_paths:
  - main.py
  - run_live.sh
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
expected_tests:
  - pytest tests/test_trade_builder.py
  - pytest tests/test_engine_phase2_adapter.py
acceptance_proof:
  - Latency bounds safely relaxed for paper/sim/soak to avoid false-positive halts without touching LIVE variables.
  - Mean reversion quality base score and multiplier boosted, proving higher candidate confidence selection.
  - All unit tests pass cleanly after branch isolation from outdated PR history.
