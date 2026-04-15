from __future__ import annotations

from config import config as cfg
from core.issue_policy import ISSUE_CATEGORY_HARD, ISSUE_CATEGORY_SOFT, classify_issue


def _ctx() -> dict:
    return {
        "mode": "LIVE",
        "market_open": True,
        "permission": "QUEUE_ONLY",
    }


def test_type_mismatch_soft_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", False, raising=False)
    decision = classify_issue("type_mismatch", _ctx())
    assert decision.category == ISSUE_CATEGORY_SOFT


def test_type_mismatch_hard_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", True, raising=False)
    decision = classify_issue("type_mismatch", _ctx())
    assert decision.category == ISSUE_CATEGORY_HARD


def test_iv_bounds_soft_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False, raising=False)
    decision = classify_issue("iv_bounds", _ctx())
    assert decision.category == ISSUE_CATEGORY_SOFT


def test_iv_bounds_hard_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", True, raising=False)
    decision = classify_issue("iv_bounds", _ctx())
    assert decision.category == ISSUE_CATEGORY_HARD


def test_iv_skew_curvature_soft_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False, raising=False)
    decision = classify_issue("iv_skew_curvature", _ctx())
    assert decision.category == ISSUE_CATEGORY_SOFT


def test_iv_skew_curvature_hard_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", True, raising=False)
    decision = classify_issue("iv_skew_curvature", _ctx())
    assert decision.category == ISSUE_CATEGORY_HARD
