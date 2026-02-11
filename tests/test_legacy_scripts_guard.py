from types import SimpleNamespace

from config import config as cfg
from tools.flatten_positions import _flatten


def test_flatten_positions_blocked_when_live_env_disabled(monkeypatch, tmp_path):
    class _FakeKite:
        VARIETY_REGULAR = "regular"
        ORDER_TYPE_MARKET = "market"
        PRODUCT_MIS = "mis"
        VALIDITY_DAY = "day"
        calls = 0

        def place_order(self, **kwargs):
            self.calls += 1
            return "OID"

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    fake = _FakeKite()
    monkeypatch.setattr("tools.flatten_positions.kite_client", SimpleNamespace(kite=fake))

    _flatten(
        [{"tradingsymbol": "NIFTY26FEBFUT", "exchange": "NFO", "quantity": 10}],
        dry_run=False,
    )
    assert fake.calls == 0
