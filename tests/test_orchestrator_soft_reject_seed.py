from __future__ import annotations

from config import config as cfg
from core import orchestrator as orch


class _DummyBuilder:
    def __init__(self, reason: str):
        self._reject_ctx = {"reason": reason, "gate_reasons": [reason]}


def test_soft_reject_does_not_seed_rank_score(monkeypatch):
    pass


def test_soft_reject_does_not_pollute_ranking():
    real = {"trade_id": "real_1", "rank_score": 0.62}
    soft = {
        "trade_id": "tbsoft_1",
        "rank_score": None,
        "soft_reject_seed_confidence": 0.18,
        "score_origin": "soft_reject_seed",
    }

    ranked = sorted(
        [real, soft],
        key=lambda x: x.get("rank_score") if x.get("rank_score") is not None else -1.0,
        reverse=True,
    )

    assert ranked[0]["trade_id"] == "real_1"
    assert ranked[1]["trade_id"] == "tbsoft_1"


def test_soft_reject_augmentation_disabled_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)

    ranked, soft_candidates, reject_reason, _ = orch._augment_ranked_candidates_with_soft_reject(
        trade_builder=_DummyBuilder("spread_pct"),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reject_reason == "spread_pct"
    assert ranked == []
    assert soft_candidates == []
