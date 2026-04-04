from __future__ import annotations

from config import config as cfg
from core.offline_family_learning import append_family_outcome_record, rebuild_family_learning_state
from core.strategy_weight_learning import (
    load_strategy_weight_state,
    lookup_strategy_weight,
    rebuild_strategy_weight_state,
    save_strategy_weight_state,
    update_strategy_weights_from_outcomes,
)


def _family_state(
    *,
    sample_count: int,
    expectancy_score: float,
    win_rate: float = 0.6,
    median_pnl: float = 12.0,
    median_mfe: float = 16.0,
    median_mae: float = -4.0,
    family_confidence: float = 0.8,
    direction_family: str = "bullish",
) -> dict:
    return {
        "version": 1,
        "generated_at": "2026-04-04T00:00:00+00:00",
        "min_samples": 25,
        "families": {
            f"continuation|{direction_family}": {
                "strategy_family": "continuation",
                "direction_family": direction_family,
                "sample_count": sample_count,
                "win_rate": win_rate,
                "median_pnl": median_pnl,
                "median_mfe": median_mfe,
                "median_mae": median_mae,
                "would_have_worked_rate": max(0.0, min(1.0, win_rate + 0.05)),
                "rejection_saved_loss_rate": 0.10,
                "rejection_missed_win_rate": 0.04,
                "opportunity_conversion_rate": 0.62,
                "expectancy_score": expectancy_score,
                "family_confidence": family_confidence,
            }
        },
    }


def test_update_strategy_weights_from_outcomes_shrinks_small_samples_to_neutral(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 40, raising=False)
    state = update_strategy_weights_from_outcomes(_family_state(sample_count=8, expectancy_score=0.8))
    family = state["families"]["continuation|bullish"]

    assert family["strategy_weight_applied"] is False
    assert float(family["strategy_weight_adjustment"]) == 0.0


def test_strong_family_gets_small_positive_weight_adjustment(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 10, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", 0.04, raising=False)
    state = update_strategy_weights_from_outcomes(_family_state(sample_count=80, expectancy_score=0.7))
    family = state["families"]["continuation|bullish"]

    assert family["strategy_weight_applied"] is True
    assert 0.0 < float(family["strategy_weight_adjustment"]) <= 0.04


def test_weak_family_gets_small_negative_weight_adjustment(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 10, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", 0.04, raising=False)
    state = update_strategy_weights_from_outcomes(
        _family_state(
            sample_count=80,
            expectancy_score=-0.7,
            win_rate=0.35,
            median_pnl=-8.0,
            median_mfe=5.0,
            median_mae=-12.0,
        )
    )
    family = state["families"]["continuation|bullish"]

    assert family["strategy_weight_applied"] is True
    assert -0.04 <= float(family["strategy_weight_adjustment"]) < 0.0


def test_family_learning_changes_weight_safely(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 10, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", 0.04, raising=False)
    state = update_strategy_weights_from_outcomes(_family_state(sample_count=60, expectancy_score=0.55))
    family = state["families"]["continuation|bullish"]

    assert 0.0 < float(family["weight_adj"]) <= 0.04
    assert 0.0 < float(family["confidence"]) <= 1.0


def test_strategy_weight_state_round_trips_json(tmp_path):
    path = tmp_path / "strategy_weight_state.json"
    state = update_strategy_weights_from_outcomes(_family_state(sample_count=80, expectancy_score=0.5))
    save_strategy_weight_state(state, path=path)

    loaded = load_strategy_weight_state(path=path)

    assert loaded == state


def test_lookup_strategy_weight_defaults_to_neutral_when_missing(tmp_path):
    loaded = load_strategy_weight_state(path=tmp_path / "missing.json")
    weight = lookup_strategy_weight("continuation", "bullish", state=loaded)

    assert weight["strategy_weight_applied"] is False
    assert float(weight["strategy_weight_adjustment"]) == 0.0


def test_rebuild_strategy_weight_state_from_family_state(tmp_path):
    path = tmp_path / "strategy_weight_state.json"
    state = rebuild_strategy_weight_state(
        family_learning_state=_family_state(sample_count=80, expectancy_score=0.5),
        path=path,
    )

    assert path.exists()
    assert "continuation|bullish" in state["families"]


def test_family_learning_rebuild_updates_strategy_weight_state(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 5, raising=False)
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"
    for idx in range(8):
        append_family_outcome_record(
            {
                "timestamp": f"2026-04-04T00:00:{idx:02d}+00:00",
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "candidate_class": "EXECUTABLE",
                "selector_outcome": "EXECUTE_TOP",
                "signal_score": 0.7,
                "execution_score": 0.66,
                "priority_score": 0.68,
                "final_score": 0.68,
                "selection_probability": 0.62,
                "simulation_status": "SIM_EXECUTED",
                "fill_status": "FILLED",
                "mfe": 15.0,
                "mae": -4.0,
                "simulated_pnl": 10.0,
                "exit_reason": "TARGET_HIT",
                "would_have_worked": True,
                "rejection_saved_loss": False,
                "rejection_missed_win": False,
            },
            path=records_path,
        )

    rebuild_family_learning_state(records_path=records_path, state_path=state_path)
    strategy_state = load_strategy_weight_state()

    assert "continuation|bullish" in strategy_state["families"]
