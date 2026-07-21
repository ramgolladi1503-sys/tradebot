import pytest
import pandas as pd
from pathlib import Path
from core.option_backtest.adapter import build_candidate_from_candle
from core.option_backtest.models import OptionBacktestConfig, ResearchMode

@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_8_quote_age():
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("."),
        research_mode=ResearchMode.PROXY_RESEARCH,
        max_quote_age_seconds=5.0
    )
    
    timestamp = pd.Timestamp("2024-01-01 09:15:00")
    
    # We pass a quote timestamp that is 10 seconds older than the bar timestamp.
    # The intended contract is that the adapter should compute a quote age of 10.0 seconds.
    row = {
        "timestamp": timestamp,
        "quote_ts": (timestamp - pd.Timedelta(seconds=10)).timestamp(),
        "bid": 100,
        "ask": 102,
        "has_bid_ask": True,
        "close": 101,
        "side": "BUY"
    }
    
    candidate = build_candidate_from_candle(row, config)
    
    # The bug causes quote_age_sec to be exactly 0.0 because it ignores `quote_ts`
    # and hardcodes the snapshot timestamp to be the same as the evaluated_at_epoch.
    quote_age_sec = candidate.get("quote_age_ms", 0) / 1000.0
    
    assert quote_age_sec > 0.0, "Bug confirmed: adapter hardcodes quote age to 0 by ignoring quote_ts"
