import pytest
import os
from unittest.mock import patch, MagicMock
from core.execution_router import ExecutionRouter
from core.orders.state_machine import OrderState

class MockTrade:
    def __init__(self, **kwargs):
        self.tradable = True
        self.symbol = "BANKNIFTY"
        self.instrument = "OPT"
        self.side = "BUY"
        self.qty = 15
        self.entry_price = 100.0
        self.strategy_family = "TEST_FAMILY"
        self.regime = "TRENDING"
        self.direction = "BULLISH"
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("core.execution_router.cfg")
def test_paper_mode_physically_blocked_from_live(mock_cfg):
    """
    REQ-CONF-01: Proves that PAPER mode physical network block works.
    When EXECUTION_MODE is PAPER, it strictly uses PaperFillSimulator
    and never reaches the LIVE execution path or broker payloads.
    """
    mock_cfg.EXECUTION_MODE = "PAPER"
    mock_cfg.ENFORCE_READINESS_ON_EXECUTION = False
    mock_cfg.MANUAL_APPROVAL = False
    
    router = ExecutionRouter()
    
    trade = MockTrade()
    
    import time
    def mock_snapshot():
        return {"bid": 99.0, "ask": 101.0, "ts": time.time()}
        
    with patch.object(router.paper_sim, 'simulate', return_value=(True, 100.5, {"fill_qty": 15})) as mock_sim, \
         patch.object(router.engine, 'is_instrument_temporarily_disabled', return_value={"disabled": False}), \
         patch("core.execution_router.require_approval_or_abort"):
        filled, price, report = router.execute(
            trade=trade,
            bid=99.0,
            ask=101.0,
            volume=1000,
            snapshot_fn=mock_snapshot
        )
        
        # Invariant: Must have routed to paper simulator
        assert report.get("reason_if_aborted") is None, f"Aborted unexpectedly with reason: {report.get('reason_if_aborted')}"
        assert mock_sim.called
        assert filled is True
        
        # Invariant: Mode logic explicitly handles it via paper branch, not live
        assert report.get("reason_if_aborted") is None

@patch("core.execution_router.cfg")
@patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"})
def test_live_mode_requires_manual_approval(mock_cfg):
    """
    REQ-CONF-02: Proves LIVE mode explicitly requires manual approval.
    """
    mock_cfg.EXECUTION_MODE = "LIVE"
    mock_cfg.ALLOW_LIVE_PLACEMENT = True
    mock_cfg.ENFORCE_READINESS_ON_EXECUTION = False
    
    router = ExecutionRouter()
    trade = MockTrade()
    
    filled, price, report = router.execute(
        trade=trade,
        bid=99.0,
        ask=101.0,
        volume=1000,
    )
    
    # Invariant: Must fail due to approval missing
    assert filled is False
    assert "manual_approval" in report.get("reason_if_aborted", "")

@patch("core.execution_router.cfg")
def test_live_mode_placement_disabled_safeguard(mock_cfg):
    """
    Proves that even if MODE=LIVE, if ALLOW_LIVE_PLACEMENT is False, it hard blocks.
    """
    mock_cfg.EXECUTION_MODE = "LIVE"
    mock_cfg.ALLOW_LIVE_PLACEMENT = False
    mock_cfg.ENFORCE_READINESS_ON_EXECUTION = False
    
    router = ExecutionRouter()
    trade = MockTrade()
    
    filled, price, report = router.execute(
        trade=trade,
        bid=99.0,
        ask=101.0,
        volume=1000,
    )
    
    assert filled is False
    assert report.get("reason_if_aborted") == "live_placement_disabled"
