from __future__ import annotations

from config import config as cfg
from core import orchestrator as orch


class _DummyBuilder:
    def __init__(self, reason: str):
        self._reject_ctx = {"reason": reason, "gate_reasons": [reason]}


def test_soft_reject_does_not_seed_rank_score(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18, raising=False)

    ranked, soft_candidates, reject_reason, _ = orch._augment_ranked_candidates_with_soft_reject(
        trade_builder=_DummyBuilder("spread_pct"),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert reject_reason == "spread_pct"
    assert len(soft_candidates) == 1
    assert len(ranked) == 1
    out = ranked[0]
    assert out.get("candidate_origin") == "softened_builder_path"
    assert out.get("rank_score") is None
    assert out.get("soft_reject_seed_confidence") == 0.18
    assert out.get("score_origin") == "soft_reject_seed"


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
