from datetime import datetime
from zoneinfo import ZoneInfo

from config import config as cfg
import core.market_data as market_data


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.8, "RANGE": 0.2},
            "regime_entropy": 0.2,
            "unstable_regime_flag": False,
        }


def test_fetch_live_market_data_uses_session_minutes(monkeypatch):
    fixed_now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())

    def _fake_get_ltp(symbol: str):
        market_data._DATA_CACHE.setdefault(symbol, {})
        market_data._DATA_CACHE[symbol]["ltp_source"] = "live"
        market_data._DATA_CACHE[symbol]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT")

    assert snap["valid"] is True
    assert snap["minutes_since_open"] == 165
    assert snap["orb_bias"] != "PENDING"
