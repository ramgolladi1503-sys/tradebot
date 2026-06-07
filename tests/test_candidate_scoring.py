from __future__ import annotations

from config import config as cfg
from core.candidate_scoring import score_candidate


def test_score_candidate_strong_inputs_is_high_and_deterministic():
    candidate = {
        "trade_id": "T-STRONG",
        "trade_score": 82.0,
        "trade_alignment": 0.76,
        "builder_confidence": 0.79,
        "instrument_token": 99123,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 114.0,
        "volume": 85000,
        "oi": 140000,
        "spread_pct": 0.004,
        "pattern_flags": ["breakout", "trend"],
        "quote_ok": True,
    }
    market_data = {
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 4.0,
        "quote_source": "tick_store",
        "current_ltp": 101.5,
    }
    context = {
        "mode": "LIVE",
        "market_open": True,
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }

    first = score_candidate(candidate, market_data, context)
    second = score_candidate(candidate, market_data, context)

    assert first == second
    assert first["confidence_raw"] > 0.72
    assert first["confidence_final"] > 0.66
    assert first["rank_score"] > 0.65
    assert first["opportunity_score"] > 0.65
    assert first["score_breakdown"]["components"]["setup_strength"] > 0.7
    assert first["penalty_reasons"] == []


def test_score_candidate_degrades_gracefully_when_some_inputs_are_missing():
    candidate = {
        "trade_id": "T-DEGRADED",
        "builder_confidence": None,
        "entry_price": 120.0,
        "stop_loss": None,
        "target": None,
        "pattern_flags": ["watchlist"],
    }
    market_data = {
        "regime": "UNKNOWN",
        "market_open": False,
        "quote_source": "rest_fallback",
        "current_ltp": 121.0,
    }
    context = {
        "mode": "SIM",
        "market_open": False,
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }

    scored = score_candidate(candidate, market_data, context)

    assert 0.30 < scored["confidence_raw"] < 0.75
    assert 0.25 < scored["confidence_final"] < 0.70
    assert scored["rank_score"] > 0.20
    assert scored["opportunity_score"] > 0.20
    assert "rr_estimated_context" in scored["penalty_reasons"]
    assert scored["score_breakdown"]["missing_reasons"]


def test_score_candidate_missing_entry_still_flags_missing_rr_context():
    candidate = {
        "trade_id": "T-MISSING-RR",
        "builder_confidence": 0.31,
        "entry_price": None,
        "stop_loss": None,
        "target": None,
    }
    market_data = {
        "regime": "UNKNOWN",
        "market_open": True,
        "quote_source": "tick_store",
        "current_ltp": None,
    }
    context = {
        "mode": "LIVE",
        "market_open": True,
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }

    scored = score_candidate(candidate, market_data, context)

    assert "missing_rr_context" in scored["penalty_reasons"]
    assert "rr_estimated_context" not in scored["penalty_reasons"]


def test_score_candidate_weak_setup_is_penalized_without_zeroing_everything():
    candidate = {
        "trade_id": "T-WEAK",
        "trade_score": 0.18,
        "trade_alignment": 0.22,
        "entry_price": 100.0,
        "stop_loss": 98.5,
        "target": 101.0,
        "volume": 1200,
        "oi": 900,
        "spread_pct": 0.032,
        "countertrend": True,
        "hard_blockers": ["NO_LIVE_OPTION_FEED"],
        "soft_penalties": ["STALE_OPTION_LTP"],
    }
    market_data = {
        "regime": "PANIC",
        "market_open": True,
        "quote_age_sec": 420.0,
        "quote_source": "subscription_failed",
        "current_ltp": 100.3,
    }
    context = {
        "mode": "LIVE",
        "market_open": True,
        "blockers": ["NO_LIVE_OPTION_FEED", "STALE_OPTION_LTP"],
        "hard_blockers": ["NO_LIVE_OPTION_FEED"],
        "soft_penalties": ["STALE_OPTION_LTP"],
        "warnings": [],
    }

    scored = score_candidate(candidate, market_data, context)

    assert scored["confidence_raw"] < 0.45
    assert scored["confidence_final"] < 0.30
    assert scored["penalty_score"] > 0.20
    assert "NO_LIVE_OPTION_FEED" in scored["penalty_reasons"]
    assert "wide_spread" in scored["penalty_reasons"]
    assert "weak_risk_reward" in scored["penalty_reasons"]


def test_score_candidate_quote_consistency_degrades_liquidity_for_quote_valid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SCORING_LIQUIDITY_TARGET_VOLUME", 25000.0, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SCORING_LIQUIDITY_TARGET_OI", 50000.0, raising=False)
    base_candidate = {
        "trade_id": "T-LIQ-QUOTE-CONSISTENCY",
        "trade_score": 72.0,
        "trade_alignment": 0.70,
        "builder_confidence": 0.68,
        "instrument_token": 99123,
        "entry_price": 100.0,
        "stop_loss": 96.0,
        "target": 108.0,
        "volume": 250000,
        "oi": 350000,
        "spread_pct": 0.0015,
        "quote_ok": True,
    }
    market_data = {
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 0.8,
        "quote_source": "tick_store",
        "current_ltp": 100.2,
    }
    context = {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []}

    weak_quote = score_candidate(
        {
            **base_candidate,
            "quote_consistency_score": 0.25,
            "best_bid": 100.0,
            "best_ask": 100.15,
            "current_ltp": 99.2,
        },
        {**market_data, "quote_consistency_score": 0.25},
        context,
    )
    strong_quote = score_candidate(
        {
            **base_candidate,
            "quote_consistency_score": 1.0,
            "best_bid": 100.0,
            "best_ask": 100.15,
            "current_ltp": 100.1,
        },
        {**market_data, "quote_consistency_score": 1.0},
        context,
    )

    assert weak_quote["liquidity_score"] < strong_quote["liquidity_score"]
    assert weak_quote["confidence_final"] < strong_quote["confidence_final"]
    assert weak_quote["rank_score"] < strong_quote["rank_score"]


def test_score_candidate_liquidity_does_not_flatten_all_high_volume_rows(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SCORING_LIQUIDITY_TARGET_VOLUME", 25000.0, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SCORING_LIQUIDITY_TARGET_OI", 50000.0, raising=False)
    base_candidate = {
        "trade_id": "T-LIQ-SATURATION",
        "trade_score": 70.0,
        "trade_alignment": 0.68,
        "builder_confidence": 0.66,
        "instrument_token": 99123,
        "entry_price": 100.0,
        "stop_loss": 96.0,
        "target": 108.0,
        "spread_pct": 0.0012,
        "quote_consistency_score": 1.0,
        "quote_ok": True,
    }
    market_data = {
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 0.6,
        "quote_source": "tick_store",
        "current_ltp": 100.05,
        "quote_consistency_score": 1.0,
    }
    context = {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []}

    moderate = score_candidate(
        {**base_candidate, "volume": 100000, "oi": 150000},
        market_data,
        context,
    )
    extreme = score_candidate(
        {**base_candidate, "volume": 1000000000, "oi": 5000000},
        market_data,
        context,
    )

    assert moderate["liquidity_score"] < 1.0
    assert extreme["liquidity_score"] <= 1.0
    assert moderate["liquidity_score"] < extreme["liquidity_score"]


def test_score_candidate_strong_regime_and_consensus_separate_cleanly():
    strong = score_candidate(
        {
            "trade_id": "T-STRONG-SEPARATION",
            "trade_score": 84.0,
            "trade_alignment": 0.82,
            "builder_confidence": 0.86,
            "regime_alignment_score": 0.94,
            "family_consensus_score": 0.89,
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target": 114.0,
            "volume": 120000,
            "oi": 180000,
            "spread_pct": 0.003,
            "quote_ok": True,
            "pattern_flags": ["breakout", "trend"],
        },
        {
            "regime": "TREND",
            "market_open": True,
            "quote_age_sec": 1.5,
            "quote_source": "tick_store",
            "current_ltp": 100.8,
        },
        {
            "mode": "LIVE",
            "market_open": True,
            "blockers": [],
            "hard_blockers": [],
            "soft_penalties": [],
            "warnings": [],
        },
    )
    weak = score_candidate(
        {
            "trade_id": "T-WEAK-SEPARATION",
            "trade_score": 24.0,
            "trade_alignment": 0.26,
            "builder_confidence": 0.31,
            "regime_alignment_score": 0.21,
            "family_consensus_score": 0.18,
            "correlation_penalty": 0.34,
            "instrument_token": 99124,
            "entry_price": 100.0,
            "stop_loss": 99.4,
            "target": 100.8,
            "volume": 1200,
            "oi": 700,
            "spread_pct": 0.031,
            "quote_ok": False,
            "countertrend": True,
            "pattern_flags": ["watchlist"],
        },
        {
            "regime": "PANIC",
            "market_open": True,
            "quote_age_sec": 240.0,
            "quote_source": "subscription_failed",
            "current_ltp": 100.2,
        },
        {
            "mode": "LIVE",
            "market_open": True,
            "blockers": ["NO_LIVE_OPTION_FEED"],
            "hard_blockers": ["NO_LIVE_OPTION_FEED"],
            "soft_penalties": ["STALE_OPTION_LTP"],
            "warnings": [],
        },
    )

    assert strong["confidence_final"] > weak["confidence_final"]
    assert strong["rank_score"] > weak["rank_score"]
    assert strong["opportunity_score"] > weak["opportunity_score"]
    assert strong["rank_score"] - weak["rank_score"] >= 0.2
    assert strong["score_breakdown"]["components"]["regime_fit"] > weak["score_breakdown"]["components"]["regime_fit"]
    assert strong["score_breakdown"]["components"]["penalty_score"] < weak["score_breakdown"]["components"]["penalty_score"]


def test_score_candidate_bad_spread_is_penalized_below_good_spread():
    base = {
        "trade_id": "T-SPREAD-SEP",
        "trade_score": 68.0,
        "trade_alignment": 0.66,
        "builder_confidence": 0.64,
        "regime_alignment_score": 0.72,
        "family_consensus_score": 0.74,
        "instrument_token": 99123,
        "entry_price": 100.0,
        "stop_loss": 96.5,
        "target": 108.0,
        "volume": 50000,
        "oi": 95000,
        "quote_ok": True,
    }
    market_data = {
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 2.0,
        "quote_source": "tick_store",
        "current_ltp": 100.4,
    }
    context = {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []}

    good = score_candidate({**base, "spread_pct": 0.003}, market_data, context)
    bad = score_candidate({**base, "spread_pct": 0.034}, market_data, context)

    assert good["spread_score"] > bad["spread_score"]
    assert good["rank_score"] > bad["rank_score"]
    assert good["confidence_final"] > bad["confidence_final"]


def test_trend_regime_prefers_breakout_over_range_candidate():
    breakout = score_candidate(
        {
            "trade_id": "T-TREND-BREAKOUT",
            "strategy_family": "breakout",
            "trade_score": 78.0,
            "trade_alignment": 0.77,
            "builder_confidence": 0.80,
            "regime_alignment_score": 0.91,
            "family_consensus_score": 0.86,
            "pattern_flags": ["breakout", "trend"],
            "entry_condition": "vwap_reclaim",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 96.0,
            "target": 110.0,
            "volume": 120000,
            "oi": 160000,
            "spread_pct": 0.004,
            "quote_ok": True,
        },
        {"regime": "TREND", "market_open": True, "quote_age_sec": 1.0, "quote_source": "tick_store", "current_ltp": 100.5},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )
    range_style = score_candidate(
        {
            "trade_id": "T-TREND-RANGE",
            "strategy_family": "mean_reversion",
            "trade_score": 78.0,
            "trade_alignment": 0.77,
            "builder_confidence": 0.80,
            "regime_alignment_score": 0.31,
            "family_consensus_score": 0.34,
            "pattern_flags": ["range", "mean_reversion"],
            "entry_condition": "upper_extension_reversion",
            "instrument_token": 99124,
            "entry_price": 100.0,
            "stop_loss": 99.2,
            "target": 100.6,
            "volume": 120000,
            "oi": 160000,
            "spread_pct": 0.004,
            "quote_ok": True,
        },
        {"regime": "TREND", "market_open": True, "quote_age_sec": 1.0, "quote_source": "tick_store", "current_ltp": 100.5},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert breakout["rank_score"] > range_style["rank_score"]
    assert breakout["regime_profile"]["regime_bucket"] == "TREND"
    assert "trend_regime_breakout_momentum_preferred" in breakout["regime_profile"]["reasons"]
    assert "trend_regime_range_mismatch" in range_style["regime_profile"]["reasons"]


def test_range_regime_prefers_range_candidate_over_breakout_candidate():
    range_candidate = score_candidate(
        {
            "trade_id": "T-RANGE-CORE",
            "strategy_family": "mean_reversion",
            "trade_score": 74.0,
            "trade_alignment": 0.73,
            "builder_confidence": 0.76,
            "regime_alignment_score": 0.88,
            "family_consensus_score": 0.84,
            "entry_condition": "vwap_reclaim",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 99.1,
            "target": 100.8,
            "volume": 85000,
            "oi": 125000,
            "spread_pct": 0.004,
            "quote_ok": True,
        },
        {"regime": "RANGE", "market_open": True, "quote_age_sec": 1.2, "quote_source": "tick_store", "current_ltp": 100.1},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )
    breakout_candidate = score_candidate(
        {
            "trade_id": "T-RANGE-BREAKOUT",
            "strategy_family": "breakout",
            "trade_score": 74.0,
            "trade_alignment": 0.73,
            "builder_confidence": 0.76,
            "regime_alignment_score": 0.22,
            "family_consensus_score": 0.26,
            "entry_condition": "opening_range_breakout",
            "instrument_token": 99124,
            "entry_price": 100.0,
            "stop_loss": 99.4,
            "target": 101.2,
            "volume": 85000,
            "oi": 125000,
            "spread_pct": 0.004,
            "quote_ok": True,
        },
        {"regime": "RANGE", "market_open": True, "quote_age_sec": 1.2, "quote_source": "tick_store", "current_ltp": 100.1},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert range_candidate["rank_score"] > breakout_candidate["rank_score"]
    assert "range_regime_mean_reversion_preferred" in range_candidate["regime_profile"]["reasons"]
    assert "range_regime_breakout_penalty" in breakout_candidate["regime_profile"]["reasons"]


def test_chop_regime_penalizes_directional_candidates():
    chop = score_candidate(
        {
            "trade_id": "T-CHOP",
            "strategy_family": "breakout",
            "trade_score": 80.0,
            "trade_alignment": 0.81,
            "builder_confidence": 0.83,
            "regime_alignment_score": 0.76,
            "family_consensus_score": 0.74,
            "entry_condition": "vwap_reclaim",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 96.0,
            "target": 108.0,
            "volume": 100000,
            "oi": 130000,
            "spread_pct": 0.004,
            "quote_ok": True,
        },
        {"regime": "CHOP", "market_open": True, "quote_age_sec": 1.0, "quote_source": "tick_store", "current_ltp": 100.4},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert chop["rank_score"] < 0.55
    assert "chop_regime_directional_penalty" in chop["regime_profile"]["reasons"]


def test_expiry_regime_penalizes_bad_spread_and_liquidity_more():
    expiry = score_candidate(
        {
            "trade_id": "T-EXPIRY",
            "strategy_family": "expiry_scalp",
            "trade_score": 69.0,
            "trade_alignment": 0.68,
            "builder_confidence": 0.70,
            "regime_alignment_score": 0.71,
            "family_consensus_score": 0.73,
            "entry_condition": "time_window",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 98.8,
            "target": 101.4,
            "volume": 2400,
            "oi": 1800,
            "spread_pct": 0.028,
            "quote_ok": False,
        },
        {"regime": "EXPIRY", "market_open": True, "quote_age_sec": 3.0, "quote_source": "tick_store", "current_ltp": 100.2},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )
    normal = score_candidate(
        {
            "trade_id": "T-NORMAL",
            "strategy_family": "expiry_scalp",
            "trade_score": 69.0,
            "trade_alignment": 0.68,
            "builder_confidence": 0.70,
            "regime_alignment_score": 0.71,
            "family_consensus_score": 0.73,
            "entry_condition": "time_window",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 98.8,
            "target": 101.4,
            "volume": 2400,
            "oi": 1800,
            "spread_pct": 0.028,
            "quote_ok": False,
        },
        {"regime": "TREND", "market_open": True, "quote_age_sec": 3.0, "quote_source": "tick_store", "current_ltp": 100.2},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert expiry["rank_score"] < normal["rank_score"]
    assert expiry["score_breakdown"]["components"]["spread_score"] <= normal["score_breakdown"]["components"]["spread_score"]


def test_high_vol_regime_punishes_wide_spread_more_than_normal():
    high_vol = score_candidate(
        {
            "trade_id": "T-HIGH-VOL",
            "strategy_family": "volatility_expansion",
            "trade_score": 72.0,
            "trade_alignment": 0.72,
            "builder_confidence": 0.74,
            "regime_alignment_score": 0.84,
            "family_consensus_score": 0.79,
            "entry_condition": "volatility_expansion",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 96.5,
            "target": 108.5,
            "volume": 90000,
            "oi": 120000,
            "spread_pct": 0.032,
            "quote_ok": False,
        },
        {"regime": "HIGH_VOL", "market_open": True, "quote_age_sec": 2.5, "quote_source": "tick_store", "current_ltp": 100.3},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )
    normal = score_candidate(
        {
            "trade_id": "T-HIGH-VOL-NORMAL",
            "strategy_family": "volatility_expansion",
            "trade_score": 72.0,
            "trade_alignment": 0.72,
            "builder_confidence": 0.74,
            "regime_alignment_score": 0.84,
            "family_consensus_score": 0.79,
            "entry_condition": "volatility_expansion",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 96.5,
            "target": 108.5,
            "volume": 90000,
            "oi": 120000,
            "spread_pct": 0.032,
            "quote_ok": False,
        },
        {"regime": "TREND", "market_open": True, "quote_age_sec": 2.5, "quote_source": "tick_store", "current_ltp": 100.3},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert high_vol["rank_score"] < normal["rank_score"]
    assert high_vol["score_breakdown"]["components"]["spread_score"] <= normal["score_breakdown"]["components"]["spread_score"]


def test_low_vol_regime_penalizes_weak_breakout_without_confirmation():
    weak_breakout = score_candidate(
        {
            "trade_id": "T-LOW-VOL-WEAK",
            "strategy_family": "breakout",
            "trade_score": 34.0,
            "trade_alignment": 0.35,
            "builder_confidence": 0.33,
            "regime_alignment_score": 0.26,
            "family_consensus_score": 0.22,
            "entry_condition": "opening_range_breakout",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 99.6,
            "target": 100.7,
            "volume": 1600,
            "oi": 900,
            "spread_pct": 0.018,
            "quote_ok": False,
        },
        {"regime": "LOW_VOL", "market_open": True, "quote_age_sec": 6.0, "quote_source": "tick_store", "current_ltp": 100.05},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert weak_breakout["rank_score"] < 0.45
    assert "low_vol_weak_breakout_penalty" in weak_breakout["regime_profile"]["reasons"]


def test_unknown_regime_does_not_create_a_score_boost():
    unknown = score_candidate(
        {
            "trade_id": "T-UNKNOWN",
            "strategy_family": "breakout",
            "trade_score": 64.0,
            "trade_alignment": 0.62,
            "builder_confidence": 0.64,
            "regime_alignment_score": None,
            "family_consensus_score": None,
            "entry_condition": "vwap_reclaim",
            "instrument_token": 99123,
            "entry_price": 100.0,
            "stop_loss": 97.2,
            "target": 106.8,
            "volume": 32000,
            "oi": 64000,
            "spread_pct": 0.006,
            "quote_ok": True,
        },
        {"regime": None, "market_open": True, "quote_age_sec": 1.5, "quote_source": "tick_store", "current_ltp": 100.3},
        {"mode": "LIVE", "market_open": True, "blockers": [], "hard_blockers": [], "soft_penalties": [], "warnings": []},
    )

    assert unknown["regime_profile"]["regime_bucket"] == "UNKNOWN"
    assert unknown["regime_profile"]["penalty"] > 0.0
    assert "unknown_regime_conservative_profile" in unknown["regime_profile"]["reasons"]
