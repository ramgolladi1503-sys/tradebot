from core.cross_asset import CrossAsset
from config import config as cfg
import core.cross_asset as ca_mod


class _FakeKite:
    def ltp(self, _):
        return {}


def test_cross_asset_stale_guard(monkeypatch):
    monkeypatch.setattr(cfg, "CROSS_ASSET_SYMBOLS", {"USDINR_SPOT": "CDS:USDINR"})
    monkeypatch.setattr(cfg, "CROSS_DISABLED_FEEDS", {})
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    monkeypatch.setattr(cfg, "CROSS_FEED_STATUS", {"USDINR_SPOT": {"status": "required"}})
    monkeypatch.setattr(ca_mod, "kite_client", type("KC", (), {"kite": _FakeKite(), "ltp": _FakeKite().ltp})())
    ca = CrossAsset()
    out = ca.update("NIFTY", 25000)
    assert out["data_quality"]["any_stale"] is True


def test_cross_asset_last_ts_age(monkeypatch):
    class _GoodKite:
        def ltp(self, _):
            return {"CDS:USDINR": {"last_price": 83.0}}

    monkeypatch.setattr(cfg, "CROSS_ASSET_SYMBOLS", {"USDINR_SPOT": "CDS:USDINR"})
    monkeypatch.setattr(cfg, "CROSS_DISABLED_FEEDS", {})
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    monkeypatch.setattr(cfg, "CROSS_FEED_STATUS", {"USDINR_SPOT": {"status": "required"}})
    monkeypatch.setattr(ca_mod, "kite_client", type("KC", (), {"kite": _GoodKite(), "ltp": _GoodKite().ltp})())
    ca = CrossAsset()
    out = ca.update("NIFTY", 25000)
    dq = out["data_quality"]
    assert dq["last_ts"].get("USDINR_SPOT") is not None
    assert dq["age_sec"].get("USDINR_SPOT") is not None
    assert dq["age_sec"]["USDINR_SPOT"] >= 0.0


def test_cross_asset_fetch_error_marks_disabled(monkeypatch):
    class _BadKite:
        def ltp(self, _):
            raise RuntimeError("ltp_failed")

    monkeypatch.setattr(cfg, "CROSS_ASSET_SYMBOLS", {"USDINR_SPOT": "CDS:USDINR"})
    monkeypatch.setattr(cfg, "CROSS_DISABLED_FEEDS", {})
    monkeypatch.setattr(cfg, "CROSS_REQUIRED_FEEDS", ["USDINR_SPOT"])
    monkeypatch.setattr(cfg, "CROSS_OPTIONAL_FEEDS", [])
    monkeypatch.setattr(cfg, "CROSS_FEED_STATUS", {"USDINR_SPOT": {"status": "required"}})
    monkeypatch.setattr(ca_mod, "kite_client", type("KC", (), {"kite": _BadKite(), "ltp": _BadKite().ltp})())
    ca = CrossAsset()
    out = ca.update("NIFTY", 25000)
    dq = out["data_quality"]
    assert dq["disabled"] is True
    assert dq["disabled_reason"] == "fetch_error"
    assert dq["missing"].get("USDINR_SPOT") is not None
