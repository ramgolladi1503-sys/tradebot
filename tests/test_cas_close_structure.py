from datetime import datetime, time

import pytest

from core.cas_close_structure import (
    PHASE_CAS_MATCHING,
    PHASE_CAS_ORDER_DISCOVERY,
    PHASE_CAS_RANDOM_CLOSE_WINDOW,
    PHASE_CAS_REFERENCE_TRANSITION,
    PHASE_DERIVATIVE_CONVERGENCE,
    PHASE_NORMAL_CONTINUOUS,
    PHASE_POST_CLOSE,
    build_cas_close_observation,
    cas_research_readiness,
    classify_nse_close_phase,
    normal_strategy_entry_allowed,
    normal_strategy_position_may_cross_cas,
)


def at(hh, mm, ss=0, *, day=4):
    return datetime(2026, 8, day, hh, mm, ss)


def test_new_nse_cash_boundaries():
    assert classify_nse_close_phase(at(15, 14, 59), segment="NSE_EQ") == PHASE_NORMAL_CONTINUOUS
    assert classify_nse_close_phase(at(15, 15), segment="NSE_EQ") == PHASE_CAS_REFERENCE_TRANSITION
    assert classify_nse_close_phase(at(15, 20), segment="NSE_EQ") == PHASE_CAS_ORDER_DISCOVERY
    assert classify_nse_close_phase(at(15, 25), segment="NSE_EQ") == PHASE_CAS_RANDOM_CLOSE_WINDOW
    assert classify_nse_close_phase(at(15, 30), segment="NSE_EQ") == PHASE_CAS_MATCHING
    assert classify_nse_close_phase(at(15, 35), segment="NSE_EQ") == PHASE_POST_CLOSE


def test_derivatives_continue_after_cash_matching_only_to_1540():
    assert classify_nse_close_phase(at(15, 35), segment="NSE_FNO") == PHASE_DERIVATIVE_CONVERGENCE
    assert classify_nse_close_phase(at(15, 39, 59), segment="NSE_FNO") == PHASE_DERIVATIVE_CONVERGENCE
    assert classify_nse_close_phase(at(15, 40), segment="NSE_FNO") == PHASE_POST_CLOSE


def test_legacy_replay_before_effective_date_keeps_1530_close():
    assert classify_nse_close_phase(at(15, 20, day=2), segment="NSE_FNO") == PHASE_NORMAL_CONTINUOUS
    assert classify_nse_close_phase(at(15, 30, day=2), segment="NSE_FNO") == PHASE_POST_CLOSE


def test_normal_strategy_cutoff_and_cas_crossing_are_fail_closed():
    assert normal_strategy_entry_allowed(at(15, 5), last_normal_entry=time(15, 5))
    assert not normal_strategy_entry_allowed(at(15, 5, 1), last_normal_entry=time(15, 5))
    assert not normal_strategy_entry_allowed(at(15, 20))
    assert normal_strategy_position_may_cross_cas(at(15, 0), planned_hold_minutes=20)
    assert not normal_strategy_position_may_cross_cas(at(14, 45), planned_hold_minutes=20)
    with pytest.raises(ValueError):
        normal_strategy_position_may_cross_cas(at(15, 0), planned_hold_minutes=-1)


def test_broad_auction_repricing_is_observation_not_trade():
    returns = [0.8] * 48 + [-0.3, -0.7]
    observation = build_cas_close_observation(
        session_date="2026-08-04",
        pre_match_index=24463.45,
        matched_index=24614.90,
        constituent_returns_pct=returns,
    )
    assert observation.evidence_class == "BROAD_AUCTION_REPRICING"
    assert observation.diagnostic_direction == "UP"
    assert observation.positive_constituents == 48
    assert observation.execution_eligible is False
    readiness = cas_research_readiness(observation)
    assert readiness["predictive_cas_hypothesis_testable"] is False
    assert readiness["execution_eligible"] is False
    assert "INDICATIVE_CLOSE_REVISION_SERIES" in readiness["missing_authoritative_inputs"]


def test_predictive_readiness_requires_all_four_inputs():
    observation = build_cas_close_observation(
        session_date="2026-08-04",
        pre_match_index=100.0,
        matched_index=101.0,
        constituent_returns_pct=[1.0] * 10,
        indicative_revision_series_available=True,
        auction_imbalance_available=True,
        futures_available=True,
        real_option_contracts_available=True,
    )
    readiness = cas_research_readiness(observation)
    assert readiness["predictive_cas_hypothesis_testable"] is True
    assert readiness["execution_eligible"] is False
