mode: READ_ONLY
source_agent: hermes
action: DESIGN_ARCHITECTURE
title: Legacy strategy decommission phase 1 — authority removal and synthetic backtest invalidation
scope: Remove rejected legacy strategies from the old certification registry, remove synthetic legacy backtest/WFA executables and their dedicated tests, add tombstones and anti-resurrection coverage. Do not delete strategy implementation modules in this phase.
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
allowed_paths:
  - files listed above only
forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - core/runtime_safety_boot_guard.py
  - current frozen candidate specs
  - PR #930 files
expected_tests:
  - tests/test_strategy_registry.py
  - tests/test_legacy_strategy_decommission.py
  - repository required CI
acceptance_proof:
  - rejected legacy strategies absent from legacy certification registry
  - MEG remains shadow/advisory-only
  - helper/test-fixture registry behavior retained
  - synthetic backtest/WFA scripts removed
  - dedicated tests for those synthetic scripts removed
  - tombstone list exists
  - anti-resurrection test proves removed IDs are not registry-reachable
  - no broker/order/risk/feed/live paths changed

# Hermes Architecture

## Problem

The repository contains an old certification registry that still exposes rejected or uncertified heuristic strategies. Separately, two legacy scripts named as backtest/WFA runners emit fixed economic metrics when basic preconditions pass rather than deriving those metrics from real event/trade ledgers. Keeping these paths available creates two risks:

1. a rejected strategy can be rediscovered through old audit tooling and appear certifiable;
2. synthetic economic outputs can be mistaken for backtest evidence.

This phase removes those authorities without deleting implementation modules yet.

## Safety boundary

This phase is registration/evidence cleanup only.

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

No strategy thresholds are changed.

## Phase split

### Phase 1 — this PR

- remove rejected legacy strategies from `strategies/strategy_registry.py`;
- retain only MEG shadow/advisory registration plus non-strategy helpers/test fixture needed by old audit tooling;
- delete `scripts/run_candidate_strategy_backtest.py`;
- delete `scripts/run_candidate_strategy_wfa.py`;
- delete their two dedicated tests, which only assert shape of legacy artifacts;
- add a tombstone manifest;
- add anti-resurrection tests.

### Phase 2 — follow-up only after Phase 1 CI proves isolation

Build an import/call-graph inventory for the physical strategy modules. Delete implementation files and implementation-specific tests only when each file has zero current governed/shadow/runtime dependency. Shared safety/ranking/replay tests must be retained and converted to neutral fixtures where needed.

## Decommission set for Phase 1

The old registry must no longer expose:

- SIMPLE_ORB
- HTF_OPENING_DRIVE_CONT
- MEAN_REVERSION_EXTENSION
- COMPRESSION_BREAKOUT
- TREND_PULLBACK
- VWAP_RECLAIM
- OPENING_DRIVE
- FAILED_BREAKOUT_TRAP
- EXHAUSTION_REVERSAL
- EVENT_VOLATILITY_EXPANSION
- LATE_DAY_MOMENTUM
- OPTION_PRESSURE
- OPENING_RANGE_BREAKOUT
- NO_TRADE_CHOP
- PRO_STRATEGY_ENGINE
- ENSEMBLE
- TRADE_BUILDER
- NIFTY_INTRADAY
- BANKNIFTY_INTRADAY
- SENSEX_INTRADAY
- VWAP_ORB
- ZERO_HERO
- PAIRS_ARBITRAGE
- VOLATILITY_TREND

These IDs are not current governed execution authority.

## Explicitly preserved

- MARKET_EVENT_GRAPH_REVERSAL remains shadow/advisory-only;
- RISK_MANAGER, POSITION_SIZER, SOFT_SIGNAL and PRO_DECISION_ADAPTER remain registered only as non-strategy helper modules for legacy tooling;
- TEST_STRAT remains a test fixture;
- all current C1/C2/CAS/MEG/frozen prospective implementations remain untouched;
- no physical strategy implementation files are deleted in this phase.

## Evidence integrity

The removed backtest/WFA scripts contain fixed economic outputs. Historical reports produced by those scripts are not deleted here because history should not be silently rewritten. The tombstone manifest records that these two runners are invalidated as evidence generators.

## Acceptance gates

1. Registry contains no decommissioned strategy ID.
2. MEG is present and `certification_supported == false`.
3. MEG track remains `shadow_live_observation_only`.
4. Helper modules are non-certifiable.
5. Test fixture remains excluded.
6. Legacy synthetic backtest/WFA files do not exist.
7. No changed file belongs to broker/order/risk/feed/live execution paths.
8. Required GitHub CI passes before merge.
9. PR #930 remains separate; this cleanup must not merge before #930 integration is resolved.
