from __future__ import annotations

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
