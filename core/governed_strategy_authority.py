"""
Governed Strategy Authority & Candidate Gatekeeper.

Authoritative classification and candidate pool filtering for strategies.
Enforces that only ACTIVE_APPROVED strategies enter governed candidate pools
and ranking in SIM, PAPER, or LIVE modes.
Superseded, Shadow-only, Research-only, and unknown strategies are strictly blocked
from governed ranking outputs.
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class StrategyGovernanceStatus(str, Enum):
    ACTIVE_APPROVED = "ACTIVE_APPROVED"
    SHADOW_ONLY = "SHADOW_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SUPERSEDED = "SUPERSEDED"
    UNAPPROVED = "UNAPPROVED"


# Canonical strategy authority catalog
GOVERNED_STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    # Active Approved Strategies (C1 and C2)
    "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE": {
        "alias": "C1",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Intraday 15m Momentum Impulse with Trailing Stop",
    },
    "C1_INTRADAY_15M_IMPULSE": {
        "alias": "C1",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Intraday 15m Momentum Impulse (Evaluator ID)",
    },
    "C1": {
        "alias": "C1",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Intraday 15m Momentum Impulse (Alias)",
    },
    "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT": {
        "alias": "C2",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Overnight Trend 15:12 Signal 15:14 Entry Open Exit",
    },
    "C2_OVERNIGHT_TREND": {
        "alias": "C2",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Overnight Trend (Evaluator ID)",
    },
    "C2": {
        "alias": "C2",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Nifty Overnight Trend (Alias)",
    },
    # Production Engine Tradable Families (Base Tradable Strategies)
    "TREND": {
        "alias": "TREND",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Trend Strategy Family",
    },
    "MOMENTUM": {
        "alias": "MOMENTUM",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Momentum Strategy Family",
    },
    "BREAKOUT": {
        "alias": "BREAKOUT",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Breakout Strategy Family",
    },
    "MEAN_REVERT": {
        "alias": "MEAN_REVERT",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Mean Reversion Strategy Family",
    },
    "DEFINED_RISK": {
        "alias": "DEFINED_RISK",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Defined Risk Strategy Family",
    },
    "EVENT": {
        "alias": "EVENT",
        "status": StrategyGovernanceStatus.ACTIVE_APPROVED,
        "eligible_for_governed_ranking": True,
        "eligible_for_execution": True,
        "description": "Core Event Strategy Family",
    },
    # Shadow-Only Strategies (CAS)
    "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1": {
        "alias": "CAS",
        "status": StrategyGovernanceStatus.SHADOW_ONLY,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "CAS Morning Reversal Short Horizon Advisory (Shadow Only)",
    },
    "CAS": {
        "alias": "CAS",
        "status": StrategyGovernanceStatus.SHADOW_ONLY,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "CAS Morning Reversal Short Horizon Advisory (Alias)",
    },
    # Research-Only Strategies (MACD)
    "MACD_FUTURES_EXECUTION_RESEARCH": {
        "alias": "MACD",
        "status": StrategyGovernanceStatus.RESEARCH_ONLY,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "MACD Futures Execution Research Model (Research Only)",
    },
    "MACD": {
        "alias": "MACD",
        "status": StrategyGovernanceStatus.RESEARCH_ONLY,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "MACD Research Model (Alias)",
    },
    # Superseded Auxiliary Strategies (explicitly blocked)
    "expiry_lotto": {
        "alias": "expiry_lotto",
        "status": StrategyGovernanceStatus.SUPERSEDED,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "Superseded Expiry Lotto Exploration",
    },
    "zero_hero": {
        "alias": "zero_hero",
        "status": StrategyGovernanceStatus.SUPERSEDED,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "Superseded Zero-to-Hero Exploration",
    },
    "scalp": {
        "alias": "scalp",
        "status": StrategyGovernanceStatus.SUPERSEDED,
        "eligible_for_governed_ranking": False,
        "eligible_for_execution": False,
        "description": "Superseded Micro-Scalp Exploration",
    },
}


def resolve_strategy_authority(strategy_id: Optional[str]) -> StrategyGovernanceStatus:
    """
    Resolve the governance status of a strategy by its ID or alias.
    Defaults to UNAPPROVED if not recognized in catalog.
    """
    if not strategy_id:
        return StrategyGovernanceStatus.UNAPPROVED
    
    clean_id = str(strategy_id).strip()
    entry = GOVERNED_STRATEGY_CATALOG.get(clean_id)
    if entry:
        return entry["status"]
    
    # Check case-insensitive / partial match
    clean_id_lower = clean_id.lower()
    for cat_id, data in GOVERNED_STRATEGY_CATALOG.items():
        if cat_id.lower() == clean_id_lower:
            return data["status"]
            
    return StrategyGovernanceStatus.UNAPPROVED


def is_strategy_governed_eligible(strategy_id: Optional[str]) -> bool:
    """
    Returns True ONLY if strategy is ACTIVE_APPROVED and eligible for governed ranking.
    """
    status = resolve_strategy_authority(strategy_id)
    return status == StrategyGovernanceStatus.ACTIVE_APPROVED


def extract_candidate_strategy_id(candidate: Any) -> Optional[str]:
    """
    Safely extract strategy_id / strategy name from a candidate object or dictionary.
    """
    if candidate is None:
        return None
    if isinstance(candidate, dict):
        return (
            candidate.get("strategy_id")
            or candidate.get("strategy")
            or candidate.get("strategy_name")
            or candidate.get("strategy_family")
            or candidate.get("family")
            or candidate.get("name")
        )
    return (
        getattr(candidate, "strategy_id", None)
        or getattr(candidate, "strategy", None)
        or getattr(candidate, "strategy_name", None)
        or getattr(candidate, "strategy_family", None)
        or getattr(candidate, "family", None)
        or getattr(candidate, "name", None)
    )


def filter_governed_candidates(
    candidates: List[Any],
    trace_id: Optional[str] = None,
    emit_audit_event: bool = False
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """
    Filters candidates, allowing ONLY ACTIVE_APPROVED strategies through.
    Returns:
        (governed_candidates, rejected_audit_records)
    """
    governed: List[Any] = []
    rejected: List[Dict[str, Any]] = []

    for cand in candidates:
        strat_id = extract_candidate_strategy_id(cand)
        status = resolve_strategy_authority(strat_id)
        if status == StrategyGovernanceStatus.ACTIVE_APPROVED:
            governed.append(cand)
        else:
            rejection = {
                "trace_id": trace_id,
                "strategy_id": strat_id,
                "status": status.value,
                "reason": f"Strategy {strat_id} with status {status.value} is not ACTIVE_APPROVED",
            }
            rejected.append(rejection)

    return governed, rejected
