from config import config as cfg
from core.strategy_gatekeeper import StrategyGatekeeper


def _base_market_data():
    return {
        "indicators_ok": True,
        "indicators_age_sec": 1.0,
        "primary_regime": "NEUTRAL",
        "regime_probs": {"TREND": 0.30, "RANGE": 0.35, "EVENT": 0.35},
        "regime_entropy": 1.6,
        "unstable_regime_flag": False,
        "cross_asset_quality": {},
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
    }


def test_gatekeeper_uses_unstable_reasons_not_legacy_boolean(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)
    monkeypatch.setattr(cfg, "PAPER_RELAX_GATES", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_NEUTRAL_FAMILY", "DEFINED_RISK", raising=False)

    md = _base_market_data()
    md.update(
        {
            "regime_probs": {"TREND": 1.0},
            "regime_entropy": 0.0,
            "unstable_regime_flag": True,
            "unstable_reasons": [],
        }
    )
    gate = StrategyGatekeeper().evaluate(md, mode="MAIN")
    assert gate.allowed is True
    assert "regime_unstable" not in gate.reasons


def test_gatekeeper_blocks_when_unstable_reasons_present(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)

    md = _base_market_data()
    md.update(
        {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 1.0},
            "regime_entropy": 0.0,
            "unstable_regime_flag": False,
            "unstable_reasons": ["warmup_incomplete"],
        }
    )
    gate = StrategyGatekeeper().evaluate(md, mode="MAIN")
    assert gate.allowed is False
    assert "regime_unstable" in gate.reasons
    assert "unstable:warmup_incomplete" in gate.reasons


def test_live_mode_keeps_strict_regime_thresholds(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)
    monkeypatch.setattr(cfg, "PAPER_RELAX_GATES", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROB_MIN", 0.45, raising=False)
    monkeypatch.setattr(cfg, "REGIME_ENTROPY_MAX", 1.3, raising=False)
    monkeypatch.setattr(cfg, "PAPER_REGIME_PROB_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "PAPER_REGIME_ENTROPY_MAX", 2.0, raising=False)

    gate = StrategyGatekeeper().evaluate(_base_market_data(), mode="MAIN")

    assert gate.allowed is False
    assert "regime_unstable" in gate.reasons or "regime_low_confidence" in gate.reasons


def test_paper_mode_relaxes_thresholds_and_routes_neutral(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)
    monkeypatch.setattr(cfg, "PAPER_RELAX_GATES", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROB_MIN", 0.45, raising=False)
    monkeypatch.setattr(cfg, "REGIME_ENTROPY_MAX", 1.3, raising=False)
    monkeypatch.setattr(cfg, "PAPER_REGIME_PROB_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "PAPER_REGIME_ENTROPY_MAX", 2.0, raising=False)
    monkeypatch.setattr(cfg, "PAPER_NEUTRAL_FAMILY", "DEFINED_RISK", raising=False)

    gate = StrategyGatekeeper().evaluate(_base_market_data(), mode="MAIN")

    assert gate.allowed is True
    assert gate.family == "DEFINED_RISK"
    assert "paper_neutral_routed" in gate.reasons


def test_paper_soft_unblock_allows_defined_risk_for_non_contradictory_unstable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)
    monkeypatch.setattr(cfg, "PAPER_RELAX_GATES", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_CONF_MIN", 0.80, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS", ["entropy_too_high", "prob_too_low"], raising=False)

    md = _base_market_data()
    md.update(
        {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.85, "RANGE": 0.10, "EVENT": 0.05},
            "regime_entropy": 0.25,
            "unstable_reasons": ["warmup_incomplete"],
            "indicators_ok": True,
        }
    )
    gate = StrategyGatekeeper().evaluate(md, mode="MAIN")

    assert gate.allowed is True
    assert gate.family == "DEFINED_RISK"
    assert "paper_soft_unblock" in gate.reasons


def test_live_mode_never_applies_paper_soft_unblock(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_CROSS_ASSET", False, raising=False)
    monkeypatch.setattr(cfg, "PAPER_RELAX_GATES", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_CONF_MIN", 0.80, raising=False)
    monkeypatch.setattr(cfg, "PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS", ["entropy_too_high", "prob_too_low"], raising=False)

    md = _base_market_data()
    md.update(
        {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.90, "RANGE": 0.05, "EVENT": 0.05},
            "regime_entropy": 0.20,
            "unstable_reasons": ["warmup_incomplete"],
            "indicators_ok": True,
        }
    )
    gate = StrategyGatekeeper().evaluate(md, mode="MAIN")

    assert gate.allowed is False
    assert "regime_unstable" in gate.reasons
    assert "paper_soft_unblock" not in gate.reasons
