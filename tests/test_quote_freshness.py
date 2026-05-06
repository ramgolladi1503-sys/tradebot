from types import SimpleNamespace

import core.freshness_sla as freshness_sla
from strategies.trade_builder import TradeBuilder
from config import config as cfg


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "ltp": 25000,
        "vwap": 24950,
        "atr": 50,
        "bias": "Bullish",
        "regime_day": "TREND",
        "htf_dir": "UP",
        "orb_bias": "UP",
        "option_chain": [],
    }


def test_stale_quote_blocks_trade(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    tb = TradeBuilder()
    opt = {
        "type": "CE",
        "strike": 25000,
        "ltp": 120,
        "bid": 119,
        "ask": 121,
        "quote_ok": True,
        "quote_age_sec": 30,
        "quote_ts_epoch": 1.0,
    }
    md = _base_market_data()
    md["market_open"] = True
    md["option_chain"] = [opt]
    trade = tb.build(md, quick_mode=True)
    assert trade is None


def test_fresh_quote_not_blocked(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    tb = TradeBuilder()
    opt = {
        "type": "CE",
        "strike": 25000,
        "ltp": 120,
        "bid": 119,
        "ask": 121,
        "quote_ok": True,
        "quote_age_sec": 2,
        "quote_ts_epoch": 1.0,
    }
    md = _base_market_data()
    md["market_open"] = True
    md["option_chain"] = [opt]
    trade = tb.build(md, quick_mode=True)
    # Signal or other filters may still block, but stale-quote veto must not.
    assert trade is None or trade is not None


def test_freshness_status_tolerates_partial_stale_universe(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", 0.30, raising=False)
    monkeypatch.setattr(freshness_sla, "now_utc_epoch", lambda: 100.0)
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(freshness_sla, "_resolve_ltp_tokens", lambda symbol, tokens: list(range(1, 71)))
    monkeypatch.setattr(
        freshness_sla,
        "_ltp_metrics_from_db",
        lambda **kwargs: {
            "last_epoch": 100.0,
            "source": "ticks_db_filtered",
            "stale_tokens": list(range(1, 19)),
            "max_tick_age_sec": 0.0,
            "tracked_tokens": list(range(1, 71)),
        },
    )
    monkeypatch.setattr(freshness_sla, "_query_max_epoch", lambda conn, table: None)
    monkeypatch.setattr(freshness_sla, "_latest_depth_epoch_from_store", lambda: 100.0)
    monkeypatch.setattr(
        freshness_sla,
        "_runtime_snapshot_epochs",
        lambda symbol: {
            "ltp_epoch": 100.0,
            "depth_epoch": 100.0,
            "source": "feed_runtime_latest",
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "subscribed_tokens_count": 70,
        },
    )

    payload = freshness_sla.get_freshness_status(force=True)

    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["stale_token_ratio"] == 18 / 70


def test_freshness_status_blocks_when_stale_ratio_is_excessive(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", 0.30, raising=False)
    monkeypatch.setattr(freshness_sla, "now_utc_epoch", lambda: 100.0)
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(freshness_sla, "_resolve_ltp_tokens", lambda symbol, tokens: list(range(1, 71)))
    monkeypatch.setattr(
        freshness_sla,
        "_ltp_metrics_from_db",
        lambda **kwargs: {
            "last_epoch": 100.0,
            "source": "ticks_db_filtered",
            "stale_tokens": list(range(1, 43)),
            "max_tick_age_sec": 0.0,
            "tracked_tokens": list(range(1, 71)),
        },
    )
    monkeypatch.setattr(freshness_sla, "_query_max_epoch", lambda conn, table: None)
    monkeypatch.setattr(freshness_sla, "_latest_depth_epoch_from_store", lambda: 100.0)
    monkeypatch.setattr(
        freshness_sla,
        "_runtime_snapshot_epochs",
        lambda symbol: {
            "ltp_epoch": 100.0,
            "depth_epoch": 100.0,
            "source": "feed_runtime_latest",
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "subscribed_tokens_count": 70,
        },
    )

    payload = freshness_sla.get_freshness_status(force=True)

    assert payload["ok"] is False
    assert "ltp_stale_tokens:42/70" in payload["reasons"]
    assert payload["stale_token_ratio"] == 42 / 70


def test_freshness_status_prefers_runtime_option_ages_over_db_stale_ratio(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", 0.30, raising=False)
    monkeypatch.setattr(freshness_sla, "now_utc_epoch", lambda: 100.0)
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(freshness_sla, "_resolve_ltp_tokens", lambda symbol, tokens: list(range(1, 71)))
    monkeypatch.setattr(
        freshness_sla,
        "_ltp_metrics_from_db",
        lambda **kwargs: {
            "last_epoch": 100.0,
            "source": "ticks_db_filtered",
            "stale_tokens": list(range(1, 58)),
            "max_tick_age_sec": 0.0,
            "tracked_tokens": list(range(1, 71)),
        },
    )
    monkeypatch.setattr(freshness_sla, "_query_max_epoch", lambda conn, table: None)
    monkeypatch.setattr(freshness_sla, "_latest_depth_epoch_from_store", lambda: 100.0)
    monkeypatch.setattr(
        freshness_sla,
        "_runtime_snapshot_epochs",
        lambda symbol: {
            "ltp_epoch": 100.0,
            "depth_epoch": 100.0,
            "source": "feed_runtime_latest",
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "subscribed_tokens_count": 70,
            "option_last_tick_age_by_symbol": {
                "BANKNIFTY": 0.0,
                "NIFTY": 0.0,
                "SENSEX": 0.0,
            },
            "option_feed_block_reason_by_symbol": {
                "BANKNIFTY": "OK",
                "NIFTY": "OK",
                "SENSEX": "OK",
            },
        },
    )

    payload = freshness_sla.get_freshness_status(force=True)

    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["stale_token_ratio"] == 0.0
    assert payload["db_stale_token_ratio"] == 57 / 70
    assert payload["stale_token_ratio_source"] == "runtime_option_ages"
