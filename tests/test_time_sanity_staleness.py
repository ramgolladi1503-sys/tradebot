from datetime import timedelta

from zoneinfo import ZoneInfo

import core.market_data as market_data
from config import config as cfg
from core.time_utils import now_ist
from strategies.trade_builder import TradeBuilder


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "regime_probs": {"TREND": 0.6, "RANGE": 0.2, "EVENT": 0.2},
            "primary_regime": "TREND",
            "regime_entropy": 0.4,
            "unstable_regime_flag": False,
        }


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


def _patch_common(monkeypatch, *, now_epoch: float, ltp_ts_epoch: float, last_ts):
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "MAX_LTP_AGE_SEC", 8.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_CANDLE_AGE_SEC", 120.0, raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_API", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    fixed_now = now_ist().replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: now_epoch)
    monkeypatch.setattr(market_data, "is_open", lambda now_dt=None, segment=None: True)
    monkeypatch.setattr(market_data, "get_ltp", lambda symbol: 25000.0)

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data.ohlc_buffer, "get_bars", lambda symbol: [{"close": 25000.0}] * 40)
    monkeypatch.setattr(
        market_data,
        "compute_indicators",
        lambda bars, **kwargs: {
            "vwap": 25000.0,
            "atr": 50.0,
            "adx": 25.0,
            "vol_z": 0.2,
            "vwap_slope": 0.1,
            "last_ts": last_ts,
            "ok": True,
        },
    )
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda symbol, ltp, force_synthetic=False: [])
    market_data._DATA_CACHE["NIFTY"] = {"ltp_source": "live", "ltp_ts_epoch": ltp_ts_epoch}


def test_stale_ltp_marks_snapshot_invalid(monkeypatch):
    reference_now = now_ist()
    _patch_common(
        monkeypatch,
        now_epoch=200.0,
        ltp_ts_epoch=100.0,
        last_ts=reference_now,
    )
    rows = market_data.fetch_live_market_data()
    assert len(rows) == 1
    snap = rows[0]
    assert snap["valid"] is False
    assert "LTP_STALE" in str(snap.get("invalid_reason"))
    assert snap.get("feed_health", {}).get("time_sanity", {}).get("ok") is False


def test_fresh_timestamps_do_not_block(monkeypatch):
    reference_now = now_ist()
    _patch_common(
        monkeypatch,
        now_epoch=200.0,
        ltp_ts_epoch=199.0,
        last_ts=reference_now - timedelta(seconds=30),
    )
    rows = market_data.fetch_live_market_data()
    assert len(rows) >= 1
    snap = next(row for row in rows if row.get("instrument") == "OPT")
    assert snap["valid"] is True
    assert snap["invalid_reason"] is None
    assert snap.get("time_sanity", {}).get("ok") is True


def test_trade_builder_blocks_stale_snapshot_reason():
    builder = TradeBuilder()
    trade = builder.build({"symbol": "NIFTY", "valid": False, "invalid_reason": "LTP_STALE"})
    assert trade is None
    assert builder._reject_ctx.get("reason") == "LTP_STALE"
