import time
from types import SimpleNamespace

from config import config as cfg
import core.execution_router as execution_router


def _trade(trade_id: str = "T-READINESS-GUARD"):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="NIFTY",
        instrument="OPT",
        instrument_id="NIFTY|2026-02-12|25200|CE",
        instrument_token=12345,
        side="BUY",
        entry_price=102.0,
        stop_loss=98.0,
        target=108.0,
        qty=10,
        confidence=0.8,
        tradable=True,
        tradable_reasons_blocking=[],
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        exchange="NFO",
        product="MIS",
    )


def _snapshot():
    return {"bid": 100.0, "ask": 101.0, "ts": time.time(), "depth": {}}


def test_live_readiness_blocks_before_approval(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", True, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", True, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(
        execution_router,
        "run_readiness_check",
        lambda write_log=False: {
            "can_trade": False,
            "state": "BLOCKED",
            "blockers": ["risk_halt_active"],
            "reasons": ["risk_halt_active"],
        },
    )

    router = execution_router.ExecutionRouter()
    filled, price, report = router.execute(_trade(), bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)

    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("readiness_gate_fail:BLOCKED")


def test_live_readiness_passes_then_manual_approval_still_required(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", True, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", True, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setattr(
        execution_router,
        "run_readiness_check",
        lambda write_log=False: {
            "can_trade": True,
            "state": "READY",
            "blockers": [],
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        execution_router,
        "get_freshness_status",
        lambda force=False: {"ok": True, "market_open": True, "reasons": [], "state": "OK"},
    )

    router = execution_router.ExecutionRouter()
    filled, price, report = router.execute(_trade("T-READINESS-READY"), bid=100.0, ask=101.0, volume=1000, snapshot_fn=_snapshot)

    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("manual_approval_required:")
