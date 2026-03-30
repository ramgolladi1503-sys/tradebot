from types import SimpleNamespace

from config import config as cfg
from core.kite_client import kite_client
from core.orchestrator import Orchestrator


def test_sync_trades_skips_broker_fetch_in_sim(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "KITE_TRADES_SYNC", True, raising=False)
    monkeypatch.setattr(kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(
        kite_client,
        "trades",
        lambda: (_ for _ in ()).throw(AssertionError("trade sync must not fetch broker trades in SIM")),
        raising=False,
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.last_trade_sync = 0
    orch.open_trades = {}
    orch.trade_meta = {}
    orch.execution_engine = SimpleNamespace(calibrate_slippage=lambda *args, **kwargs: None)

    orch._sync_trades()

    assert orch.last_trade_sync == 0
