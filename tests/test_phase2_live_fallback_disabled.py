from __future__ import annotations

from config import config as cfg
from core.engine_phase2_adapter import run_engine_phase2
from core.runtime_safety_boot_guard import assess_runtime_boot_safety


def test_live_startup_fails_closed_when_phase2_forced_fallback_flags_enabled():
    decision = assess_runtime_boot_safety(
        env={
            "EXECUTION_MODE": "LIVE",
            "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE": "true",
            "PHASE2_FORCE_FALLBACK_ALLOW_LIVE": "true",
        }
    )
    assert decision.allowed is False
    assert "LIVE_UNSAFE_FLAG:PHASE2_FORCE_FALLBACK_EXECUTION" in decision.fatal_reasons


def test_live_synthetic_or_fallback_candidate_cannot_enter_even_with_high_score(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)

    result = run_engine_phase2(
        [
            {
                "trade_id": "FALLBACK_HIGH",
                "symbol": "NIFTY",
                "final_score": 0.95,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
                "synthetic_candidate": True,
                "quote_source": "fallback",
            }
        ],
    )

    assert result["state"] == "WATCHLIST"
    assert result["reason"] == "live_fallback_candidate_blocked"
    assert result["selected"]["live_fallback_execution_blocked"] is True
    assert result["selected"]["execution_status"] != "executable"
