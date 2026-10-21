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
    """Legacy heuristic movement strategies are intentionally de-authorized."""

    return []


def load_strategy_registry() -> Dict[str, StrategyRegistryEntry]:
    """Residual registry for shadow/advisory and non-strategy audit helpers only.

    Rejected or uncertified legacy heuristic strategies are intentionally absent
    so old certification/replay tooling cannot rediscover them as candidates.
    """

    registry: Dict[str, StrategyRegistryEntry] = {}

    registry["MARKET_EVENT_GRAPH_REVERSAL"] = StrategyRegistryEntry(
        strategy_id="MARKET_EVENT_GRAPH_REVERSAL",
        module_path="strategies/movement/market_event_graph_reversal.py",
        strategy_kind="candidate_generator_strategy",
        instrument_family="EQUITY_INDEX_OPTIONS",
        callable_name="generate_market_event_graph_reversal_candidates",
        certification_supported=False,
        certification_track="shadow_live_observation_only",
        blocked_reason=(
            "Shadow/advisory only; no broker/order authority and no "
            "structural-edge certification."
        ),
    )

    helpers = {
        "RISK_MANAGER": "strategies/risk_manager.py",
        "POSITION_SIZER": "strategies/position_sizer.py",
        "SOFT_SIGNAL": "strategies/soft_signal.py",
        "PRO_DECISION_ADAPTER": "strategies/pro_layer/pro_decision_adapter.py",
    }
    for strategy_id, module_path in helpers.items():
        registry[strategy_id] = StrategyRegistryEntry(
            strategy_id=strategy_id,
            module_path=module_path,
            strategy_kind="helper_module",
            instrument_family="N/A",
            callable_name="",
            certification_supported=False,
            certification_track="not_certifiable",
            blocked_reason="Helper module; not a trading strategy",
        )

    registry["TEST_STRAT"] = StrategyRegistryEntry(
        strategy_id="TEST_STRAT",
        module_path="strategies/test_strat.py",
        strategy_kind="test_fixture",
        instrument_family="N/A",
        callable_name="",
        certification_supported=False,
        certification_track="not_certifiable",
        blocked_reason="Test fixture excluded from production",
    )

    return registry


registry = load_strategy_registry()
