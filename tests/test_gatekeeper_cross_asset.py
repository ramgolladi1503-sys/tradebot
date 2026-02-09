from core.strategy_gatekeeper import StrategyGatekeeper
from config import config as cfg


def _mk_md(stale=True, missing=True):
    missing_map = {"USDINR_SPOT": "missing_last_price"} if missing else {}
    stale_list = ["USDINR_SPOT"] if stale else []
    return {
        "indicators_ok": True,
        "indicators_age_sec": 0,
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.8},
        "regime_entropy": 0.1,
        "unstable_regime_flag": False,
        "cross_asset_quality": {
            "any_stale": bool(stale),
            "stale_feeds": stale_list,
            "missing": missing_map,
            "required_stale": stale_list,
            "optional_stale": [],
        },
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
    }


def _mk_md_disabled(required_stale=True):
    return {
        "indicators_ok": True,
        "indicators_age_sec": 0,
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.8},
        "regime_entropy": 0.1,
        "unstable_regime_flag": False,
        "cross_asset_quality": {
            "disabled": True,
            "disabled_reason": "kite_unavailable",
            "required_stale": ["USDINR_SPOT"] if required_stale else [],
            "optional_stale": [],
            "missing": {"USDINR_SPOT": "kite_unavailable"} if required_stale else {},
        },
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
    }


def test_cross_asset_required_blocks(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", True)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    gate = StrategyGatekeeper()
    md = _mk_md(stale=True, missing=True)
    res = gate.evaluate(md)
    assert not res.allowed
    assert "cross_asset_required_stale" in res.reasons


def test_cross_asset_not_required_allows(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    gate = StrategyGatekeeper()
    md = _mk_md(stale=True, missing=True)
    res = gate.evaluate(md)
    assert res.allowed


def test_cross_asset_optional_does_not_block(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", True)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", [])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", ["USDINR_SPOT"])
    gate = StrategyGatekeeper()
    md = _mk_md(stale=True, missing=True)
    res = gate.evaluate(md)
    assert res.allowed
    assert "cross_asset_optional_stale" in res.reasons


def test_cross_asset_disabled_blocks_when_required(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", True)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    gate = StrategyGatekeeper()
    md = _mk_md_disabled(required_stale=True)
    res = gate.evaluate(md)
    assert not res.allowed
    assert "cross_asset_required_stale" in res.reasons or "cross_asset_required_missing" in res.reasons


def test_cross_asset_disabled_optional_allows(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", True)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", [])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", ["USDINR_SPOT"])
    gate = StrategyGatekeeper()
    md = _mk_md_disabled(required_stale=False)
    res = gate.evaluate(md)
    assert res.allowed
    assert any(r.startswith("cross_asset_disabled") for r in res.reasons)
