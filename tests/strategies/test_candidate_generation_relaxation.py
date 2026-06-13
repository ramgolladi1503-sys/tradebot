from __future__ import annotations

from datetime import date

import strategies.ensemble as ensemble
import strategies.nifty_intraday as nifty_intraday
import strategies.zero_hero as zero_hero


def test_nifty_intraday_candidate_survives_moderate_imperfection():
    debug = {}

    signal = nifty_intraday.generate_signal(
        ltp=100.12,
        vwap=100.0,
        bias=None,
        vwap_buffer=0.0015,
        min_move=0.001,
        debug_stats=debug,
    )

    assert signal is not None
    assert signal["direction"] == "BUY_CALL"
    assert "below_primary_vwap_buffer" in signal["soft_flags"]
    assert "bias_missing" in signal["soft_flags"]
    assert debug["candidates_considered"] == 1
    assert debug["candidates_rejected_pre_score"] == 0
    assert debug["candidates_scored"] == 1


def test_ensemble_scores_soft_trend_mismatch_and_records_debug():
    market_data = {
        "regime": "TREND",
        "ltp": 100.25,
        "vwap": 100.0,
        "vwap_slope": -0.01,
        "rsi_mom": 0.1,
        "atr": 0.6,
        "orb_high": 101.0,
        "orb_low": 99.0,
        "vol_z": 0.3,
    }

    signal = ensemble.ensemble_signal(market_data)

    assert signal is not None
    assert signal.direction == "BUY_CALL"
    assert "soft slope mismatch" in signal.reason
    stats = market_data["strategy_debug"]["ensemble"]
    assert stats["candidates_considered"] >= 1
    assert stats["candidates_scored"] >= 1


def test_zero_hero_strategy_accepts_expiry_window(monkeypatch):
    monkeypatch.setattr(zero_hero, "next_expiry", lambda _symbol: date(2026, 3, 12))
    debug = {}

    trades = zero_hero.zero_hero_strategy(
        "NIFTY",
        22050.0,
        {"bias": "bullish"},
        current_date=date(2026, 3, 11),
        debug_stats=debug,
    )

    assert len(trades) == 1
    assert trades[0]["option_type"] == "CE"
    assert debug["candidates_considered"] == 1
    assert debug["candidates_scored"] == 1
