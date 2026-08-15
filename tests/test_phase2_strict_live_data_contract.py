from __future__ import annotations

from config import config as cfg
import core._engine_phase2_adapter_base as phase2
from core.paths import logs_dir
from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair


def _install_current_feed():
    make_valid_canonical_feed_pair(logs_dir(), feed_ok=True)


def _base_candidate(**overrides):
    candidate = {
        "trade_id": "C1",
        "symbol": "NIFTY",
        "final_score": 0.95,
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "liquidity_score": 0.9,
        "spread_pct": 0.01,
        "quote_source": "live",
    }
    candidate.update(overrides)
    return candidate


def test_live_missing_spread_and_bbo_is_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False, raising=False)

    _install_current_feed()
    ranked = phase2.build_candidates_phase2(
        [
            _base_candidate(
                trade_id="MISSING_SPREAD",
                spread_pct=None,
                best_bid=None,
                best_ask=None,
                quote_age_sec=0.5,
                volume=1000,
            )
        ]
    )
    assert ranked
    assert ranked[0]["execution_ok"] is False
    assert ranked[0]["execution_quality_reason_code"] in {"missing_spread_context", "missing_liquidity_validation", "missing_live_timing_context"}
    assert "missing_spread_context" in (ranked[0].get("gate_reasons") or [])

    result = phase2.run_engine_phase2(ranked)
    assert result["state"] != "ENTER"
    assert result["state"] in {"WATCHLIST", "NO_TRADE"}


def test_live_missing_quote_age_is_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False, raising=False)

    _install_current_feed()
    ranked = phase2.build_candidates_phase2(
        [
            _base_candidate(
                trade_id="MISSING_QUOTE_AGE",
                quote_age_sec=None,
                volume=1000,
            )
        ]
    )
    assert ranked
    assert ranked[0]["execution_ok"] is False
    assert ranked[0]["execution_quality_reason_code"] == "missing_live_timing_context"
    assert "missing_live_timing_context" in (ranked[0].get("gate_reasons") or [])
    result = phase2.run_engine_phase2(ranked)
    assert result["state"] == "NO_TRADE"
    assert result["state"] != "ENTER"


def test_live_estimated_rr_is_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False, raising=False)

    _install_current_feed()
    ranked = phase2.build_candidates_phase2(
        [
            _base_candidate(
                trade_id="RR_ESTIMATED",
                quote_age_sec=0.2,
                gate_reasons=["rr_estimated_context"],
                volume=1000,
            )
        ]
    )
    assert ranked
    assert ranked[0]["execution_ok"] is False
    assert ranked[0]["execution_quality_reason_code"] == "rr_estimated_context"
    assert "rr_estimated_context" in (ranked[0].get("gate_reasons") or [])
    result = phase2.run_engine_phase2(ranked)
    assert result["state"] == "NO_TRADE"
    assert result["state"] != "ENTER"


def test_paper_missing_fields_can_still_be_scored_as_before(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False, raising=False)

    _install_current_feed()
    ranked = phase2.build_candidates_phase2(
        [
            _base_candidate(
                trade_id="PAPER_FALLBACKS_OK",
                quote_age_sec=None,
                spread_pct=None,
                liquidity_score=None,
                best_bid=None,
                best_ask=None,
            )
        ]
    )
    assert ranked
    assert ranked[0].get("quote_age_sec") is not None
    assert ranked[0].get("phase2_spread_fallback_used") is True
    assert ranked[0].get("phase2_liquidity_fallback_used") is True
