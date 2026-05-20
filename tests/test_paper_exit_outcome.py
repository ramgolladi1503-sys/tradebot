from __future__ import annotations

import pytest

from core.offline_family_learning import load_family_learning_state, load_family_outcome_records
from core.paper_exit_outcome import (
    PaperExitOutcomeError,
    build_paper_exit_outcome,
    normalize_exit_outcome,
    record_paper_exit_outcome,
)


def _exit(**overrides):
    payload = {
        "candidate_id": "cand-1",
        "paper_intent_id": "intent-1",
        "strategy_family": "orb",
        "regime": "trend-morning",
        "direction_family": "BUY_CALL",
        "terminal_status": "target-hit",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "quantity": 2,
        "stop_price": 95.0,
        "slippage_cost": 1.5,
        "final_score": 0.84,
    }
    payload.update(overrides)
    return payload


def test_exit_outcome_aliases_are_explicit_and_fail_closed():
    assert normalize_exit_outcome("TARGET") == "target-hit"
    assert normalize_exit_outcome("STOP_HIT") == "stopped"
    assert normalize_exit_outcome("EOD_EXIT") == "timed-exit"
    with pytest.raises(PaperExitOutcomeError, match="paper_exit_outcome_invalid"):
        normalize_exit_outcome("entry-filled")


def test_target_hit_exit_computes_bullish_pnl_and_r_multiple():
    record = build_paper_exit_outcome(_exit())

    assert record.candidate_id == "cand-1"
    assert record.strategy_family == "orb"
    assert record.regime == "trend-morning"
    assert record.direction_family == "bullish"
    assert record.terminal_status == "target-hit"
    assert record.gross_pnl == 20.0
    assert record.slippage_adjusted_pnl == 18.5
    assert record.risk_per_unit == 5.0
    assert record.realized_r_multiple == 2.0
    assert record.is_order_action is False
    assert record.broker_api_called is False
    assert record.to_dict()["final_score"] == 0.84


def test_stopped_exit_computes_negative_r_multiple():
    record = build_paper_exit_outcome(
        _exit(terminal_status="stop-hit", exit_price=95.0, slippage_cost=0.5)
    )

    assert record.terminal_status == "stopped"
    assert record.gross_pnl == -10.0
    assert record.slippage_adjusted_pnl == -10.5
    assert record.realized_r_multiple == -1.0


def test_bearish_exit_pnl_uses_reverse_direction():
    record = build_paper_exit_outcome(
        _exit(direction_family="BUY_PUT", entry_price=100.0, exit_price=90.0, stop_price=105.0)
    )

    assert record.direction_family == "bearish"
    assert record.gross_pnl == 20.0
    assert record.realized_r_multiple == 2.0


def test_exit_outcome_required_fields_fail_closed():
    with pytest.raises(PaperExitOutcomeError, match="candidate"):
        build_paper_exit_outcome(_exit(candidate_id=""))
    with pytest.raises(PaperExitOutcomeError, match="entry_price"):
        build_paper_exit_outcome(_exit(entry_price=""))
    with pytest.raises(PaperExitOutcomeError, match="exit_price"):
        build_paper_exit_outcome(_exit(exit_price=""))
    with pytest.raises(PaperExitOutcomeError, match="paper_exit_quantity_must_be_positive"):
        build_paper_exit_outcome(_exit(quantity=0))


def test_record_paper_exit_outcome_appends_to_existing_journal(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"

    normalized = record_paper_exit_outcome(
        _exit(),
        records_path=records_path,
        state_path=state_path,
    )

    records = load_family_outcome_records(path=records_path)
    state = load_family_learning_state(path=state_path)

    assert records == [normalized]
    assert normalized["terminal_status"] == "target-hit"
    assert normalized["strategy_family"] == "orb"
    assert normalized["direction_family"] == "bullish"
    assert normalized["simulated_pnl"] == 20.0
    assert normalized["slippage_adjusted_pnl"] == 18.5
    assert normalized["realized_r_multiple"] == 2.0
    assert state["families"]["orb|bullish"]["sample_count"] == 1
