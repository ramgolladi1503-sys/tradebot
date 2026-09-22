mode: READ_ONLY
source_agent: gsd
action: GENERATE_PATCH
title: Legacy strategy decommission phase 1 — implementation and verification record
scope: Implement the Hermes contract in docs/agent_reviews/legacy_strategy_decommission_v1.md.
requested_paths:
  - strategies/strategy_registry.py
  - scripts/run_candidate_strategy_backtest.py
  - scripts/run_candidate_strategy_wfa.py
  - tests/test_strategy_registry.py
  - tests/test_candidate_strategy_backtest.py
  - tests/test_candidate_strategy_wfa.py
  - tests/test_legacy_strategy_decommission.py
  - docs/strategy_truth/legacy_strategy_tombstones_v1.json
  - docs/agent_reviews/legacy_strategy_decommission_v1.md
  - docs/agent_reviews/legacy_strategy_decommission_v1_gsd.md
allowed_paths:
  - files listed above only
forbidden_paths:
  - broker/order/risk/feed/live runtime paths
  - current frozen strategy specs
  - PR #930 files
expected_tests:
  - tests/test_strategy_registry.py
  - tests/test_legacy_strategy_decommission.py
  - required GitHub CI
acceptance_proof:
  - compare against main shows only declared files
  - synthetic backtest/WFA runners removed
  - decommissioned legacy IDs absent from old certification registry
  - MEG remains shadow/advisory only
  - no implementation module deleted in phase 1
  - no broker/order/risk/feed/live path changed

# GSD Implementation Record

## What changed

- Removed rejected/uncertified legacy strategy IDs from the old certification registry.
- Retained only:
  - MARKET_EVENT_GRAPH_REVERSAL as shadow/advisory-only;
  - RISK_MANAGER, POSITION_SIZER, SOFT_SIGNAL, PRO_DECISION_ADAPTER as non-strategy helpers;
  - TEST_STRAT as a test-only fixture.
- Removed the two legacy scripts that generated fixed synthetic economic metrics:
  - scripts/run_candidate_strategy_backtest.py
  - scripts/run_candidate_strategy_wfa.py
- Removed the two dedicated shallow artifact tests tied to those scripts.
- Added docs/strategy_truth/legacy_strategy_tombstones_v1.json.
- Added tests/test_legacy_strategy_decommission.py.
- Rewrote tests/test_strategy_registry.py to assert anti-resurrection behavior.

## Why this moves safety/evidence quality forward

The old registry could make rejected or uncertified strategy code appear eligible for legacy certification workflows. The removed backtest/WFA scripts could emit deterministic economic numbers without deriving them from trade ledgers. Removing both paths prevents accidental promotion through stale tooling while preserving historical artifacts.

## What did not change

- No physical strategy implementation module was deleted in phase 1.
- C1/C2/CAS logic was not changed.
- MEG implementation was not changed.
- Current frozen shadow/prospective candidates were not changed.
- No broker, order, execution, risk, feed or live-authority file was touched.
- No strategy threshold was changed.
- Historical runtime evidence files were not rewritten.

## Phase 2 gate

Implementation files and implementation-specific tests may be deleted only after:
1. phase 1 CI is green;
2. a fresh import/call-graph audit proves zero current governed/shadow/runtime dependency;
3. shared pipeline/safety tests are separated from implementation-only tests;
4. PR #930 is integrated into main or the cleanup is rebased after it.

## Safety

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
broker_write_authority=false
order_authority=false
ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```
