from __future__ import annotations

from typing import Any

from .contracts import StrategyId


FINAL_STRATEGY_KEYS = (
    "IMPLEMENTED_EXACTLY",
    "CAUSALITY",
    "CANDIDATE_COUNT",
    "OCCURRENCE_PROBABILITY",
    "15M_RESULT",
    "30M_RESULT",
    "60M_RESULT",
    "CLOSE_RESULT",
    "CHRONOLOGICAL_WFA",
    "MATCHED_CONTROL",
    "NEGATIVE_CONTROLS",
    "DELAY_SENSITIVITY",
    "CONCENTRATION",
    "PARAMETER_NEIGHBOURHOOD",
    "UNDERLYING_EDGE_VERDICT",
    "OPTION_REPLAY_VERDICT",
    "30_MINUTE_COMPATIBILITY",
    "PROSPECTIVE_STATUS",
    "FINAL_STRATEGY_VERDICT",
)


def insufficient_data_strategy_verdict(strategy_id: StrategyId) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id.value,
        "IMPLEMENTED_EXACTLY": True,
        "CAUSALITY": "NEXT_BAR_ENTRY_ONLY",
        "CANDIDATE_COUNT": 0,
        "OCCURRENCE_PROBABILITY": 0.0,
        "15M_RESULT": "INSUFFICIENT_DATA",
        "30M_RESULT": "INSUFFICIENT_DATA",
        "60M_RESULT": "INSUFFICIENT_DATA",
        "CLOSE_RESULT": "INSUFFICIENT_DATA",
        "CHRONOLOGICAL_WFA": "INSUFFICIENT_DATA",
        "MATCHED_CONTROL": "INSUFFICIENT_DATA",
        "NEGATIVE_CONTROLS": "INSUFFICIENT_DATA",
        "DELAY_SENSITIVITY": "INSUFFICIENT_DATA",
        "CONCENTRATION": "INSUFFICIENT_DATA",
        "PARAMETER_NEIGHBOURHOOD": "INSUFFICIENT_DATA",
        "UNDERLYING_EDGE_VERDICT": "INSUFFICIENT_DATA",
        "OPTION_REPLAY_VERDICT": "INSUFFICIENT_DATA",
        "30_MINUTE_COMPATIBILITY": "FAIL_PRODUCTION_COMPATIBILITY",
        "PROSPECTIVE_STATUS": "NOT_STARTED",
        "FINAL_STRATEGY_VERDICT": "INSUFFICIENT_DATA",
    }


def suite_verdict(strategy_verdicts: list[dict[str, Any]]) -> str:
    certified = [v for v in strategy_verdicts if v.get("FINAL_STRATEGY_VERDICT") == "CERTIFIED_UNDERLYING_STRUCTURAL_EDGE"]
    if not certified:
        return "CERTIFY_NONE"
    if len(certified) == 1:
        return "CERTIFY_ONE"
    return "CERTIFY_MULTIPLE_WITH_ROUTER"

