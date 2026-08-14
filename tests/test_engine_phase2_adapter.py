from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2, run_engine_phase2
import logging
import core.engine_phase2_adapter as phase2_adapter
import time
import pytest
from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair


@pytest.fixture(autouse=True)
def canonical_feed_artifact(tmp_path, monkeypatch):
    make_valid_canonical_feed_pair(tmp_path)
    monkeypatch.setattr(phase2_adapter, "logs_dir", lambda: tmp_path)


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


def test_build_candidates_phase2_aggregates_invalid_candidate_logging(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "PHASE2_INVALID_CANDIDATE_LOG_SAMPLE_LIMIT", 2, raising=False)
    with caplog.at_level(logging.WARNING):
        ranked = build_candidates_phase2(
            [
                {},
                {"trade_id": "BAD-1"},
                {
                    "trade_id": "GOOD",
                    "symbol": "NIFTY",
                    "final_score": 0.81,
                    "spread_pct": 0.01,
                    "execution_allowed": True,
                    "tradable": True,
                    "execution_ok": True,
                    "liquidity_score": 0.9,
                },
            ]
        )

    assert [row["trade_id"] for row in ranked] == ["GOOD"]
    assert "PHASE2: invalid candidates skipped count=2" in caplog.text
    assert "PHASE2: invalid candidate skipped trade_id=" not in caplog.text


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


def test_build_candidates_phase2_applies_market_context_fallbacks(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SPREAD_FALLBACK_PCT", 0.003, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_LIQUIDITY_FALLBACK_SCORE", 0.5, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "CTX_FALLBACK",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": None,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": None,
                "quote_source": None,
            }
        ]
    )
    assert len(ranked) == 1
    assert ranked[0]["spread_pct"] == 0.003
    assert ranked[0]["liquidity_score"] == 0.5
    assert ranked[0]["quote_source"] == "unknown"
    assert "unknown_quote_source" in list(ranked[0].get("phase2_soft_penalties") or [])


def test_build_candidates_phase2_derives_liquidity_from_book_when_missing(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.03, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "CTX_LIQ_BOOK",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": None,
                "best_bid": 99.0,
                "best_ask": 100.0,
                "current_ltp": 99.5,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": None,
                "quote_source": "tick_store",
            }
        ]
    )
    assert len(ranked) == 1
    assert ranked[0]["phase2_liquidity_derived_from_book"] is True
    assert float(ranked[0]["liquidity_score"]) > 0.0
    assert "phase2_liquidity_fallback_used" not in ranked[0]


def test_build_candidates_phase2_caps_precomputed_liquidity_on_split_brain_quote_bundle(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.03, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "CTX_LIQ_SPLIT_BRAIN",
                "symbol": "NIFTY",
                "final_score": 0.8,
                "spread_pct": 0.001,
                "best_bid": 389.05,
                "best_ask": 390.2,
                "current_ltp": 1.7,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.7,
                "liquidity_score": 1.0,
                "quote_source": "tick_store",
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_soft_degrades_noncritical_execution_context(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(
        cfg,
        "PHASE2_SOFT_CONTEXT_REASON_CODES",
        "missing_rr_context,missing_liquidity_context,missing_spread_context,missing_timing_context,unknown_quote_source",
        raising=False,
    )
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "SOFT_DEGRADE_PASS",
                "symbol": "BANKNIFTY",
                "candidate_status": "near_executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": False,
                "tradable": False,
                "execution_ok": False,
                "execution_score": 0.1,
                "liquidity_score": 0.5,
                "spread_pct": None,
                "quote_source": "unknown",
                "penalty_reasons": [
                    "missing_rr_context",
                    "missing_liquidity_context",
                    "missing_spread_context",
                    "missing_timing_context",
                ],
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["SOFT_DEGRADE_PASS"]
    assert "execution_context_degraded" in list(ranked[0].get("phase2_soft_penalties") or [])


def test_build_candidates_phase2_keeps_critical_execution_failure_hard_block(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "CRITICAL_BLOCK",
                "symbol": "SENSEX",
                "candidate_status": "near_executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": False,
                "tradable": False,
                "execution_ok": False,
                "execution_score": 0.1,
                "liquidity_score": 0.5,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "hard_blockers": ["FEED_STALE"],
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_soft_degrades_quality_only_failure(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_QUALITY_SCORE", 0.3, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_DEGRADE_PENALTY", 0.1, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "QUALITY_ONLY_SOFT",
                "symbol": "NIFTY",
                "candidate_status": "near_executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.55,
                "execution_quality_score": 0.24,
                "liquidity_score": 0.6,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.72,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["QUALITY_ONLY_SOFT"]
    assert "soft_execution_degraded" in list(ranked[0].get("phase2_soft_penalties") or [])
    assert ranked[0].get("phase2_soft_degrade_reason") == "execution_quality_low"
    assert ranked[0].get("max_final_action") == "QUEUE_ONLY"
    assert float(ranked[0]["final_score"]) < 0.72


def test_build_candidates_phase2_quality_failure_with_critical_reason_stays_hard_block(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_QUALITY_SCORE", 0.3, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "QUALITY_BUT_CRITICAL",
                "symbol": "BANKNIFTY",
                "candidate_status": "near_executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.55,
                "execution_quality_score": 0.24,
                "liquidity_score": 0.6,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "hard_blockers": ["UNRESOLVED_CONTRACT"],
                "final_score": 0.75,
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_soft_degrades_noncritical_execution_not_ready(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "NONCRITICAL_EXEC_NOT_READY",
                "symbol": "BANKNIFTY",
                "candidate_status": "executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": False,
                "execution_score": 0.62,
                "execution_quality_score": 0.62,
                "liquidity_score": 0.6,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "penalty_reasons": ["unknown_quote_source"],
                "final_score": 0.71,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["NONCRITICAL_EXEC_NOT_READY"]
    assert "soft_execution_not_ready" in list(ranked[0].get("phase2_soft_penalties") or [])
    assert ranked[0].get("phase2_soft_degrade_reason") == "execution_not_ready_noncritical"
    assert ranked[0].get("max_final_action") == "QUEUE_ONLY"
    assert float(ranked[0]["final_score"]) < 0.71


def test_build_candidates_phase2_soft_not_ready_reason_survives_low_execution_score(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "SOFT_STALE_QUOTE_LOW_SCORE",
                "symbol": "SENSEX",
                "candidate_status": "executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": False,
                "order_policy_reason": "stale_quote",
                "execution_score": 0.18,
                "execution_quality_score": 0.18,
                "liquidity_score": 0.6,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.68,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["SOFT_STALE_QUOTE_LOW_SCORE"]
    assert "soft_execution_not_ready" in list(ranked[0].get("phase2_soft_penalties") or [])
    assert ranked[0].get("phase2_soft_degrade_reason") == "execution_not_ready_noncritical"
    assert ranked[0].get("max_final_action") == "QUEUE_ONLY"


def test_build_candidates_phase2_soft_not_ready_fallbacks_on_moderate_liquidity_without_reason(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    monkeypatch.setattr(
        cfg,
        "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_FALLBACK_ENABLE",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        cfg,
        "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN",
        0.5,
        raising=False,
    )
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "SOFT_LIQUIDITY_FALLBACK",
                "symbol": "SENSEX",
                "candidate_status": "executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": False,
                "execution_score": 0.18,
                "execution_quality_score": 0.18,
                "liquidity_score": 0.5,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.68,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["SOFT_LIQUIDITY_FALLBACK"]
    assert "soft_execution_not_ready" in list(ranked[0].get("phase2_soft_penalties") or [])
    assert ranked[0].get("phase2_soft_degrade_reason") == "execution_not_ready_noncritical"
    assert ranked[0].get("max_final_action") == "QUEUE_ONLY"


def test_build_candidates_phase2_missing_quote_not_ready_stays_hard_block(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "HARD_MISSING_QUOTE",
                "symbol": "SENSEX",
                "candidate_status": "executable",
                "execution_status": "queue_only",
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": False,
                "order_policy_reason": "missing_quote",
                "execution_score": 0.18,
                "execution_quality_score": 0.18,
                "liquidity_score": 0.6,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.68,
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_recomputes_zero_placeholder_final_score(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.5, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "ZERO_PLACEHOLDER",
                "symbol": "NIFTY",
                "final_score": 0.0,
                "rank_score": 0.42,
                "confidence": 0.39,
                "confidence_final": 0.39,
                "gating_final_confidence": 0.39,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.62,
                "liquidity_score": 0.7,
                "spread_pct": 0.004,
                "quote_source": "tick_store",
            }
        ]
    )
    assert len(ranked) == 1
    assert float(ranked[0]["final_score"]) > 0.0
    assert bool((ranked[0].get("phase2_score_detail") or {}).get("phase2_recomputed_final_score")) is True


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


def test_run_engine_phase2_strict_mode_disables_forced_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.9, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_MIN_SCORE", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_ALLOW_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)

    out = run_engine_phase2(
        [
            {
                "trade_id": "STRICT_WEAK_BUT_VALID",
                "symbol": "NIFTY",
                "final_score": 0.11,
                "execution_mode": "SIM",
                "spread_pct": 0.005,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.8,
                "execution_entry": 100.0,
                "stop_loss": 80.0,
                "target": 130.0,
                "quote_source": "tick_store",
            }
        ]
    )
    assert out["state"] == "WATCHLIST"
    assert out["reason"] != "forced_fallback_execution"


def test_soft_reject_weak_signal_candidates_are_queue_capped(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.4, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", True, raising=False)
    raw = [
        {
            "trade_id": "TB_SOFT_WEAK",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_allowed": True,
            "tradable": True,
            "execution_ok": True,
            "execution_score": 0.9,
            "execution_quality_score": 0.9,
            "liquidity_score": 0.8,
            "spread_pct": 0.003,
            "quote_source": "tick_store",
            "raw_rank_score": 0.9,
            "rank_score": 0.9,
            "final_score": 0.9,
            "source_flags": {
                "soft_reject_reason": "weak_signal",
                "candidate_origin": "softened_builder_path",
            },
        }
    ]
    ranked = build_candidates_phase2(raw)
    assert len(ranked) == 1
    assert ranked[0].get("max_final_action") == "QUEUE_ONLY"
    assert ranked[0].get("truth_allows_execution") is False
    assert ranked[0].get("execution_allowed") is False

    out = run_engine_phase2(raw)
    assert out["state"] == "WATCHLIST"
    assert out["reason"] == "queue_only_cap"


def test_soft_reject_weak_signal_defaults_to_soft_penalty_not_hard_cap(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.4, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_WEAK_SIGNAL_QUEUE_CAP_ENABLE", False, raising=False)
    raw = [
        {
            "trade_id": "TB_SOFT_WEAK_RELAXED",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_allowed": True,
            "tradable": True,
            "execution_ok": True,
            "execution_score": 0.9,
            "execution_quality_score": 0.9,
            "liquidity_score": 0.8,
            "spread_pct": 0.003,
            "quote_source": "tick_store",
            "raw_rank_score": 0.9,
            "rank_score": 0.9,
            "final_score": 0.9,
            "source_flags": {
                "soft_reject_reason": "weak_signal",
                "candidate_origin": "softened_builder_path",
            },
        }
    ]
    ranked = build_candidates_phase2(raw)
    assert len(ranked) == 1
    assert ranked[0].get("phase2_soft_degrade_reason") == "weak_signal_soft_penalty"
    assert ranked[0].get("max_final_action") != "QUEUE_ONLY"
    assert ranked[0].get("execution_allowed") is True

    out = run_engine_phase2(raw)
    assert out["state"] == "ENTER"


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


def test_run_engine_phase2_respects_queue_only_cap_even_with_enter_score(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.6, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", False, raising=False)
    out = run_engine_phase2(
        [
            {
                "trade_id": "QUEUE_CAP",
                "symbol": "NIFTY",
                "final_score": 0.91,
                "max_final_action": "QUEUE_ONLY",
                "spread_pct": 0.004,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "liquidity_score": 0.8,
            }
        ]
    )
    assert out["state"] == "WATCHLIST"
    assert out["reason"] == "queue_only_cap"


def test_build_candidates_phase2_strict_mode_drops_soft_reject_placeholders(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "tbsoft_NIFTY_1",
                "symbol": "NIFTY",
                "candidate_origin": "softened_builder_path",
                "strategy_family": "builder_soft_reject",
                "candidate_status": "near_executable",
                "execution_status": "queue_only",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "spread_pct": 0.003,
                "liquidity_score": 0.7,
                "quote_source": "tick_store",
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_strict_mode_drops_degraded_context(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "STRICT_DROP_CONTEXT",
                "symbol": "BANKNIFTY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "spread_pct": 0.003,
                "liquidity_score": 0.7,
                "quote_source": "tick_store",
                "penalty_reasons": ["rr_estimated_context"],
                "execution_entry": 120.0,
                "stop_loss": 100.0,
                "target": 150.0,
            }
        ]
    )
    assert ranked == []


def test_build_candidates_phase2_strict_mode_keeps_clean_real_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "STRICT_KEEP_REAL",
                "symbol": "NIFTY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "execution_quality_score": 0.8,
                "spread_pct": 0.003,
                "liquidity_score": 0.8,
                "quote_source": "tick_store",
                "execution_entry": 180.0,
                "display_entry": 180.0,
                "entry": 180.0,
                "stop_loss": 150.0,
                "target": 230.0,
                "final_score": 0.7,
            }
        ]
    )
    assert [row["trade_id"] for row in ranked] == ["STRICT_KEEP_REAL"]


def test_build_candidates_phase2_injects_profile_rejection_setup_fields():
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "PR_SETUP_1",
                "symbol": "NIFTY",
                "strategy_family": "profile_rejection",
                "direction": "BUY_CALL",
                "execution_entry": 150.0,
                "stop_loss": 120.0,
                "target": 210.0,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "liquidity_score": 0.8,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.7,
            }
        ]
    )
    assert len(ranked) == 1
    row = ranked[0]
    assert row.get("profile_rejection_detected") is True
    assert row.get("setup_name") == "mean_reversion_profile_rejection"
    assert row.get("decision_playbook") == "profile_rejection"
    assert float(row.get("setup_score") or 0.0) > 0.0
    assert float(row.get("trigger_score") or 0.0) > 0.0
    assert float(row.get("entry_quality_score") or 0.0) > 0.0


def test_build_candidates_phase2_profile_rejection_not_detected_without_identity():
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "PR_SETUP_2",
                "symbol": "NIFTY",
                "strategy_family": "ensemble_opt",
                "direction": "BUY_CALL",
                "execution_entry": 150.0,
                "stop_loss": 120.0,
                "target": 210.0,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.8,
                "liquidity_score": 0.8,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.7,
            }
        ]
    )
    assert len(ranked) == 1
    assert ranked[0].get("profile_rejection_detected") is False


def test_build_candidates_phase2_selects_profile_rejection_playbook_in_range(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "PLAYBOOK_RANGE_1",
                "symbol": "NIFTY",
                "regime": "RANGE",
                "strategy_family": "profile_rejection",
                "direction": "BUY_CALL",
                "execution_entry": 203.0,
                "display_entry": 203.0,
                "entry": 203.0,
                "stop_loss": 170.0,
                "target": 250.0,
                "day_high": 200.0,
                "day_low": 180.0,
                "candle_open": 198.0,
                "candle_close": 203.0,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.85,
                "liquidity_score": 0.8,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.7,
            }
        ]
    )
    assert len(ranked) == 1
    row = ranked[0]
    assert row.get("selected_playbook") == "profile_rejection"
    assert row.get("decision_playbook") == "profile_rejection"
    assert row.get("profile_rejection_detected") is True


def test_build_candidates_phase2_selects_breakout_playbook_in_trend(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "PLAYBOOK_TREND_1",
                "symbol": "BANKNIFTY",
                "regime": "TREND",
                "strategy_family": "ensemble_opt",
                "direction": "BUY_CALL",
                "execution_entry": 305.0,
                "display_entry": 305.0,
                "entry": 305.0,
                "stop_loss": 270.0,
                "target": 360.0,
                "day_high": 300.0,
                "day_low": 280.0,
                "candle_open": 297.0,
                "candle_close": 305.0,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.85,
                "liquidity_score": 0.8,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.7,
            }
        ]
    )
    assert len(ranked) == 1
    row = ranked[0]
    assert row.get("selected_playbook") == "breakout_continuation"
    assert row.get("decision_playbook") == "breakout_continuation"
    assert row.get("breakout_detected") is True


def test_build_candidates_phase2_filters_when_no_playbook_detected(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", True, raising=False)
    ranked = build_candidates_phase2(
        [
            {
                "trade_id": "PLAYBOOK_NONE_1",
                "symbol": "NIFTY",
                "regime": "RANGE",
                "strategy_family": "ensemble_opt",
                "direction": "BUY_CALL",
                "execution_entry": 150.0,
                "display_entry": 150.0,
                "entry": 150.0,
                "stop_loss": 120.0,
                "target": 200.0,
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "execution_score": 0.85,
                "liquidity_score": 0.8,
                "spread_pct": 0.003,
                "quote_source": "tick_store",
                "final_score": 0.7,
            }
        ]
    )
    assert ranked == []
