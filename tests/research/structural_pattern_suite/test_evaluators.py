from __future__ import annotations

import pytest

from research.structural_pattern_suite.contracts import Bar, PreviousSession, Side, StrategyId
from research.structural_pattern_suite.gap_go_leader import evaluate as eval_gap
from research.structural_pattern_suite.late_day_persistence import evaluate as eval_late
from research.structural_pattern_suite.oracle import assert_candidate_invariants
from research.structural_pattern_suite.prior_range_leader import evaluate as eval_prior


def bar(ts: str, open_: float, high: float, low: float, close: float, symbol: str = "NIFTY") -> Bar:
    return Bar(symbol=symbol, session="2026-07-20", timestamp=ts, open=open_, high=high, low=low, close=close)


def test_gap_go_leader_uses_frozen_gap_leader_thresholds_and_next_bar_entry() -> None:
    previous = PreviousSession(symbol="NIFTY", session="2026-07-17", high=100.0, low=90.0, close=95.0)
    candidate = eval_gap(
        symbol="NIFTY",
        peer_symbol="BANKNIFTY",
        session="2026-07-20",
        session_open=99.0,
        peer_session_open=200.0,
        previous=previous,
        decision_bar=bar("2026-07-20T09:45:00+05:30", 99.0, 101.0, 98.5, 100.0),
        peer_decision_bar=bar("2026-07-20T09:45:00+05:30", 200.0, 201.0, 199.0, 200.2, "BANKNIFTY"),
        entry_bar=bar("2026-07-20T09:50:00+05:30", 100.1, 101.0, 100.0, 100.5),
        source_manifest_hash="s" * 64,
    )
    assert candidate is not None
    assert candidate.strategy_id == StrategyId.GAP_GO_LEADER
    assert candidate.side == Side.LONG
    assert candidate.gap_normalized == pytest.approx(0.4)
    assert candidate.leader_spread_bps is not None and candidate.leader_spread_bps >= 20.0
    assert candidate.entry_timestamp > candidate.decision_timestamp
    assert candidate.execution_eligibility is False
    assert candidate.research_only is True
    assert_candidate_invariants(candidate)


def test_gap_go_rejects_same_direction_without_leader_confirmation() -> None:
    previous = PreviousSession(symbol="NIFTY", session="2026-07-17", high=100.0, low=90.0, close=95.0)
    candidate = eval_gap(
        symbol="NIFTY",
        peer_symbol="BANKNIFTY",
        session="2026-07-20",
        session_open=99.0,
        peer_session_open=200.0,
        previous=previous,
        decision_bar=bar("2026-07-20T09:45:00+05:30", 99.0, 100.0, 98.5, 99.1),
        peer_decision_bar=bar("2026-07-20T09:45:00+05:30", 200.0, 202.0, 199.0, 201.5, "BANKNIFTY"),
        entry_bar=bar("2026-07-20T09:50:00+05:30", 99.2, 100.0, 99.0, 99.5),
        source_manifest_hash="s" * 64,
    )
    assert candidate is None


def test_prior_range_leader_has_no_extra_indicator_filters() -> None:
    previous = PreviousSession(symbol="NIFTY", session="2026-07-17", high=100.0, low=90.0, close=95.0)
    candidate = eval_prior(
        symbol="NIFTY",
        peer_symbol="BANKNIFTY",
        session="2026-07-20",
        session_open=99.0,
        peer_session_open=200.0,
        previous=previous,
        decision_bar=bar("2026-07-20T09:45:00+05:30", 99.0, 103.0, 98.5, 102.0),
        peer_decision_bar=bar("2026-07-20T09:45:00+05:30", 200.0, 200.5, 199.0, 200.1, "BANKNIFTY"),
        entry_bar=bar("2026-07-20T09:50:00+05:30", 102.2, 103.0, 102.0, 102.5),
        source_manifest_hash="s" * 64,
    )
    assert candidate is not None
    assert candidate.prior_boundary_relation == "ABOVE_PREVIOUS_HIGH"
    assert candidate.strategy_id == StrategyId.PRIOR_RANGE_LEADER


def test_late_day_persistence_requires_displacement_and_outer_close_location() -> None:
    previous = PreviousSession(symbol="NIFTY", session="2026-07-17", high=110.0, low=90.0, close=100.0)
    bars = [
        bar("2026-07-20T09:15:00+05:30", 100.0, 101.0, 99.5, 100.5),
        bar("2026-07-20T13:55:00+05:30", 109.5, 111.0, 108.0, 110.5),
    ]
    candidate = eval_late(
        symbol="NIFTY",
        session="2026-07-20",
        session_open=100.0,
        previous=previous,
        bars_from_open_to_decision=bars,
        decision_bar=bar("2026-07-20T14:00:00+05:30", 110.0, 111.0, 109.0, 110.5),
        entry_bar=bar("2026-07-20T14:05:00+05:30", 110.6, 111.5, 110.0, 111.0),
        source_manifest_hash="s" * 64,
    )
    assert candidate is not None
    assert candidate.side == Side.LONG
    assert candidate.late_displacement == pytest.approx(0.525)
    assert candidate.close_location is not None and candidate.close_location >= 0.80


def test_oracle_rejects_same_bar_entry_mutation() -> None:
    previous = PreviousSession(symbol="NIFTY", session="2026-07-17", high=100.0, low=90.0, close=95.0)
    candidate = eval_prior(
        symbol="NIFTY",
        peer_symbol="BANKNIFTY",
        session="2026-07-20",
        session_open=99.0,
        peer_session_open=200.0,
        previous=previous,
        decision_bar=bar("2026-07-20T09:45:00+05:30", 99.0, 103.0, 98.5, 102.0),
        peer_decision_bar=bar("2026-07-20T09:45:00+05:30", 200.0, 200.5, 199.0, 200.1, "BANKNIFTY"),
        entry_bar=bar("2026-07-20T09:45:00+05:30", 102.0, 103.0, 102.0, 102.5),
        source_manifest_hash="s" * 64,
    )
    assert candidate is not None
    with pytest.raises(AssertionError, match="same-bar"):
        assert_candidate_invariants(candidate)

