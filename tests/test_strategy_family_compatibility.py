"""Comprehensive Test Suite for Strategy Family Architecture & Compatibility Gate.

Covers:
- StrategyFamily and StrategySubfamily parsing, aliases, and immutability.
- Canonical Strategy Registry (C1, C2, and standard strategies).
- Negative Controls (NC1 - NC10):
  NC1: Candidate family is None -> FAMILY_MISSING
  NC2: Candidate family is unknown string -> FAMILY_UNKNOWN
  NC3: Allowed families set is empty -> REGIME_FAMILY_SET_EMPTY
  NC4: Allowed families set contains only invalid entries -> REGIME_FAMILY_SET_EMPTY
  NC5: Candidate family TREND against RANGE regime {"MEAN_REVERT"} -> FAMILY_MISMATCH
  NC6: Candidate family MEAN_REVERT against TREND regime {"TREND"} -> FAMILY_MISMATCH
  NC7: Candidate family SCALP_ONLY against DEFINED_RISK regime {"DEFINED_RISK"} -> FAMILY_MISMATCH
  NC8: Candidate family DEFINED_RISK against TREND regime {"TREND"} -> FAMILY_MISMATCH
  NC9: Candidate family NO_TRADE against TREND regime {"TREND"} -> FAMILY_MISMATCH
  NC10: Candidate family TREND against NO_TRADE regime {"NO_TRADE"} -> FAMILY_MISMATCH
- Non-Mutation Assertions:
  Candidate family identity must never be mutated to force compatibility with any regime.
- Compatibility & Admission Flow:
  - C1 (TREND) under TREND regime -> FAMILY_COMPATIBLE -> Handed off to pool.
  - C1 (TREND) under RANGE regime -> FAMILY_MISMATCH -> Not admitted to pool.
  - C2 (TREND) under TREND regime -> FAMILY_COMPATIBLE -> Handed off to pool.
  - C2 (TREND) under RANGE regime -> FAMILY_MISMATCH -> Not admitted to pool.
- Zero Execution Authority Invariants:
  - is_order_action = False
  - broker_write_authority = False
  - orders_placed = 0
"""

from __future__ import annotations

import pytest

from core.candidate_evaluators import (
    CandidateEmission,
    evaluate_c1,
    evaluate_c2,
)
from core.market_session_store import MarketMemorySnapshot
from core.observability import (
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    generate_trace_id,
)
from core.strategy_family_contract import (
    STRATEGY_REGISTRY,
    StrategyDefinition,
    StrategyFamily,
    StrategySubfamily,
    check_strategy_family_compatibility,
    resolve_strategy_family,
)


# =============================================================================
# 1. StrategyFamily & Subfamily Contract Tests
# =============================================================================

def test_strategy_family_values_and_aliases():
    """Verify canonical family values and alias parsing."""
    assert StrategyFamily.TREND.value == "TREND"
    assert StrategyFamily.MEAN_REVERT.value == "MEAN_REVERT"
    assert StrategyFamily.DEFINED_RISK.value == "DEFINED_RISK"
    assert StrategyFamily.SCALP_ONLY.value == "SCALP_ONLY"
    assert StrategyFamily.NO_TRADE.value == "NO_TRADE"

    # Aliases
    assert StrategyFamily.from_str("TRENDING") == StrategyFamily.TREND
    assert StrategyFamily.from_str("trend-continuation") == StrategyFamily.TREND
    assert StrategyFamily.from_str("DIRECTIONAL") == StrategyFamily.TREND
    assert StrategyFamily.from_str("BREAKOUT") == StrategyFamily.TREND
    assert StrategyFamily.from_str("MEAN_REVERSION") == StrategyFamily.MEAN_REVERT
    assert StrategyFamily.from_str("range") == StrategyFamily.MEAN_REVERT
    assert StrategyFamily.from_str("EVENT") == StrategyFamily.DEFINED_RISK
    assert StrategyFamily.from_str("scalp") == StrategyFamily.SCALP_ONLY
    assert StrategyFamily.from_str("NONE") == StrategyFamily.NO_TRADE
    assert StrategyFamily.from_str(None) is None
    assert StrategyFamily.from_str("INVALID_XYZ") is None


def test_strategy_subfamily_values_and_aliases():
    """Verify subfamily values and parsing."""
    assert StrategySubfamily.MOMENTUM_IMPULSE.value == "MOMENTUM_IMPULSE"
    assert StrategySubfamily.OVERNIGHT_TREND.value == "OVERNIGHT_TREND"
    assert StrategySubfamily.BREAKOUT.value == "BREAKOUT"
    assert StrategySubfamily.CONTINUATION.value == "CONTINUATION"

    assert StrategySubfamily.from_str("momentum-impulse") == StrategySubfamily.MOMENTUM_IMPULSE
    assert StrategySubfamily.from_str("overnight_trend") == StrategySubfamily.OVERNIGHT_TREND
    assert StrategySubfamily.from_str(None) is None
    assert StrategySubfamily.from_str("UNKNOWN_SUB") is None


def test_strategy_registry_c1_c2():
    """Verify C1 and C2 definitions in canonical registry."""
    assert "C1_INTRADAY_15M_IMPULSE" in STRATEGY_REGISTRY
    c1_def = STRATEGY_REGISTRY["C1_INTRADAY_15M_IMPULSE"]
    assert c1_def.strategy_family == StrategyFamily.TREND
    assert c1_def.strategy_subfamily == StrategySubfamily.MOMENTUM_IMPULSE
    assert c1_def.is_order_action is False
    assert c1_def.broker_write_authority is False

    assert "C2_OVERNIGHT_TREND" in STRATEGY_REGISTRY
    c2_def = STRATEGY_REGISTRY["C2_OVERNIGHT_TREND"]
    assert c2_def.strategy_family == StrategyFamily.TREND
    assert c2_def.strategy_subfamily == StrategySubfamily.OVERNIGHT_TREND
    assert c2_def.is_order_action is False
    assert c2_def.broker_write_authority is False


# =============================================================================
# 2. Negative Controls (NC1 - NC10)
# =============================================================================

def test_nc1_candidate_family_is_none():
    """NC1: Candidate family is None -> FAMILY_MISSING."""
    res = check_strategy_family_compatibility(None, {"TREND"})
    assert res.compatible is False
    assert res.candidate_family is None
    assert res.reason_code == "FAMILY_MISSING"


def test_nc2_candidate_family_is_unknown():
    """NC2: Candidate family is unknown string -> FAMILY_UNKNOWN."""
    res = check_strategy_family_compatibility("NONEXISTENT_FAMILY_XYZ", {"TREND"})
    assert res.compatible is False
    assert res.candidate_family is None
    assert res.reason_code == "FAMILY_UNKNOWN"


def test_nc3_allowed_families_set_empty():
    """NC3: Allowed families set is empty -> REGIME_FAMILY_SET_EMPTY."""
    res = check_strategy_family_compatibility(StrategyFamily.TREND, set())
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.TREND
    assert res.reason_code == "REGIME_FAMILY_SET_EMPTY"


def test_nc4_allowed_families_set_invalid():
    """NC4: Allowed families set contains only unresolvable values -> REGIME_FAMILY_SET_EMPTY."""
    res = check_strategy_family_compatibility(StrategyFamily.TREND, {"GARBAGE_1", "GARBAGE_2"})
    assert res.compatible is False
    assert res.reason_code == "REGIME_FAMILY_SET_EMPTY"


def test_nc5_trend_candidate_vs_range_regime():
    """NC5: Candidate family TREND against RANGE regime {"MEAN_REVERT"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.TREND, {"MEAN_REVERT"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.TREND
    assert res.allowed_families == frozenset({StrategyFamily.MEAN_REVERT})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc6_mean_revert_candidate_vs_trend_regime():
    """NC6: Candidate family MEAN_REVERT against TREND regime {"TREND"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.MEAN_REVERT, {"TREND"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.MEAN_REVERT
    assert res.allowed_families == frozenset({StrategyFamily.TREND})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc7_scalp_candidate_vs_defined_risk_regime():
    """NC7: Candidate family SCALP_ONLY against DEFINED_RISK regime {"DEFINED_RISK"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.SCALP_ONLY, {"DEFINED_RISK"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.SCALP_ONLY
    assert res.allowed_families == frozenset({StrategyFamily.DEFINED_RISK})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc8_defined_risk_candidate_vs_trend_regime():
    """NC8: Candidate family DEFINED_RISK against TREND regime {"TREND"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.DEFINED_RISK, {"TREND"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.DEFINED_RISK
    assert res.allowed_families == frozenset({StrategyFamily.TREND})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc9_no_trade_candidate_vs_trend_regime():
    """NC9: Candidate family NO_TRADE against TREND regime {"TREND"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.NO_TRADE, {"TREND"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.NO_TRADE
    assert res.allowed_families == frozenset({StrategyFamily.TREND})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc10_trend_candidate_vs_no_trade_regime():
    """NC10: Candidate family TREND against NO_TRADE regime {"NO_TRADE"} -> FAMILY_MISMATCH."""
    res = check_strategy_family_compatibility(StrategyFamily.TREND, {"NO_TRADE"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.TREND
    assert res.allowed_families == frozenset({StrategyFamily.NO_TRADE})
    assert res.reason_code == "FAMILY_MISMATCH"


def test_nc11_duplicate_candidate_admission_rejected():
    """NC11: Candidate with duplicate candidate_id rejected by admit_candidate_to_pool."""
    from core.strategy_family_contract import admit_candidate_to_pool
    pool: list[dict] = []
    cand = CandidateEmission(
        candidate_id="DUP_TEST_ID",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="trace_dup",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )
    compat = check_strategy_family_compatibility(cand.strategy_family, ["TREND"])
    assert admit_candidate_to_pool(pool, cand, compatibility_result=compat) is True
    # Duplicate insertion fails
    assert admit_candidate_to_pool(pool, cand, compatibility_result=compat) is False
    assert len(pool) == 1


def test_nc12_incompatible_or_unadmitted_candidate_never_reaches_advisory():
    """NC12: Incompatible candidate cannot enter pool, cannot be ranked, cannot reach advisory."""
    from unittest.mock import patch
    from core.strategy_family_contract import admit_candidate_to_pool
    from core.engine_phase2_adapter import run_engine_phase2
    from core.orchestrator import _build_top_opportunities_payload

    cand = CandidateEmission(
        candidate_id="INCOMPAT_ADVISORY_TEST",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="trace_incompat",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )
    pool: list[dict] = []
    # Gate allows only MEAN_REVERT
    compat = check_strategy_family_compatibility(cand.strategy_family, ["MEAN_REVERT"])
    assert compat.compatible is False
    assert admit_candidate_to_pool(pool, cand, compatibility_result=compat) is False
    assert len(pool) == 0

    mock_feed = {
        "valid": True,
        "payload": {
            "feed_ok": True,
            "last_tick_age_sec": 0.5,
            "last_depth_age_sec": 1.0,
        },
    }
    with patch("core.engine_phase2_adapter.load_current_feed_runtime", return_value=mock_feed):
        res = run_engine_phase2(pool, top_n=5)
        assert len(res.get("ranked", [])) == 0
        payload = _build_top_opportunities_payload(candidates=pool, advisory_top_n=5)
        assert len(payload.get("top_advisory_opportunities", [])) == 0



# =============================================================================
# 3. Non-Mutation & C1/C2 Compatibility Assertions
# =============================================================================

def test_candidate_family_non_mutation_invariant():
    """Candidate family identity must NEVER mutate to match regime."""
    cand = CandidateEmission(
        candidate_id="TEST_CAND_01",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="test_trace",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )

    # In Range regime
    range_allowed = frozenset({"MEAN_REVERT"})
    res = check_strategy_family_compatibility(cand.strategy_family, range_allowed)
    assert res.compatible is False
    assert res.reason_code == "FAMILY_MISMATCH"

    # Ensure cand.strategy_family was not mutated
    assert cand.strategy_family == "TREND"
    assert cand.strategy_subfamily == "MOMENTUM_IMPULSE"


def test_c1_compatible_under_trend_regime():
    """C1 (TREND) under TREND regime -> FAMILY_COMPATIBLE."""

    mem = MarketMemorySnapshot(
        as_of_timestamp="2026-09-11 10:00:00+05:30",
        symbol="NIFTY",
        current_price=23300.0,
        session_open=23240.0,
        session_high=23350.0,
        session_low=23200.0,
        session_close=23300.0,
        bar_index=45,
        rolling_1m_bars_count=45,
        derived_5m_bars_count=9,
        derived_15m_bars_count=3,
        rolling_15m_return_bps=55.0,
        distance_from_session_open_bps=25.8,
        rolling_15m_range_bps=12.0,
        realized_vol_15m=3.0,
        freshness_watermark=1.0,
        persistence_watermark=1.0,
        trace_id="c1_test_trace",
    )
    res_c1 = evaluate_c1(mem, as_of_timestamp="2026-09-11 10:00:00+05:30", trace_id="c1_test_trace")
    assert res_c1.qualified is True
    assert res_c1.candidate is not None
    assert res_c1.candidate.strategy_family == StrategyFamily.TREND.value
    assert res_c1.candidate.strategy_subfamily == StrategySubfamily.MOMENTUM_IMPULSE.value

    res = check_strategy_family_compatibility(res_c1.candidate.strategy_family, {"TREND", "BREAKOUT"})
    assert res.compatible is True
    assert res.candidate_family == StrategyFamily.TREND
    assert res.reason_code == "FAMILY_COMPATIBLE"


def test_c2_compatible_under_trend_regime():
    """C2 (TREND) under TREND regime -> FAMILY_COMPATIBLE."""

    mem = MarketMemorySnapshot(
        as_of_timestamp="2026-09-11 15:12:00+05:30",
        symbol="NIFTY",
        current_price=23419.0,
        session_open=23240.65,
        session_high=23430.0,
        session_low=23220.0,
        session_close=23419.0,
        bar_index=357,
        rolling_1m_bars_count=357,
        derived_5m_bars_count=71,
        derived_15m_bars_count=23,
        rolling_15m_return_bps=12.5,
        distance_from_session_open_bps=76.74,
        rolling_15m_range_bps=15.0,
        realized_vol_15m=4.5,
        freshness_watermark=1.0,
        persistence_watermark=1.0,
        trace_id="c2_test_trace",
    )
    res_c2 = evaluate_c2(mem, as_of_timestamp="2026-09-11 15:12:00+05:30", trace_id="c2_test_trace")
    assert res_c2.qualified is True
    assert res_c2.candidate is not None
    assert res_c2.candidate.strategy_family == StrategyFamily.TREND.value
    assert res_c2.candidate.strategy_subfamily == StrategySubfamily.OVERNIGHT_TREND.value

    res = check_strategy_family_compatibility(res_c2.candidate.strategy_family, {"TREND"})
    assert res.compatible is True
    assert res.candidate_family == StrategyFamily.TREND
    assert res.reason_code == "FAMILY_COMPATIBLE"



def test_c2_incompatible_under_range_regime():
    """C2 (TREND) under RANGE regime (like 2026-09-11 at 15:12) -> FAMILY_MISMATCH."""
    # On 2026-09-11 15:12 IST, regime is RANGE -> allowed_strategy_families = {"MEAN_REVERT"}
    res = check_strategy_family_compatibility("TREND", {"MEAN_REVERT"})
    assert res.compatible is False
    assert res.candidate_family == StrategyFamily.TREND
    assert res.reason_code == "FAMILY_MISMATCH"


# =============================================================================
# 4. Lifecycle Ledger Transition & Attribution Verification
# =============================================================================

def test_ledger_transition_on_family_mismatch():
    """Ledger accurately transitions candidate to REGIME_CHECK / FILTERED with FAMILY_MISMATCH."""
    ledger = CandidateLifecycleLedger()
    t_id = generate_trace_id(seed="test_mismatch")
    cand_id = "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT"

    ledger.record_transition(
        candidate_id=cand_id,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.REGIME_CHECK,
        status="FILTERED",
        reason_code="FAMILY_MISMATCH",
        metadata={
            "trace_id": t_id,
            "candidate_family": "TREND",
            "allowed_families": ["MEAN_REVERT"],
        },
    )

    records = ledger.get_candidate_history(cand_id)
    assert len(records) == 1
    assert records[0].from_stage == CandidateLifecycleStage.CREATED
    assert records[0].to_stage == CandidateLifecycleStage.REGIME_CHECK
    assert records[0].status == "FILTERED"
    assert records[0].reason_code == "FAMILY_MISMATCH"
    assert records[0].metadata["candidate_family"] == "TREND"
    assert records[0].metadata["allowed_families"] == ["MEAN_REVERT"]


def test_ledger_transition_on_family_compatible():
    """Ledger accurately transitions candidate to REGIME_CHECK / PASS with FAMILY_COMPATIBLE."""
    ledger = CandidateLifecycleLedger()
    t_id = generate_trace_id(seed="test_compatible")
    cand_id = "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE"

    ledger.record_transition(
        candidate_id=cand_id,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.REGIME_CHECK,
        status="PASS",
        reason_code="FAMILY_COMPATIBLE",
        metadata={
            "trace_id": t_id,
            "candidate_family": "TREND",
            "allowed_families": ["TREND"],
        },
    )

    records = ledger.get_candidate_history(cand_id)
    assert len(records) == 1
    assert records[0].from_stage == CandidateLifecycleStage.CREATED
    assert records[0].to_stage == CandidateLifecycleStage.REGIME_CHECK
    assert records[0].status == "PASS"
    assert records[0].reason_code == "FAMILY_COMPATIBLE"


# =============================================================================
# 5. Safety & Authority Invariants
# =============================================================================

def test_zero_execution_authority_invariants():
    """Ensure zero order authority across all family architecture objects."""
    for strat_id, defn in STRATEGY_REGISTRY.items():
        assert defn.is_order_action is False
        assert defn.broker_write_authority is False
        assert defn.paper_authorized is False
        assert defn.live_authorized is False

    # resolve_strategy_family fails closed to NO_TRADE for unknown strategy
    assert resolve_strategy_family("UNKNOWN_STRATEGY_XYZ") == StrategyFamily.NO_TRADE

    # StrategyDefinition fails closed if order authority flags are asserted
    with pytest.raises(ValueError, match="strategy_definition_order_action_forbidden"):
        StrategyDefinition(
            strategy_id="UNSAFE_ORDER",
            strategy_family=StrategyFamily.TREND,
            is_order_action=True,
        )

    with pytest.raises(ValueError, match="strategy_definition_broker_write_forbidden"):
        StrategyDefinition(
            strategy_id="UNSAFE_BROKER",
            strategy_family=StrategyFamily.TREND,
            broker_write_authority=True,
        )

    # GateResult default allowed_strategy_families when allowed=False or family=None
    from core.strategy_gatekeeper import GateResult
    gr_blocked = GateResult(allowed=False, family="TREND", reasons=["test_block"])
    assert gr_blocked.allowed_strategy_families == frozenset()
    gr_none = GateResult(allowed=True, family=None, reasons=[])
    assert gr_none.allowed_strategy_families == frozenset()

    # Orchestrator candidate_visibility_bucket guarantees
    from core.orchestrator_truth import candidate_visibility_bucket
    cand_adv = {"candidate_status": "advisory_only", "execution_status": "advisory_only", "permission": "ADVISORY_ONLY"}
    assert candidate_visibility_bucket(cand_adv) == "advisory"
    assert candidate_visibility_bucket(cand_adv) != "visible"



def test_orchestrator_c1_c2_handoff_integration():
    """Verify orchestrator admission & filtering integration for C1/C2 under TREND vs RANGE."""
    from core.orchestrator import _check_strategy_family_compatibility
    from core.strategy_gatekeeper import GateResult
    from core.candidate_evaluators import CandidateEmission

    c1 = CandidateEmission(
        candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="trace_test_c1",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )

    c2 = CandidateEmission(
        candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
        strategy_id="C2_OVERNIGHT_TREND",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 15:12:00+05:30",
        entry_boundary="EXACT_1514_OPEN",
        exit_boundary="NEXT_SESSION_OPEN",
        stop_rule="SESSION_OPEN_STOP",
        trace_id="trace_test_c2",
        features={"distance_from_session_open_bps": 64.0},
        strategy_family="TREND",
        strategy_subfamily="OVERNIGHT_TREND",
    )

    # 1. Gate allowing TREND
    gate_trend = GateResult(
        allowed=True,
        family="TREND",
        allowed_strategy_families=frozenset({"TREND"}),
        reasons=[],
    )

    compat_c1_trend = _check_strategy_family_compatibility(c1.strategy_family, gate_trend.allowed_strategy_families)
    assert compat_c1_trend.compatible is True
    assert compat_c1_trend.reason_code == "FAMILY_COMPATIBLE"

    compat_c2_trend = _check_strategy_family_compatibility(c2.strategy_family, gate_trend.allowed_strategy_families)
    assert compat_c2_trend.compatible is True
    assert compat_c2_trend.reason_code == "FAMILY_COMPATIBLE"

    # 2. Gate allowing only RANGE (MEAN_REVERT) - like 2026-09-11 at 15:12
    gate_range = GateResult(
        allowed=True,
        family="RANGE",
        allowed_strategy_families=frozenset({"MEAN_REVERT"}),
        reasons=[],
    )

    compat_c1_range = _check_strategy_family_compatibility(c1.strategy_family, gate_range.allowed_strategy_families)
    assert compat_c1_range.compatible is False
    assert compat_c1_range.reason_code == "FAMILY_MISMATCH"

    compat_c2_range = _check_strategy_family_compatibility(c2.strategy_family, gate_range.allowed_strategy_families)
    assert compat_c2_range.compatible is False
    assert compat_c2_range.reason_code == "FAMILY_MISMATCH"


def test_20260911_replay_c2_at_1512_filtered_by_family_mismatch():
    """Exact Causal Replay Proof for 2026-09-11 at 15:12 IST.

    Historical facts:
    - Session Open: 23240.65
    - Spot at 15:12: 23419.0 -> +76.74 bps (>= +50.0 bps threshold -> C2 qualifies!)
    - Regime at 15:12: RANGE -> allowed_strategy_families = {"MEAN_REVERT"}
    - Candidate family: TREND
    - Result: Candidate qualifies, but compatibility gate blocks admission with FAMILY_MISMATCH.
    - Lifecycle ledger records transition: CREATED -> REGIME_CHECK / FILTERED / FAMILY_MISMATCH.
    - Candidate is NOT falsely admitted into the candidate pool.
    """
    from core.candidate_evaluators import C2ReasonCode
    from core.strategy_gatekeeper import GateResult

    session_open = 23240.65
    spot_1512 = 23419.0
    trend_bps = (spot_1512 - session_open) / session_open * 10000.0

    memory = MarketMemorySnapshot(
        as_of_timestamp="2026-09-11 15:12:00+05:30",
        symbol="NIFTY",
        current_price=spot_1512,
        session_open=session_open,
        session_high=23430.0,
        session_low=23220.0,
        session_close=spot_1512,
        bar_index=357,
        rolling_1m_bars_count=357,
        derived_5m_bars_count=71,
        derived_15m_bars_count=23,
        rolling_15m_return_bps=12.5,
        distance_from_session_open_bps=trend_bps,
        rolling_15m_range_bps=15.0,
        realized_vol_15m=4.5,
        freshness_watermark=1.0,
        persistence_watermark=1.0,
        trace_id="trace_sep11_replay_1512",
    )

    c2_res = evaluate_c2(memory, as_of_timestamp="2026-09-11 15:12:00+05:30", trace_id="trace_sep11_replay_1512")
    assert c2_res.qualified is True
    assert c2_res.reason_code == C2ReasonCode.C2_QUALIFIED.value
    assert c2_res.candidate is not None
    assert c2_res.candidate.strategy_family == "TREND"

    # Historical regime: RANGE
    gate_range = GateResult(
        allowed=True,
        family="RANGE",
        allowed_strategy_families=frozenset({"MEAN_REVERT"}),
        reasons=[],
    )

    compat = check_strategy_family_compatibility(c2_res.candidate.strategy_family, gate_range.allowed_strategy_families)
    assert compat.compatible is False
    assert compat.reason_code == "FAMILY_MISMATCH"

    # Verify lifecycle transition
    ledger = CandidateLifecycleLedger()
    ledger.record_transition(
        candidate_id=c2_res.candidate.candidate_id,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.REGIME_CHECK,
        status="FILTERED",
        reason_code=compat.reason_code,
        metadata={
            "trace_id": c2_res.candidate.trace_id,
            "candidate_family": compat.candidate_family.value,
            "allowed_families": [f.value for f in compat.allowed_families],
            "session_date": "2026-09-11",
            "regime": "RANGE",
        },
    )
    records = ledger.get_candidate_history(c2_res.candidate.candidate_id)
    assert len(records) == 1
    assert records[0].status == "FILTERED"
    assert records[0].reason_code == "FAMILY_MISMATCH"
    assert records[0].metadata["regime"] == "RANGE"


def test_admit_candidate_to_pool_contract():
    """Verify admit_candidate_to_pool enforces compatibility, deduplication, and zero order authority."""
    from core.strategy_family_contract import admit_candidate_to_pool
    from core.candidate_evaluators import CandidateEmission

    pool: list[dict] = []
    c1 = CandidateEmission(
        candidate_id="ENTRY_C1_POOL_TEST",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="trace_test_pool_c1",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )

    # 1. Reject incompatible candidate
    compat_incompat = check_strategy_family_compatibility(c1.strategy_family, ["MEAN_REVERT"])
    assert compat_incompat.compatible is False
    admitted = admit_candidate_to_pool(pool, c1, compatibility_result=compat_incompat)
    assert admitted is False
    assert len(pool) == 0

    # 2. Admit compatible candidate
    compat_ok = check_strategy_family_compatibility(c1.strategy_family, ["TREND"])
    assert compat_ok.compatible is True
    admitted = admit_candidate_to_pool(pool, c1, compatibility_result=compat_ok)
    assert admitted is True
    assert len(pool) == 1
    admitted_item = pool[0]
    assert admitted_item["candidate_id"] == "ENTRY_C1_POOL_TEST"
    assert admitted_item["strategy_family"] == "TREND"
    assert admitted_item["is_order_action"] is False
    assert admitted_item["broker_write_authority"] is False
    assert admitted_item["permission"] == "ADVISORY_ONLY"
    assert admitted_item["final_action"] == "ADVISORY_ONLY"

    # 3. Reject duplicate candidate
    admitted_dup = admit_candidate_to_pool(pool, c1, compatibility_result=compat_ok)
    assert admitted_dup is False
    assert len(pool) == 1


def test_ranking_and_advisory_handoff_contract():
    """Verify unadmitted candidate cannot be ranked, and admitted candidate reaches advisory."""
    from unittest.mock import patch
    from core.strategy_family_contract import admit_candidate_to_pool
    from core.candidate_evaluators import CandidateEmission
    from core.engine_phase2_adapter import run_engine_phase2
    from core.orchestrator import _build_top_opportunities_payload

    c1 = CandidateEmission(
        candidate_id="C1_RANK_TEST",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 10:00:00+05:30",
        entry_boundary="NEXT_BAR_OPEN",
        exit_boundary="SESSION_CLOSE",
        stop_rule="40BPS_FIXED",
        trace_id="trace_test_c1",
        features={"rolling_15m_return_bps": 55.0},
        strategy_family="TREND",
        strategy_subfamily="MOMENTUM_IMPULSE",
    )
    c2 = CandidateEmission(
        candidate_id="C2_ADVISORY_TEST",
        strategy_id="C2_OVERNIGHT_TREND",
        symbol="NIFTY",
        signal_timestamp="2026-09-11 15:12:00+05:30",
        entry_boundary="EXACT_1514_OPEN",
        exit_boundary="NEXT_SESSION_OPEN",
        stop_rule="SESSION_OPEN_STOP",
        trace_id="trace_test_c2",
        features={"distance_from_session_open_bps": 64.0},
        strategy_family="TREND",
        strategy_subfamily="OVERNIGHT_TREND",
    )

    # Empty pool: neither candidate admitted
    unadmitted_pool: list[dict] = []
    mock_feed = {
        "valid": True,
        "payload": {
            "feed_ok": True,
            "last_tick_age_sec": 0.5,
            "last_depth_age_sec": 1.0,
        },
    }

    with patch("core.engine_phase2_adapter.load_current_feed_runtime", return_value=mock_feed):
        res_empty = run_engine_phase2(unadmitted_pool, top_n=5)
        assert len(res_empty.get("ranked", [])) == 0
        top_empty = _build_top_opportunities_payload(candidates=unadmitted_pool, advisory_top_n=5)
        assert len(top_empty.get("top_advisory_opportunities", [])) == 0

        # Admitted pool: C1 and C2 admitted under TREND
        admitted_pool: list[dict] = []
        compat1 = check_strategy_family_compatibility(c1.strategy_family, ["TREND"])
        compat2 = check_strategy_family_compatibility(c2.strategy_family, ["TREND"])
        assert admit_candidate_to_pool(admitted_pool, c1, compatibility_result=compat1) is True
        assert admit_candidate_to_pool(admitted_pool, c2, compatibility_result=compat2) is True

        res_admitted = run_engine_phase2(admitted_pool, top_n=5)
        ranked_ids = [r["trade_id"] for r in res_admitted.get("ranked", [])]
        assert "C1_RANK_TEST" in ranked_ids or "C2_ADVISORY_TEST" in ranked_ids

        top_admitted = _build_top_opportunities_payload(candidates=admitted_pool, advisory_top_n=5)
        adv_ids = [r["trade_id"] for r in top_admitted.get("top_advisory_opportunities", [])]
        assert len(adv_ids) > 0
        # Preserves canonical family identity
        for adv_row in top_admitted.get("top_advisory_opportunities", []):
            assert adv_row.get("strategy_family") == "TREND"

