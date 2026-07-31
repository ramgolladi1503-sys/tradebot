from __future__ import annotations

import pytest

import core.opportunity_engine as engine


pytestmark = [pytest.mark.behavior, pytest.mark.regression, pytest.mark.replay]


def _candidate(trade_id: str, *, builder: float, permission: float, symbol: str = "NIFTY") -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "builder_confidence": builder,
        "permission_confidence": permission,
        "source_flags": {},
    }


def _install_equal_primary_scores(monkeypatch) -> None:
    def _metrics(candidate):
        return {
            "candidate_class": "ADVISORY_ONLY",
            "final_score": 0.5,
            "opportunity_score": 0.5,
            "strategy_priority": 0.5,
            "risk_adjusted_quality": 0.5,
            "builder_confidence": float(candidate["builder_confidence"]),
            "permission_confidence": float(candidate["permission_confidence"]),
            "liquidity_quality": 0.5,
            "quote_consistency_score": 0.5,
            "data_confidence": 0.5,
            "priority_weight_signal": 0.5,
            "priority_weight_execution": 0.5,
        }

    monkeypatch.setattr(engine, "build_opportunity_score", _metrics)
    monkeypatch.setattr(engine, "_ranking_score", lambda candidate, metrics: 0.5)


def test_higher_confidence_wins_when_primary_scores_tie(monkeypatch):
    _install_equal_primary_scores(monkeypatch)
    low = _candidate("LOW", builder=0.40, permission=0.40)
    high = _candidate("HIGH", builder=0.90, permission=0.90)

    ranked = engine.annotate_relative_opportunity_ranks(
        [low, high],
        scope="qa:ranking-tiebreak",
    )

    assert [row["trade_id"] for row in ranked] == ["HIGH", "LOW"]


def test_exact_ties_are_independent_of_input_order(monkeypatch):
    _install_equal_primary_scores(monkeypatch)
    first = _candidate("A", builder=0.70, permission=0.70)
    second = _candidate("B", builder=0.70, permission=0.70)

    forward = engine.annotate_relative_opportunity_ranks(
        [first, second],
        scope="qa:ranking-tiebreak",
    )
    reverse = engine.annotate_relative_opportunity_ranks(
        [second, first],
        scope="qa:ranking-tiebreak",
    )

    assert [row["trade_id"] for row in forward] == ["A", "B"]
    assert [row["trade_id"] for row in reverse] == ["A", "B"]
