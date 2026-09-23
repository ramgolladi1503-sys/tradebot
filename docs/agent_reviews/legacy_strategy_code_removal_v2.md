mode: READ_ONLY
candidate_id: legacy_strategy_code_removal_v2
decision: HERMES_DESIGN_APPROVED_PENDING_PHASE1_GREEN
reason: Define dependency-safe physical retirement of negative legacy heuristic strategies after Phase 1 authority cleanup.
timestamp: 2026-09-23T05:45:00+05:30
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: docs/agent_reviews/legacy_strategy_code_removal_v2.md

# Legacy Strategy Code Removal V2

## Agent Work Contract

- source_agent: hermes
- action: DESIGN_ARCHITECTURE
- title: Legacy strategy physical code/test removal with current-pipeline preservation
- scope: Physically retire negative legacy heuristic implementations and their dedicated research/tests only where a fresh dependency audit proves they are not part of the current governed/shadow/live path. Preserve shared runtime and defensive infrastructure.
- prerequisite: PR #931 Phase 1 required CI green and merged before implementation.
- requested_paths:
  - legacy strategy modules under strategies/**
  - legacy research/backtest/replay-only modules directly coupled to them
  - core/strategy_spec.py
  - core/strategy_parameter_profiles.py where no retained consumer remains
  - core/replay_candidate_handoff_entrypoint.py only to remove dead strategy adapters while preserving generic replay infrastructure
  - strategies/movement/__init__.py
  - implementation-specific tests for retired modules
  - generic strategy-spec tests only as needed to remove assumptions that retired strategies are active
  - docs/strategy_truth/legacy_strategy_tombstones_v1.json
  - docs/strategy_truth/legacy_strategy_runtime_reachability_v2.json
  - this review and GSD review
- forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - core/read_only_strategy_registry.py
  - core/causal_strategy_harness.py
  - current frozen candidate specs
  - current CAS/C1/C2/MEG implementation logic
- expected_tests:
  - all surviving strategy registry/spec contract tests
  - candidate safety tests
  - current read-only live pipeline tests
  - frozen candidate tests
  - full required repository CI
- acceptance_proof:
  - deleted implementation has zero current governed/shadow/live runtime dependency
  - dedicated deleted tests are not generic safety/pipeline tests
  - current live/read-only strategy registry hash unchanged
  - current causal strategy harness hash unchanged
  - no broker/order/risk/feed/live changes
  - retained shared infrastructure remains importable
  - required CI green

## Scope Guard

The purpose is repository hygiene after negative legacy closure, not strategy redesign.

The physical-delete boundary must be evidence-driven.

Allowed:
- remove dead heuristic implementation code;
- remove offline-only replay/backtest wrappers that cannot function without retired strategies;
- remove strategy-specific tests for deleted implementations;
- prune metadata/default specs so retired strategies cannot reappear as candidate metadata;
- add anti-resurrection assertions.

Forbidden:
- threshold retuning;
- strategy replacement;
- modifying frozen prospective strategies;
- deleting defensive no-trade behavior;
- removing shared helper code used by current read-only observation;
- weakening generic safety/ranking/replay tests.

Safety:
```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```

## Grill Me Review

Challenge: Why not just delete every file under strategies that failed?

Because several historical strategy files now serve as shared implementation dependencies. Current `core/causal_strategy_harness.py` imports `strategies.trade_builder.TradeBuilder`, and TradeBuilder imports helper functions from `strategies.ensemble`. Deleting those files would alter the current live/read-only observation path.

Challenge: Why keep NO_TRADE_CHOP after negative strategy closure?

It is a defensive no-trade filter, not a profit-seeking alpha strategy, and is directly referenced by `core/candidate_pool_orchestrator.py`. Removing it would weaken a safety path.

Challenge: Why preserve MEG?

MEG remains the current governed read-only shadow/advisory path and is outside the negative legacy-alpha deletion boundary.

Challenge: Can generic tests that mention old IDs be deleted?

No. A test is removed only when its sole purpose is the retired implementation. Candidate ranking, execution firewall, observability, replay integrity, feed safety and generic strategy-contract tests must be preserved, converting fixtures to neutral IDs where necessary.

Verdict: deletion must be selective.

## Hermes Review

### Retain as current/shared infrastructure

- `strategies/trade_builder.py`: current causal strategy harness dependency.
- `strategies/ensemble.py`: imported by TradeBuilder as signal/helper functions; de-authorized as a strategy but retained as shared support.
- `strategies/movement/no_trade_chop.py`: current defensive candidate-pool dependency.
- `strategies/movement/market_event_graph_reversal.py`: current MEG shadow/advisory path.
- `strategies/movement/_utils.py`: retained if used by MEG/no-trade.
- generic candidate/ranking/observability/execution-firewall infrastructure.

### Strong physical-retirement candidates

Movement heuristics:
- strategies/movement/opening_drive.py
- strategies/movement/opening_range_breakout.py
- strategies/movement/compression_breakout.py
- strategies/movement/trend_pullback.py
- strategies/movement/vwap_reclaim.py
- strategies/movement/failed_breakout_trap.py
- strategies/movement/exhaustion_reversal.py
- strategies/movement/mean_reversion_extension.py
- strategies/movement/event_volatility_expansion.py
- strategies/movement/late_day_momentum.py
- strategies/movement/option_pressure.py

Top-level legacy strategy implementations:
- strategies/simple_orb.py
- strategies/vwap_orb.py
- strategies/nifty_intraday.py
- strategies/banknifty_intraday.py
- strategies/sensex_intraday.py
- strategies/pairs_arbitrage.py
- strategies/zero_hero.py
- strategies/volatility_trend.py

Legacy Pro layer, if final search confirms no retained runtime consumer:
- strategies/pro_layer/pro_strategy_engine.py
- strategies/pro_layer/pro_decision_adapter.py

### Legacy research/backtest tooling to retire

Phase 1 already removes fixed-metric:
- scripts/run_candidate_strategy_backtest.py
- scripts/run_candidate_strategy_wfa.py

Phase 2 must audit and normally retire the old broad directional-proxy campaign:
- scripts/backtest_all_strategies_available_data.py
- scripts/analyze_all_available_strategy_edge.py
- its dedicated test

Also remove old strategy-specific replay/audit helpers whose only executable dependency is a retired strategy, including opening-range-retest and old VWAP/ORB replays, but retain immutable historical result/docs.

### Metadata

`core/strategy_spec.py` currently advertises many retired strategies to generic metadata-only candidate tooling. Phase 2 should remove retired alpha specs while preserving at least the defensive no-trade contract and generic contract machinery.

`core/strategy_parameter_profiles.py` is used only by the legacy movement implementations plus old opening-range replay according to current code search. If all consumers are retired, delete this profile module and its dedicated tests rather than retain orphan parameter authority.

`core/strategy_regime_policy.py` is retained because current opportunity scoring imports it. Legacy alias entries may remain strictly for historical compatibility unless they create candidate authority; they are not execution authority.

## GSD Review

GSD may begin physical deletion only after Phase 1 PR #931:
- required `unit_tests` green;
- required health gate green;
- agent review evidence green;
- code excellence green;
- merged to main.

Implementation should proceed in dependency batches, running CI after each logical batch where practical.

No file may be deleted solely because its filename resembles a rejected strategy.

## QA / Safety Review

Required invariants after deletion:

```text
core/read_only_strategy_registry.py unchanged
core/causal_strategy_harness.py unchanged
C1/C2/CAS frozen identities unchanged
MEG shadow path retained
NO_TRADE_CHOP retained
TradeBuilder retained
broker/order/risk/feed paths unchanged
```

New anti-resurrection tests must prove retired strategy modules/IDs are not discoverable by current authority or default metadata candidate pools.

Import smoke must prove current runtime modules still import.

## Acceptance Proof

1. Phase 1 merged.
2. Reachability artifact complete.
3. Every deleted module classified `NO_CURRENT_GOVERNED_SHADOW_LIVE_DEPENDENCY`.
4. Generic tests retained or refactored.
5. Dedicated implementation tests removed.
6. Historical evidence retained.
7. Required GitHub CI green.
8. No current frozen hashes changed.
9. No broker/order/risk/feed/live authority changed.

## Runtime Proof Required After Merge

No market-hours run is required merely to delete unreachable legacy strategy code.

A post-merge offline import/contract smoke must prove:
- current read-only observer imports;
- current candidate safety tests;
- current frozen candidate tests;
- current MEG path;
- current no-trade safety path.

A later live session must not be relabeled as proof of this code cleanup.

## What This PR Does Not Prove

This cleanup does not prove:
- structural edge;
- profitability;
- live readiness;
- that a retained shared helper is a certified strategy;
- that historical negative results were caused by one mechanism;
- that data-blocked ideas are economically dead.

It only closes negative legacy strategy code where dependency safety is proven.

## Human Approval

The project owner explicitly requested autonomous removal of the negative legacy heuristic strategies, their respective implementation-only tests, and legacy backtest paths while preserving current TradeBot behavior.

## High-Risk Path Review

This phase intentionally touches `strategies/**`, a high-risk repository area.

Mitigations:
- user approval is explicit;
- current live registry/harness are protected and unchanged;
- TradeBuilder/ensemble are retained because they are current dependencies;
- NO_TRADE_CHOP and MEG are retained;
- deletions are gated by reachability evidence;
- no thresholds are modified;
- no new trading behavior is added;
- every failure is fail-closed through removal of authority rather than substitution.
