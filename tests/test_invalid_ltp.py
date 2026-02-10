from core.orchestrator import Orchestrator
from strategies.trade_builder import TradeBuilder
import core.market_data as market_data
from config import config as cfg


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


def test_invalid_ltp_snapshot_marked_invalid(monkeypatch):
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(market_data, "is_open", lambda now_dt=None, segment=None: True)
    monkeypatch.setattr(market_data, "get_ltp", lambda symbol: 0)
    monkeypatch.setattr(market_data, "_REGIME_MODEL", object(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    rows = market_data.fetch_live_market_data()
    assert len(rows) == 1
    snap = rows[0]
    assert snap["symbol"] == "NIFTY"
    assert snap["valid"] is False
    assert snap["invalid_reason"] == "invalid_ltp"


def test_orchestrator_invalid_snapshot_skips_trade_building(monkeypatch):
    monkeypatch.setattr(cfg, "INVALID_LTP_ACTION", "skip_symbol", raising=False)
    called = {"count": 0}
    orch = Orchestrator.__new__(Orchestrator)
    orch._build_decision_event = lambda *args, **kwargs: {}
    orch._log_decision_safe = lambda *args, **kwargs: None

    class _DummyBuilder:
        def build(self, *_args, **_kwargs):
            called["count"] += 1
            return None

    orch.trade_builder = _DummyBuilder()
    snapshot = {"symbol": "NIFTY", "valid": False, "invalid_reason": "invalid_ltp", "ltp": 0, "ltp_source": "none"}
    ok, halt_cycle = orch._validate_market_snapshot(snapshot)
    if ok:
        orch.trade_builder.build(snapshot)
    assert ok is False
    assert halt_cycle is False
    assert called["count"] == 0


def test_trade_builder_rejects_invalid_snapshot():
    builder = TradeBuilder()
    trade = builder.build({"symbol": "NIFTY", "valid": False, "invalid_reason": "invalid_ltp"})
    assert trade is None
