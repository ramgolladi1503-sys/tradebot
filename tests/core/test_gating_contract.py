from __future__ import annotations

from config import config as cfg
from core.gating import apply_hard_gates, apply_soft_gates, gate_decision


def _snapshot(*, age: float = 1.0, threshold: float = 2.5, feed_state: str = "OK") -> dict:
    return {
        "freshness": {
            "max_tick_age_sec": age,
            "sla_threshold_sec": threshold,
        },
        "feed_state": feed_state,
    }


def test_apply_hard_gates_passes_with_valid_structural_inputs() -> None:
    candidate = {
        "current_ltp": 102.5,
        "option_age_sec": 1.2,
        "spread_pct": 0.01,
        "volume": 5_000,
    }
    passed, reasons = apply_hard_gates(candidate, _snapshot(age=1.2, threshold=2.5))
    assert passed is True
    assert reasons == []


def test_apply_hard_gates_fails_missing_ltp_and_volume() -> None:
    candidate = {
        "current_ltp": None,
        "option_age_sec": 0.5,
        "spread_pct": 0.01,
        "volume": None,
    }
    passed, reasons = apply_hard_gates(candidate, _snapshot(age=0.5, threshold=2.5))
    assert passed is False
    assert "HARD_NO_LTP" in reasons
    assert "HARD_MISSING_VOLUME" in reasons


def test_apply_hard_gates_fails_stale_age() -> None:
    candidate = {
        "current_ltp": 99.0,
        "option_age_sec": 9.0,
        "spread_pct": 0.01,
        "volume": 10_000,
    }
    passed, reasons = apply_hard_gates(candidate, _snapshot(age=9.0, threshold=2.5))
    assert passed is False
    assert reasons == ["HARD_STALE_LTP"]


def test_apply_hard_gates_allows_missing_volume_when_quotes_are_fresh_and_valid(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "GATING_ALLOW_MISSING_VOLUME_WITH_VALID_QUOTES", True, raising=False)
    candidate = {
        "current_ltp": 99.0,
        "option_age_sec": 0.8,
        "spread_pct": 0.01,
        "best_bid": 98.8,
        "best_ask": 99.2,
        "volume": None,
    }
    passed, reasons = apply_hard_gates(candidate, _snapshot(age=0.8, threshold=2.5))
    assert passed is True
    assert "HARD_MISSING_VOLUME" not in reasons


def test_apply_soft_gates_penalizes_missing_volume_when_quotes_are_fresh_and_valid(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "GATING_ALLOW_MISSING_VOLUME_WITH_VALID_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "GATING_SOFT_PENALTY_MISSING_VOLUME_WITH_VALID_QUOTES", 0.08, raising=False)
    candidate = {
        "current_ltp": 100.0,
        "option_age_sec": 1.0,
        "spread_pct": 0.005,
        "best_bid": 99.5,
        "best_ask": 100.5,
        "volume": None,
        "confidence": 0.8,
    }
    delta, reasons = apply_soft_gates(candidate, _snapshot(age=1.0, threshold=2.5, feed_state="OK"))
    assert delta == -0.08
    assert reasons == ["SOFT_MISSING_VOLUME_WITH_VALID_QUOTES"]


def test_apply_soft_gates_only_adjusts_score() -> None:
    candidate = {
        "current_ltp": 100.0,
        "option_age_sec": 2.0,  # near limit
        "spread_pct": 0.025,  # elevated vs default hard max 0.03
        "volume": 100.0,  # low vs default min filter
        "feed_state": "DEGRADED",
        "confidence": 0.8,
    }
    delta, reasons = apply_soft_gates(candidate, _snapshot(age=2.0, threshold=2.5, feed_state="DEGRADED"))
    assert delta < 0.0
    assert "SOFT_FEED_DEGRADED" in reasons
    assert "SOFT_AGE_NEAR_LIMIT" in reasons
    assert "SOFT_SPREAD_ELEVATED" in reasons


def test_gate_decision_reports_contract_fields() -> None:
    candidate = {
        "current_ltp": 100.0,
        "option_age_sec": 1.0,
        "spread_pct": 0.005,
        "volume": 10_000,
        "feed_state": "OK",
        "confidence": 0.72,
    }
    decision = gate_decision(candidate, _snapshot(age=1.0, threshold=2.5, feed_state="OK"))
    assert set(decision.keys()) >= {
        "hard_pass",
        "soft_score_adjustment",
        "final_confidence",
        "reasons",
        "hard_reasons",
        "soft_reasons",
    }
    assert decision["hard_pass"] is True
    assert 0.0 <= float(decision["final_confidence"]) <= 1.0
