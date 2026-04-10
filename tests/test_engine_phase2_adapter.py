from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2, run_engine_phase2
import logging
import core.engine_phase2_adapter as phase2_adapter
import time


def test_build_candidates_phase2_applies_hard_filters(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.03, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35, raising=False)
    candidates = [
        {
            "trade_id": "PASS",
            "symbol": "NIFTY",
            "final_score": 0.81,
            "spread_pct": 0.01,
            "execution_allowed": True,
            "tradable": True,
            "execution_ok": True,
            "liquidity_score": 0.9,
        },
        {
            "trade_id": "BLOCK_SPREAD",
            "symbol": "NIFTY",
            "final_score": 0.95,
            "spread_pct": 0.08,
            "execution_allowed": True,
            "tradable": True,
            "execution_ok": True,
            "liquidity_score": 0.9,
        },
        {
            "trade_id": "BLOCK_EXEC",
            "symbol": "NIFTY",
            "final_score": 0.94,
            "spread_pct": 0.01,
            "execution_allowed": False,
            "tradable": True,
            "execution_ok": True,
            "liquidity_score": 0.9,
        },
        {
            "trade_id": "BLOCK_LIQ",
            "symbol": "NIFTY",
            "final_score": 0.93,
            "spread_pct": 0.01,
            "execution_allowed": True,
            "tradable": True,
            "execution_ok": True,
            "liquidity_score": 0.2,
        },
    ]

    ranked = build_candidates_phase2(candidates)

    assert [row["trade_id"] for row in ranked] == ["PASS"]
    assert ranked[0]["phase2_hard_filters"]["spread_ok"] is True
    assert ranked[0]["phase2_hard_filters"]["execution_ok"] is True
    assert ranked[0]["phase2_hard_filters"]["liquidity_ok"] is True


def test_run_engine_phase2_enters_top_ranked_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    result = run_engine_phase2(
        [
            {
                "trade_id": "HIGH",
                "symbol": "BANKNIFTY",
                "final_score": 0.88,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            },
            {
                "trade_id": "LOW",
                "symbol": "BANKNIFTY",
                "final_score": 0.62,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            },
        ],
    )
    assert result["state"] == "ENTER"
    assert result["selected"]["trade_id"] == "HIGH"
    assert result["next_active_trade"]["trade_id"] == "HIGH"
    assert len(result["ranked"]) >= 1


def test_run_engine_phase2_replace_and_hold_are_state_driven(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REPLACE_MIN_ABS_DELTA", 0.12, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REPLACE_MIN_REL_DELTA", 0.2, raising=False)
    active_trade = {
        "trade_id": "ACTIVE",
        "symbol": "NIFTY",
        "final_score": 0.75,
    }

    hold_result = run_engine_phase2(
        [
            {
                "trade_id": "SMALL_UPGRADE",
                "symbol": "NIFTY",
                "final_score": 0.82,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            }
        ],
        active_trade=active_trade,
    )
    assert hold_result["state"] == "HOLD"
    assert hold_result["selected"]["trade_id"] == "ACTIVE"
    assert hold_result["next_active_trade"]["trade_id"] == "ACTIVE"

    replace_result = run_engine_phase2(
        [
            {
                "trade_id": "BIG_UPGRADE",
                "symbol": "NIFTY",
                "final_score": 0.95,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            }
        ],
        active_trade=active_trade,
    )
    assert replace_result["state"] == "REPLACE"
    assert replace_result["selected"]["trade_id"] == "BIG_UPGRADE"
    assert replace_result["next_active_trade"]["trade_id"] == "BIG_UPGRADE"


def test_run_engine_phase2_watchlist_and_no_trade_paths(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    watchlist = run_engine_phase2(
        [
            {
                "trade_id": "LOW_CONF",
                "symbol": "SENSEX",
                "final_score": 0.4,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            }
        ],
    )
    assert watchlist["state"] == "WATCHLIST"
    assert watchlist["selected"]["trade_id"] == "LOW_CONF"

    no_trade = run_engine_phase2(
        [
            {
                "trade_id": "FILTERED_OUT",
                "symbol": "SENSEX",
                "final_score": 0.95,
                "spread_pct": 0.5,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.9,
            }
        ],
    )
    assert no_trade["state"] == "NO_TRADE"
    assert no_trade["selected"] is None


def test_build_candidates_phase2_uses_dynamic_spread_threshold(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", 0.02, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "HIGH_VOL_PASS",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": 0.019,
                "volatility": 0.9,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": 0.8,
            },
            {
                "trade_id": "LOW_VOL_BLOCK",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": 0.019,
                "volatility": 0.5,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": 0.8,
            },
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["HIGH_VOL_PASS"]


def test_run_engine_phase2_selected_payload_has_symbol_and_score(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    out = run_engine_phase2(
        [
            {
                "trade_id": "NORMALIZED",
                "symbol": "BANKNIFTY",
                "signal_score": "0.92",
                "execution_score": "0.83",
                "liquidity_score": "0.81",
                "regime_score": "0.75",
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
            }
        ]
    )
    assert out["state"] == "ENTER"
    assert out["selected"]["symbol"] == "BANKNIFTY"
    assert float(out["selected"]["score"]) > 0.0


def test_build_candidates_phase2_skips_invalid_symbol_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "INVALID",
                "symbol": None,
                "execution_score": 0.9,
                "liquidity_score": 0.9,
                "spread_pct": 0.01,
            },
            {
                "trade_id": "VALID",
                "symbol": "NIFTY",
                "final_score": 0.9,
                "execution_score": 0.9,
                "liquidity_score": 0.9,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
            },
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["VALID"]


def test_build_candidates_phase2_warns_when_empty_after_filtering(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.99, raising=False)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="phase2"):
        ranked = build_candidates_phase2(
            [
                {
                    "trade_id": "FILTERED",
                    "symbol": "BANKNIFTY",
                    "execution_score": 0.5,
                    "liquidity_score": 0.8,
                    "spread_pct": 0.01,
                    "execution_allowed": True,
                    "tradable": True,
                    "execution_ok": True,
                }
            ]
        )
    assert ranked == []
    assert "No valid candidates after filtering" in caplog.text


def test_build_candidates_phase2_time_of_day_spread_multiplier(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", 0.02, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MARKET_START_HOUR", 9, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MARKET_END_HOUR", 15, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SPREAD_OFFHOURS_MULT", 1.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35, raising=False)
    monkeypatch.setattr(
        phase2_adapter,
        "_candidate_hour",
        lambda c: 10 if c.get("trade_id") == "IN_HOURS_BLOCK" else 8,
    )
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "IN_HOURS_BLOCK",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": 0.02,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "liquidity_score": 0.8,
            },
            {
                "trade_id": "OFF_HOURS_PASS",
                "symbol": "NIFTY",
                "final_score": 0.79,
                "spread_pct": 0.02,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "liquidity_score": 0.8,
            },
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["OFF_HOURS_PASS"]


def test_run_engine_phase2_clears_stale_active_trade(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_ACTIVE_TRADE_MAX_AGE_SEC", 30, raising=False)
    stale_active = {
        "trade_id": "STALE_ACTIVE",
        "symbol": "NIFTY",
        "score": 0.95,
        "decision_ts_epoch": time.time() - 120,
    }
    out = run_engine_phase2(
        [
            {
                "trade_id": "FRESH_NEW",
                "symbol": "NIFTY",
                "signal_score": 0.9,
                "execution_score": 0.8,
                "liquidity_score": 0.8,
                "regime_score": 0.8,
                "spread_pct": 0.005,
            }
        ],
        active_trade=stale_active,
    )
    assert out["state"] == "ENTER"
    assert out["selected"]["trade_id"] == "FRESH_NEW"


def test_build_candidates_phase2_applies_data_fallback_defaults(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "FALLBACK_FIELDS",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": 0.01,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": 0.8,
                "quote_age_sec": None,
                "depth_score": 0.0,
                "tick_volume": None,
            }
        ]
    )
    assert len(ranked) == 1
    assert ranked[0]["quote_age_sec"] == 1.0
    assert ranked[0]["depth_score"] == 0.5
    assert ranked[0]["tick_volume"] == 1.0


def test_run_engine_phase2_forced_fallback_execution_when_no_enter(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.9, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_MIN_SCORE", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_ALLOW_LIVE", False, raising=False)

    out = run_engine_phase2(
        [
            {
                "trade_id": "WEAK_BUT_VALID",
                "symbol": "NIFTY",
                "final_score": 0.11,
                "execution_mode": "SIM",
                "spread_pct": 0.005,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.8,
            }
        ]
    )
    assert out["state"] == "ENTER"
    assert out["reason"] == "forced_fallback_execution"
    assert out["selected"]["execution_status"] == "executable"


def test_build_candidates_phase2_relaxes_no_signal_and_latency(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_RELAX_ALLOW_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_RELAX_NO_SIGNAL", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_DISABLE_LATENCY_BLOCK", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35, raising=False)

    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "NO_SIGNAL_LATENCY",
                "symbol": "BANKNIFTY",
                "execution_mode": "SIM",
                "final_score": 0.2,
                "spread_pct": 0.005,
                "execution_allowed": False,
                "tradable": False,
                "execution_ok": False,
                "execution_blocked": True,
                "execution_block_reason": "latency_guard_cooldown",
                "reject_reason": "no_signal",
                "liquidity_score": 0.7,
                "execution_score": 0.7,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["NO_SIGNAL_LATENCY"]


def test_run_engine_phase2_does_not_force_fallback_in_live_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.9, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_MIN_SCORE", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_ALLOW_LIVE", False, raising=False)

    out = run_engine_phase2(
        [
            {
                "trade_id": "LIVE_WEAK",
                "symbol": "NIFTY",
                "final_score": 0.11,
                "execution_mode": "LIVE",
                "spread_pct": 0.005,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.8,
            }
        ]
    )
    assert out["state"] == "WATCHLIST"
