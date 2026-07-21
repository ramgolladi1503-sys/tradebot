import pytest
import pandas as pd
from pathlib import Path
from core.option_backtest.engine import OptionBacktestEngine
from core.option_backtest.models import OptionBacktestConfig, ResearchMode

@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_5_signal_time_limit():
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("."),
        quantity=50,
        research_mode=ResearchMode.PROXY_RESEARCH,
        fill_model_run_id="test"
    )
    engine = OptionBacktestEngine(config)
    
    signal_ask = 101.0
    candidate = {
        "side": "BUY",
        "symbol": "NIFTY",
        "execution_entry": signal_ask,
    }
    
    entry_ask = 106.0
    entry_row = pd.Series({
        "timestamp": pd.Timestamp("2024-01-01 09:16:00"),
        "bid": 105.0,
        "ask": entry_ask,
        "bid_qty": 100,
        "ask_qty": 100,
        "volume": 1000,
        "oi": 5000
    })
    
    captured_order = {}
    def mock_simulate(order, snapshot, run_id):
        captured_order.update(order)
        return {"status": "FILLED", "fill_price": order["limit_price"], "slippage_bp": 0.0}
        
    engine.fill_model.simulate = mock_simulate
    engine._simulate_entry(candidate, entry_row, 1)
    
    actual_limit_price_used = captured_order.get("limit_price")
    expected_limit_price = entry_ask
    
    # Intended contract: it MUST use the entry_ask from the current row, NOT the stale signal_ask
    assert actual_limit_price_used == expected_limit_price, "Intended contract: Must evaluate limit price based on current entry bar prices, not stale signal prices"
