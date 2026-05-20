from __future__ import annotations

import pytest

from core.offline_family_learning import load_family_learning_state, load_family_outcome_records
from core.paper_outcome_journal import (
    ALLOWED_TERMINAL_OUTCOMES,
    PaperOutcomeJournalError,
    build_paper_outcome_journal_record,
    normalize_terminal_outcome,
    record_paper_outcome,
    validate_paper_outcome_records,
)


def _outcome(**overrides):
    payload = {
        "timestamp": "2026-05-20T09:15:00+00:00",
        "candidate_id": "cand-1",
        "paper_intent_id": "intent-1",
        "strategy_family": "orb",
        "regime": "trend",
        "direction_family": "BUY_CALL",
        "terminal_status": "target-hit",
        "candidate_class": "EXECUTABLE",
        "selector_outcome": "SELECTED_FOR_PAPER",
        "signal_score": 0.8,
        "execution_score": 0.75,
        "priority_score": 0.78,
        "final_score": 0.82,
        "selection_probability": 0.7,
        "simulation_status": "SIM_EXECUTED",
        "fill_status": "FILLED",
        "mfe": 18.0,
        "mae": -4.0,
        "simulated_pnl": 100.0,
        "slippage_cost": 7.5,
        "realized_r_multiple": 1.25,
        "risk_plan_respected": True,
        "mode": "PAPER",
        "source": "unit_test",
        "reason": "target reached",
    }
    payload.update(overrides)
    return payload


def test_terminal_outcome_contract_is_explicit_and_fail_closed():
    assert set(ALLOWED_TERMINAL_OUTCOMES) == {
        "executed",
        "rejected-saved-loss",
        "rejected-missed-win",
        "expired-no-move",
        "stopped",
        "target-hit",
        "timed-exit",
    }
    assert normalize_terminal_outcome("STOP_HIT") == "stopped"
    assert normalize_terminal_outcome("SIM_EXECUTED") == "executed"
    assert normalize_terminal_outcome("time_exit") == "timed-exit"

    with pytest.raises(PaperOutcomeJournalError, match="paper_terminal_outcome_invalid"):
        normalize_terminal_outcome("OPEN")


def test_outcome_record_maps_fields_for_edge_audit():
    record = build_paper_outcome_journal_record(_outcome())

    assert record.candidate_id == "cand-1"
    assert record.strategy_family == "orb"
    assert record.regime == "trend"
    assert record.direction_family == "bullish"
    assert record.terminal_status == "target-hit"
    assert record.final_score == 0.82
    assert record.slippage_adjusted_pnl == 92.5
    assert record.realized_r_multiple == 1.25
    assert record.is_order_action is False
    assert record.broker_api_called is False
    assert record.live_order_action is False
    assert record.broker_order_action is False


def test_rejection_terminal_status_sets_rejection_flags():
    saved_loss = build_paper_outcome_journal_record(_outcome(terminal_status="rejected-saved-loss"))
    missed_win = build_paper_outcome_journal_record(_outcome(terminal_status="rejected-missed-win"))

    assert saved_loss.rejection_saved_loss is True
    assert saved_loss.rejection_missed_win is False
    assert missed_win.rejection_saved_loss is False
    assert missed_win.rejection_missed_win is True


def test_required_identity_fields_fail_closed():
    with pytest.raises(PaperOutcomeJournalError, match="candidate_id"):
        build_paper_outcome_journal_record(_outcome(candidate_id=""))

    with pytest.raises(PaperOutcomeJournalError, match="strategy_family"):
        build_paper_outcome_journal_record(_outcome(strategy_family=""))

    with pytest.raises(PaperOutcomeJournalError, match="direction_family"):
        build_paper_outcome_journal_record(_outcome(direction_family=""))


def test_record_paper_outcome_writes_existing_family_outcome_journal(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"

    normalized = record_paper_outcome(
        _outcome(candidate_id="cand-append"),
        records_path=records_path,
        state_path=state_path,
    )

    assert load_family_outcome_records(path=records_path) == [normalized]
    assert load_family_learning_state(path=state_path)["families"]["orb|bullish"]["sample_count"] == 1


def test_validate_paper_outcome_records_reports_invalid_rows():
    report = validate_paper_outcome_records(
        [
            _outcome(candidate_id="valid", terminal_status="timed-exit"),
            _outcome(candidate_id="bad-terminal", terminal_status="OPEN"),
            _outcome(candidate_id="", terminal_status="target-hit"),
        ]
    )

    assert report.checked_records == 3
    assert report.valid_records == 1
    assert report.invalid_records == 2
    assert report.terminal_status_counts == {"timed-exit": 1}
    assert report.passed is False
    assert report.is_order_action is False
    assert report.broker_api_called is False
