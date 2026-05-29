from __future__ import annotations

from config import config as cfg
from core.engine_phase2_adapter import run_engine_phase2
from core.live_fallback_execution_contract import (
    LIVE_FALLBACK_EXECUTION_BLOCKED,
    enforce_live_fallback_execution_contract,
    is_fallback_execution_candidate,
)
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


def test_live_startup_fails_closed_when_force_fallback_execution_enabled_alone():
    decision = assess_runtime_boot_safety(
        env={
            "EXECUTION_MODE": "LIVE",
            "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE": "true",
        }
    )
    assert decision.allowed is False
    assert "LIVE_UNSAFE_FLAG:PHASE2_FORCE_FALLBACK_EXECUTION" in decision.fatal_reasons


def test_live_startup_fails_closed_when_force_fallback_allow_live_enabled_alone():
    decision = assess_runtime_boot_safety(
        env={
            "EXECUTION_MODE": "LIVE",
            "PHASE2_FORCE_FALLBACK_ALLOW_LIVE": "true",
        }
    )
    assert decision.allowed is False
    assert "LIVE_UNSAFE_FLAG:PHASE2_FORCE_FALLBACK_EXECUTION" in decision.fatal_reasons


def test_live_fallback_contract_blocks_unknown_quote_source():
    row = enforce_live_fallback_execution_contract(
        {
            "trade_id": "UNKNOWN_QUOTE_HIGH",
            "symbol": "NIFTY",
            "candidate_status": "executable",
            "execution_status": "executable",
            "execution_allowed": True,
            "truth_allows_execution": True,
            "tradable": True,
            "quote_source": "unknown",
            "final_score": 0.99,
        },
        "LIVE",
    )

    assert row["execution_allowed"] is False
    assert row["truth_allows_execution"] is False
    assert row["tradable"] is False
    assert row["execution_ok"] is False
    assert row["forced_fallback_execution"] is False
    assert row["candidate_status"] == "watchlist"
    assert row["execution_status"] == "not_executable"
    assert row["max_final_action"] == "QUEUE_ONLY"
    assert row["primary_blocker"] == LIVE_FALLBACK_EXECUTION_BLOCKED
    assert LIVE_FALLBACK_EXECUTION_BLOCKED in row["hard_blockers"]


def test_live_fallback_contract_blocks_nested_source_flag_fallback():
    assert is_fallback_execution_candidate(
        {
            "trade_id": "NESTED_FALLBACK",
            "symbol": "NIFTY",
            "quote_source": "kite_depth",
            "source_flags": {"synthetic_quote_used": True},
        }
    ) is True

    row = enforce_live_fallback_execution_contract(
        {
            "trade_id": "NESTED_FALLBACK",
            "symbol": "NIFTY",
            "quote_source": "kite_depth",
            "source_flags": {"synthetic_quote_used": True},
            "execution_allowed": True,
            "truth_allows_execution": True,
            "tradable": True,
        },
        "LIVE",
    )

    assert row["execution_allowed"] is False
    assert row["source_flags"]["live_fallback_execution_blocked"] is True


def test_live_fallback_contract_preserves_paper_fallback_execution_shape():
    candidate = {
        "trade_id": "PAPER_FALLBACK",
        "symbol": "NIFTY",
        "candidate_status": "executable",
        "execution_status": "executable",
        "execution_allowed": True,
        "truth_allows_execution": True,
        "tradable": True,
        "forced_fallback_execution": True,
        "quote_source": "fallback",
    }

    row = enforce_live_fallback_execution_contract(candidate, "PAPER")
    assert row["forced_fallback_execution"] is True
    assert row["execution_status"] == "executable"
    assert row["candidate_status"] == "executable"


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
    assert result["reason"] in {
        "live_fallback_candidate_blocked",
        "live_forced_fallback_disabled",
    }
    assert result["selected"]["live_fallback_execution_blocked"] is True
    assert result["selected"]["execution_status"] != "executable"
