from core.cross_asset import CrossAsset
from config import config as cfg


def test_cross_asset_stale_guard(monkeypatch):
    monkeypatch.setattr(cfg, "CROSS_ASSET_SYMBOLS", {"USDINR_SPOT": "CDS:USDINR"})
    ca = CrossAsset()
    out = ca.update("NIFTY", 25000)
    assert out["data_quality"]["any_stale"] is True
