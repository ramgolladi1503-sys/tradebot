import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict

@dataclass
class StrategyRegistryEntry:
    strategy_id: str
    module_path: str
    strategy_kind: str
    instrument_family: str
    callable_name: str
    certification_supported: bool
    certification_track: str
    blocked_reason: str = ""

def get_movement_strategies() -> list[str]:
    return [
        "MEAN_REVERSION_EXTENSION",
        "COMPRESSION_BREAKOUT",
        "TREND_PULLBACK",
        "VWAP_RECLAIM",
        "OPENING_DRIVE",
        "FAILED_BREAKOUT_TRAP",
        "EXHAUSTION_REVERSAL",
        "EVENT_VOLATILITY_EXPANSION",
        "LATE_DAY_MOMENTUM",
        "OPTION_PRESSURE",
        "OPENING_RANGE_BREAKOUT",
        "NO_TRADE_CHOP"
    ]

def load_strategy_registry() -> Dict[str, StrategyRegistryEntry]:
    registry = {}
    
    # 1. Execution strategies
    registry["SIMPLE_ORB"] = StrategyRegistryEntry(
        strategy_id="SIMPLE_ORB",
        module_path="strategies/simple_orb.py",
        strategy_kind="execution_signal_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_signals",
        certification_supported=True,
        certification_track="phase_1_to_5_execution_replay",
        blocked_reason=""
    )
    
    registry["HTF_OPENING_DRIVE_CONT"] = StrategyRegistryEntry(
        strategy_id="HTF_OPENING_DRIVE_CONT",
        module_path="strategies/htf_opening_drive_cont.py",
        strategy_kind="execution_signal_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_signals",
        certification_supported=True,
        certification_track="phase_1_to_5_execution_replay",
        blocked_reason=""
    )
    
    # 2. Movement strategies (candidate generators)
    for ms in get_movement_strategies():
        registry[ms] = StrategyRegistryEntry(
            strategy_id=ms,
            module_path=f"strategies/movement/{ms.lower()}.py",
            strategy_kind="candidate_generator_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name=f"generate_{ms.lower()}_candidates",
            certification_supported=True,
            certification_track="candidate_generator_contract_only",
            blocked_reason=""
        )

    registry["MARKET_EVENT_GRAPH_REVERSAL"] = StrategyRegistryEntry(
        strategy_id="MARKET_EVENT_GRAPH_REVERSAL",
        module_path="strategies/movement/market_event_graph_reversal.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_market_event_graph_reversal_candidates",
        certification_supported=False,
        certification_track="shadow_live_observation_only",
        blocked_reason="Underlying-only discovery; actual option premium validation and independent certification pending."
    )

    registry["H1_TRAPPED_PUSH_SNAPBACK_SHADOW"] = StrategyRegistryEntry(
        strategy_id="H1_TRAPPED_PUSH_SNAPBACK_SHADOW",
        module_path="strategies/shadow/h1_trapped_push_snapback.py",
        strategy_kind="shadow_trade_intent_strategy",
        instrument_family="NIFTY_INDEX_OPTION_SHADOW_UNROUTED",
        callable_name="generate_shadow_trade_intents",
        certification_supported=True,
        certification_track="offline_shadow_certification_only",
        blocked_reason="Shadow trade-intent emission only. Not execution viable; no broker writes, no paper orders, no live orders."
    )
        
    # 3. Aggregate Engine
    registry["PRO_STRATEGY_ENGINE"] = StrategyRegistryEntry(
        strategy_id="PRO_STRATEGY_ENGINE",
        module_path="strategies/pro_layer/pro_strategy_engine.py",
        strategy_kind="aggregate_engine",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="run",
        certification_supported=True,
        certification_track="aggregate_engine_certification",
        blocked_reason=""
    )
    
    # 4. Deferred
    registry["ENSEMBLE"] = StrategyRegistryEntry(
        strategy_id="ENSEMBLE",
        module_path="strategies/ensemble.py",
        strategy_kind="deferred",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_signals",
        certification_supported=False,
        certification_track="not_certifiable",
        blocked_reason="Ensemble strategies must wait for children."
    )
    
    # 5. Helper modules
    helpers = ["TRADE_BUILDER", "RISK_MANAGER", "POSITION_SIZER", "SOFT_SIGNAL", "PRO_DECISION_ADAPTER", "NIFTY_INTRADAY", "BANKNIFTY_INTRADAY", "SENSEX_INTRADAY", "VWAP_ORB", "ZERO_HERO", "PAIRS_ARBITRAGE", "VOLATILITY_TREND"]
    for h in helpers:
        registry[h] = StrategyRegistryEntry(
            strategy_id=h,
            module_path=f"strategies/{h.lower()}.py" if not h == "PRO_DECISION_ADAPTER" else "strategies/pro_layer/pro_decision_adapter.py",
            strategy_kind="helper_module",
            instrument_family="N/A",
            callable_name="",
            certification_supported=False,
            certification_track="not_certifiable",
            blocked_reason="Helper module"
        )
        
    # Exclude TEST_STRAT from production
    registry["TEST_STRAT"] = StrategyRegistryEntry(
        strategy_id="TEST_STRAT",
        module_path="strategies/test_strat.py",
        strategy_kind="test_fixture",
        instrument_family="N/A",
        callable_name="",
        certification_supported=False,
        certification_track="not_certifiable",
        blocked_reason="Test fixture excluded from production"
    )
        
    return registry

registry = load_strategy_registry()
