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

    # C1 and C2 are strictly the only active approved execution strategies
    assert is_strategy_governed_eligible("C1") is True
    assert is_strategy_governed_eligible("C2") is True


def test_event_and_panic_strictly_blocked():
    # EVENT is DATA_BLOCKED / NOT HISTORICALLY VALIDATED
    assert resolve_strategy_authority("EVENT") == StrategyGovernanceStatus.UNAPPROVED
    assert is_strategy_governed_eligible("EVENT") is False

    # PANIC is DATA_BLOCKED / NOT HISTORICALLY VALIDATED
    assert resolve_strategy_authority("PANIC") == StrategyGovernanceStatus.UNAPPROVED
    assert is_strategy_governed_eligible("PANIC") is False

    # Broad families without standalone strategy certification default to UNAPPROVED
    for family in ["TREND", "MOMENTUM", "BREAKOUT", "MEAN_REVERT", "DEFINED_RISK"]:
        assert resolve_strategy_authority(family) == StrategyGovernanceStatus.UNAPPROVED
        assert is_strategy_governed_eligible(family) is False

    # Prove neither EVENT nor PANIC can alter governed rank or execution selection
    event_cand = {"symbol": "NIFTY", "strategy_id": "EVENT", "score": 999.0}
    panic_cand = {"symbol": "NIFTY", "strategy_id": "PANIC", "score": 999.0}
    c1_cand = {"symbol": "NIFTY", "strategy_id": "C1", "score": 85.0}

    governed, rejected = filter_governed_candidates([event_cand, panic_cand, c1_cand], trace_id="test-trace-event")
    assert len(governed) == 1
    assert governed[0]["strategy_id"] == "C1"
    assert len(rejected) == 2
    assert {r["strategy_id"] for r in rejected} == {"EVENT", "PANIC"}


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


def test_validate_execution_candidate():
    from core.governed_strategy_authority import validate_execution_candidate

    assert validate_execution_candidate({"strategy_id": "C1"}) is True
    assert validate_execution_candidate({"strategy_id": "C2"}) is True
    assert validate_execution_candidate({"strategy_id": "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE"}) is True
    assert validate_execution_candidate({"strategy_id": "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT"}) is True

    # Blocked strategies must raise PermissionError
    for blocked_id in ["EVENT", "PANIC", "TREND", "MOMENTUM", "CAS", "MACD", "expiry_lotto", "zero_hero", "scalp", "unknown"]:
        with pytest.raises(PermissionError):
            validate_execution_candidate({"strategy_id": blocked_id})


def test_production_catalog_integrity():
    """
    Explicit Production-Catalog Integrity Test (Section 4).
    Verifies that ONLY C1 and C2 canonical IDs and aliases are ACTIVE_APPROVED in production.
    TEST, EVENT, PANIC, broad families, shadow, research, and superseded strategies
    must NEVER acquire production governed authority.
    """
    from core.governed_strategy_authority import (
        GOVERNED_STRATEGY_CATALOG,
        StrategyGovernanceStatus,
        resolve_strategy_authority,
        is_strategy_governed_eligible,
        validate_execution_candidate,
    )

    # 1. Enumerate all ACTIVE_APPROVED strategies in the catalog
    active_approved_entries = {
        strat_id: data
        for strat_id, data in GOVERNED_STRATEGY_CATALOG.items()
        if data["status"] == StrategyGovernanceStatus.ACTIVE_APPROVED
    }

    # Expected canonical IDs and aliases for C1 and C2
    expected_c1_c2_entries = {
        "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
        "C1_INTRADAY_15M_IMPULSE",
        "C1",
        "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
        "C2_OVERNIGHT_TREND",
        "C2",
    }

    assert set(active_approved_entries.keys()) == expected_c1_c2_entries, (
        f"VIOLATION: Production catalog contains unexpected ACTIVE_APPROVED strategies: "
        f"{set(active_approved_entries.keys()) - expected_c1_c2_entries}"
    )

    # 2. Strict negative checks on unauthorized strategies
    negative_checks = [
        "TEST",
        "EVENT",
        "PANIC",
        "TREND",
        "MOMENTUM",
        "BREAKOUT",
        "MEAN_REVERT",
        "DEFINED_RISK",
        "CAS",
        "MACD",
        "expiry_lotto",
        "zero_hero",
        "scalp",
        "unknown",
        "rogue_trader",
    ]

    for strat_id in negative_checks:
        assert resolve_strategy_authority(strat_id) != StrategyGovernanceStatus.ACTIVE_APPROVED, (
            f"Strategy {strat_id} must NOT be ACTIVE_APPROVED in production catalog"
        )
        assert is_strategy_governed_eligible(strat_id) is False, (
            f"Strategy {strat_id} must NOT be governed eligible"
        )
        with pytest.raises(PermissionError):
            validate_execution_candidate({"strategy_id": strat_id})


def test_temporary_test_strategy_authority_isolation():
    """
    Proves that temporary_test_strategy_authority allows TEST only within its context,
    reverts state immediately upon exit, and does not mutate production catalog.
    """
    from core.governed_strategy_authority import (
        temporary_test_strategy_authority,
        resolve_strategy_authority,
        is_strategy_governed_eligible,
        validate_execution_candidate,
        StrategyGovernanceStatus,
    )

    # Pre-condition: TEST is unapproved
    assert resolve_strategy_authority("TEST") == StrategyGovernanceStatus.UNAPPROVED
    assert is_strategy_governed_eligible("TEST") is False
    with pytest.raises(PermissionError):
        validate_execution_candidate({"strategy_id": "TEST"})

    # Inside context: TEST is temporarily allowed
    with temporary_test_strategy_authority({"TEST"}):
        assert resolve_strategy_authority("TEST") == StrategyGovernanceStatus.ACTIVE_APPROVED
        assert is_strategy_governed_eligible("TEST") is True
        assert validate_execution_candidate({"strategy_id": "TEST"}) is True

        # Other unauthorized strategies remain blocked even inside context
        assert resolve_strategy_authority("EVENT") == StrategyGovernanceStatus.UNAPPROVED
        with pytest.raises(PermissionError):
            validate_execution_candidate({"strategy_id": "EVENT"})

    # Post-condition: TEST is strictly unapproved again
    assert resolve_strategy_authority("TEST") == StrategyGovernanceStatus.UNAPPROVED
    assert is_strategy_governed_eligible("TEST") is False
    with pytest.raises(PermissionError):
        validate_execution_candidate({"strategy_id": "TEST"})
