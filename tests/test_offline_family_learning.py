from __future__ import annotations

import json

from config import config as cfg
from core.offline_family_learning import (
    append_family_outcome_record,
    derive_family_feedback,
    load_family_learning_state,
    load_family_outcome_records,
    rebuild_family_learning_state,
    save_family_learning_state,
    summarize_family_history,
)


def _record(
    *,
    strategy_family: str = "continuation",
    direction_family: str = "bullish",
    pnl: float = 10.0,
    mfe: float = 15.0,
    mae: float = -4.0,
    status: str = "SIM_EXECUTED",
    would_have_worked: bool = True,
    rejection_saved_loss: bool = False,
    rejection_missed_win: bool = False,
    idx: int = 0,
) -> dict:
    return {
        "timestamp": f"2026-04-04T00:00:{idx:02d}+00:00",
        "strategy_family": strategy_family,
        "direction_family": direction_family,
        "candidate_class": "EXECUTABLE",
        "selector_outcome": "EXECUTE_TOP",
        "signal_score": 0.7,
        "execution_score": 0.65,
        "priority_score": 0.68,
        "final_score": 0.68,
        "selection_probability": 0.62,
        "simulation_status": status,
        "fill_status": "FILLED",
        "mfe": mfe,
        "mae": mae,
        "simulated_pnl": pnl,
        "exit_reason": "TARGET_HIT" if pnl > 0 else "STOP_HIT",
        "would_have_worked": would_have_worked,
        "rejection_saved_loss": rejection_saved_loss,
        "rejection_missed_win": rejection_missed_win,
    }


def test_summarize_family_history_computes_expectancy_metrics():
    summary = summarize_family_history(
        [
            _record(pnl=12.0, mfe=18.0, mae=-3.0, idx=1),
            _record(pnl=8.0, mfe=13.0, mae=-4.0, idx=2),
            _record(pnl=-4.0, mfe=5.0, mae=-8.0, would_have_worked=False, idx=3),
        ]
    )

    family = summary["continuation|bullish"]
    assert family["sample_count"] == 3
    assert 0.0 < float(family["win_rate"]) < 1.0
    assert float(family["median_pnl"]) == 8.0
    assert float(family["median_mfe"]) == 13.0
    assert float(family["median_mae"]) == -4.0
    assert float(family["expectancy_score"]) > 0.0


def test_family_feedback_shrinks_to_neutral_for_small_samples(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25, raising=False)
    feedback = derive_family_feedback(
        summarize_family_history([_record(idx=1), _record(idx=2), _record(idx=3)])
    )

    family = feedback["continuation|bullish"]
    assert family["family_feedback_applied"] is False
    assert float(family["family_score_adjustment"]) == 0.0
    assert int(family["family_scarcity_adjustment"]) == 0


def test_family_feedback_is_bounded_for_large_samples(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 10, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", 0.06, raising=False)
    records = [_record(pnl=20.0, mfe=25.0, mae=-2.0, idx=i) for i in range(20)]

    feedback = derive_family_feedback(summarize_family_history(records))
    family = feedback["continuation|bullish"]
    assert family["family_feedback_applied"] is True
    assert -0.06 <= float(family["family_score_adjustment"]) <= 0.06
    assert -1 <= int(family["family_scarcity_adjustment"]) <= 1


def test_family_learning_state_round_trips_json(tmp_path):
    path = tmp_path / "family_learning_state.json"
    state = {
        "version": 1,
        "generated_at": "2026-04-04T00:00:00+00:00",
        "min_samples": 25,
        "families": {
            "continuation|bullish": {
                "sample_count": 40,
                "family_score_adjustment": 0.03,
            }
        },
    }
    save_family_learning_state(state, path=path)

    loaded = load_family_learning_state(path=path)

    assert loaded == state


def test_outcome_record_append_is_deterministic(tmp_path):
    path = tmp_path / "family_outcomes.jsonl"
    record = _record(idx=1)

    append_family_outcome_record(record, path=path)
    append_family_outcome_record(record, path=path)
    loaded = load_family_outcome_records(path=path)

    assert loaded == [json.loads(json.dumps(record, sort_keys=True, ensure_ascii=True, default=str))] * 2


def test_rebuild_family_learning_state_persists_feedback(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 5, raising=False)
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"
    for idx in range(8):
        append_family_outcome_record(
            _record(
                strategy_family="breakout",
                direction_family="bullish",
                pnl=12.0 if idx < 6 else -3.0,
                mfe=15.0,
                mae=-4.0,
                idx=idx,
            ),
            path=records_path,
        )

    state = rebuild_family_learning_state(records_path=records_path, state_path=state_path)

    assert state["families"]["breakout|bullish"]["sample_count"] == 8
    assert "family_score_adjustment" in state["families"]["breakout|bullish"]
    assert load_family_learning_state(path=state_path) == state
