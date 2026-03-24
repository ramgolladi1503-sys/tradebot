from __future__ import annotations

from core import orchestrator as orch
from config import config as cfg


class _DummyBuilder:
    def __init__(self, reason: str):
        self._reject_ctx = {"reason": reason, "gate_reasons": [reason]}


def test_soft_reject_enters_rank_pool_when_non_critical(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol", raising=False)

    ranked, soft_candidates, reject_reason, gate_reasons = orch._augment_ranked_candidates_with_soft_reject(
        trade_builder=_DummyBuilder("spread_pct"),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reject_reason == "spread_pct"
    assert gate_reasons == ["spread_pct"]
    assert len(soft_candidates) == 1
    assert len(ranked) == 1
    assert ranked[0].get("rank_score") is not None
    assert ranked[0].get("execution_status") == "advisory_only"


def test_soft_reject_skips_critical_reason(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "spread_pct", raising=False)

    ranked, soft_candidates, reject_reason, gate_reasons = orch._augment_ranked_candidates_with_soft_reject(
        trade_builder=_DummyBuilder("spread_pct"),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reject_reason == "spread_pct"
    assert gate_reasons == ["spread_pct"]
    assert soft_candidates == []
    assert ranked == []


def test_missing_reason_falls_back_to_unknown_reject(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol", raising=False)

    class _EmptyBuilder:
        _reject_ctx = {}

    ranked, soft_candidates, reject_reason, gate_reasons = orch._augment_ranked_candidates_with_soft_reject(
        trade_builder=_EmptyBuilder(),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reject_reason == "unknown_reject"
    assert gate_reasons == ["unknown_reject"]
    assert len(soft_candidates) == 1
    assert len(ranked) == 1
