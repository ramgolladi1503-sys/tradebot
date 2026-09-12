import pytest
from core.governed_strategy_authority import (
    StrategyGovernanceStatus,
    resolve_strategy_authority,
    is_strategy_governed_eligible,
    filter_governed_candidates,
    extract_candidate_strategy_id,
)

def test_active_approved_strategies():
    # C1 variants
    assert resolve_strategy_authority("ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("C1_INTRADAY_15M_IMPULSE") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("C1") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert is_strategy_governed_eligible("C1") is True

    # C2 variants
    assert resolve_strategy_authority("ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("C2_OVERNIGHT_TREND") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("C2") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert is_strategy_governed_eligible("C2") is True

    # Base tradable families
    assert resolve_strategy_authority("TREND") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("MOMENTUM") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("BREAKOUT") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("MEAN_REVERT") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("DEFINED_RISK") == StrategyGovernanceStatus.ACTIVE_APPROVED
    assert resolve_strategy_authority("EVENT") == StrategyGovernanceStatus.ACTIVE_APPROVED


def test_shadow_only_strategies():
    assert resolve_strategy_authority("CAS_MORNING_REVERSAL_SHORT_HORIZON_V1") == StrategyGovernanceStatus.SHADOW_ONLY
    assert resolve_strategy_authority("CAS") == StrategyGovernanceStatus.SHADOW_ONLY
    assert is_strategy_governed_eligible("CAS") is False


def test_research_only_strategies():
    assert resolve_strategy_authority("MACD_FUTURES_EXECUTION_RESEARCH") == StrategyGovernanceStatus.RESEARCH_ONLY
    assert resolve_strategy_authority("MACD") == StrategyGovernanceStatus.RESEARCH_ONLY
    assert is_strategy_governed_eligible("MACD") is False


def test_superseded_and_unknown_strategies():
    assert resolve_strategy_authority("expiry_lotto") == StrategyGovernanceStatus.SUPERSEDED
    assert resolve_strategy_authority("zero_hero") == StrategyGovernanceStatus.SUPERSEDED
    assert resolve_strategy_authority("scalp") == StrategyGovernanceStatus.SUPERSEDED
    assert resolve_strategy_authority("random_unregistered_strat") == StrategyGovernanceStatus.UNAPPROVED
    assert resolve_strategy_authority(None) == StrategyGovernanceStatus.UNAPPROVED
    assert is_strategy_governed_eligible("expiry_lotto") is False
    assert is_strategy_governed_eligible("unknown") is False


def test_candidate_filtering_and_mutation_defense():
    c1_cand = {"symbol": "NIFTY", "strategy_id": "C1", "score": 95.0}
    c2_cand = {"symbol": "NIFTY", "strategy_id": "C2", "score": 90.0}
    cas_cand = {"symbol": "NIFTY", "strategy_id": "CAS", "score": 99.0}
    macd_cand = {"symbol": "NIFTY", "strategy_id": "MACD", "score": 98.0}
    lotto_cand = {"symbol": "NIFTY", "strategy_id": "expiry_lotto", "score": 100.0}
    scalp_cand = {"symbol": "NIFTY", "strategy_id": "scalp", "score": 85.0}
    unknown_cand = {"symbol": "BANKNIFTY", "strategy_id": "rogue_ai", "score": 120.0}

    pool = [c1_cand, cas_cand, lotto_cand, c2_cand, macd_cand, scalp_cand, unknown_cand]

    governed, rejected = filter_governed_candidates(pool, trace_id="test-trace-123")

    # Only C1 and C2 should pass
    assert len(governed) == 2
    assert governed[0]["strategy_id"] == "C1"
    assert governed[1]["strategy_id"] == "C2"

    # All others must be recorded in rejected list
    assert len(rejected) == 5
    rejected_strategies = {r["strategy_id"] for r in rejected}
    assert rejected_strategies == {"CAS", "MACD", "expiry_lotto", "scalp", "rogue_ai"}

    # Mutation test: Verify superseded/shadow candidates cannot alter the top rank
    all_sorted = sorted(pool, key=lambda x: x["score"], reverse=True)
    assert all_sorted[0]["strategy_id"] == "rogue_ai"  # if unfiltered, rogue would win

    governed_sorted = sorted(governed, key=lambda x: x["score"], reverse=True)
    assert governed_sorted[0]["strategy_id"] == "C1"  # with governance, C1 wins
