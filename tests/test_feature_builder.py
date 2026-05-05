import pandas as pd
from config import config as cfg
from core.feature_builder import add_indicators, assess_trade_feature_quality

def test_add_indicators_columns():
    df = pd.DataFrame({
        "open": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
        "high": [2]*15,
        "low": [1]*15,
        "close": [1]*15,
        "volume": [100]*15
    })
    out = add_indicators(df)
    assert "vwap" in out.columns
    assert "vwap_slope" in out.columns
    assert "rsi_mom" in out.columns
    assert "vol_z" in out.columns


def test_fresh_ltp_but_stale_bidask_is_not_fresh_quote_ok(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    monkeypatch.setattr(cfg, "DATA_TRUTH_MAX_CHAIN_SNAPSHOT_AGE_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.5,
            "ask": 100.5,
            "quote_ok": True,
            "ltp_age_sec": 0.5,
            "bid_age_sec": 4.0,
            "ask_age_sec": 4.5,
            "quote_age_sec": 0.5,
            "volume": 1000,
            "spread_source": "live_book",
        },
    )

    assert quality["data_state"] == "DATA_STALE"
    assert quality["fresh_quote_ok"] is False
    assert "stale_quote" in quality["issues"]


def test_missing_bidask_marks_data_partial_or_missing(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "SIM", "market_open": True},
        {
            "ltp": 100.0,
            "quote_ok": True,
            "ltp_age_sec": 0.5,
            "quote_age_sec": 0.5,
            "volume": 1000,
        },
    )

    assert quality["data_state"] in {"DATA_PARTIAL", "DATA_MISSING"}
    assert quality["quote_completeness"] in {"LTP_ONLY", "MISSING"}


def test_inconsistent_bid_ask_marks_data_inconsistent(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 101.0,
            "ask": 100.5,
            "quote_ok": True,
            "ltp_age_sec": 0.5,
            "bid_age_sec": 0.5,
            "ask_age_sec": 0.5,
            "quote_age_sec": 0.5,
            "volume": 1000,
        },
    )

    assert quality["data_state"] == "DATA_INCONSISTENT"
    assert quality["quote_consistency_ok"] is False
    assert "inconsistent_bid_ask" in quality["issues"]


def test_stale_cached_spread_is_not_liquidity_ok(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    monkeypatch.setattr(cfg, "DATA_TRUTH_MAX_CHAIN_SNAPSHOT_AGE_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.5,
            "bid_age_sec": 0.5,
            "ask_age_sec": 0.5,
            "chain_snapshot_age_sec": 5.0,
            "quote_age_sec": 0.5,
            "volume": 1000,
            "liquidity_cache_hit": True,
            "spread_source": "cache",
        },
    )

    assert quality["data_state"] == "DATA_STALE"
    assert quality["liquidity_ok"] is False
    assert quality["spread_ok"] is False


def test_data_confidence_degrades_smoothly_for_mild_staleness(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    fresh = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 1000,
            "spread_stability_score": 0.95,
        },
    )
    mild_stale = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 2.4,
            "bid_age_sec": 2.4,
            "ask_age_sec": 2.4,
            "quote_age_sec": 2.4,
            "volume": 1000,
            "spread_stability_score": 0.95,
        },
    )

    assert fresh["data_confidence"] > mild_stale["data_confidence"] > 0.1
    assert mild_stale["data_state"] == "DATA_STALE"


def test_fresh_but_unstable_spread_lowers_data_confidence(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 1000,
            "spread_change_ratio": 0.9,
        },
    )

    assert quality["data_state"] == "DATA_OK"
    assert quality["data_confidence"] < 0.7
    assert quality["spread_stability_score"] < 0.2


def test_missing_book_drives_low_data_confidence(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    quality = assess_trade_feature_quality(
        {"execution_mode": "SIM", "market_open": True},
        {
            "ltp": 100.0,
            "quote_ok": True,
            "ltp_age_sec": 0.3,
            "quote_age_sec": 0.3,
            "volume": 1000,
        },
    )

    assert quality["data_confidence"] < 0.4
    assert quality["quote_completeness"] in {"LTP_ONLY", "MISSING"}


def test_data_state_and_data_confidence_can_diverge_reasonably(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    stable = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 1000,
            "spread_stability_score": 0.95,
        },
    )
    unstable = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 1000,
            "spread_stability_score": 0.05,
        },
    )

    assert stable["data_state"] == "DATA_OK"
    assert unstable["data_state"] == "DATA_OK"
    assert stable["data_confidence"] > unstable["data_confidence"]


def test_liquidity_quality_has_a_spread_sensitive_gradient_for_quote_valid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    low = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 1_000,
            "oi": 5_000,
            "spread_stability_score": 0.95,
        },
    )
    high = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 250_000,
            "oi": 400_000,
            "spread_stability_score": 0.95,
        },
    )

    assert 0.0 <= low["liquidity_quality"] < high["liquidity_quality"] < 1.0
    assert low["liquidity_flow_score"] < high["liquidity_flow_score"]
    assert low["liquidity_book_score"] == high["liquidity_book_score"] == 1.0


def test_missing_oi_context_lowers_liquidity_for_quote_valid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    rich_oi = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 200_000,
            "oi": 500_000,
            "spread_stability_score": 0.95,
        },
    )
    missing_oi = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.9,
            "ask": 100.1,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 200_000,
            "spread_stability_score": 0.95,
        },
    )

    assert rich_oi["liquidity_quality"] > missing_oi["liquidity_quality"]
    assert rich_oi["liquidity_quality"] - missing_oi["liquidity_quality"] >= 0.08
    assert missing_oi["liquidity_oi_score"] < 0.4


def test_liquidity_quality_penalizes_wider_spread_for_quote_valid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    tight = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.98,
            "ask": 100.02,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 250_000,
            "oi": 400_000,
            "spread_stability_score": 0.95,
        },
    )
    wide = assess_trade_feature_quality(
        {"execution_mode": "LIVE", "market_open": True},
        {
            "ltp": 100.0,
            "bid": 99.0,
            "ask": 101.0,
            "quote_ok": True,
            "ltp_age_sec": 0.2,
            "bid_age_sec": 0.2,
            "ask_age_sec": 0.2,
            "quote_age_sec": 0.2,
            "volume": 250_000,
            "oi": 400_000,
            "spread_stability_score": 0.95,
        },
    )

    assert tight["liquidity_quality"] > wide["liquidity_quality"]
    assert tight["liquidity_spread_score"] > wide["liquidity_spread_score"]
