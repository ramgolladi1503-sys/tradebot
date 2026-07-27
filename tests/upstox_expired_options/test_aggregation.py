import pandas as pd
from zoneinfo import ZoneInfo
from datetime import datetime
from research.upstox_expired_options.aggregation import aggregate_5m

KOLKATA = ZoneInfo("Asia/Kolkata")

def test_aggregate_5m():
    # 3 bars in first 5 min, 1 bar in next
    dt1 = datetime(2026, 7, 7, 9, 15, tzinfo=KOLKATA)
    dt2 = datetime(2026, 7, 7, 9, 16, tzinfo=KOLKATA)
    dt3 = datetime(2026, 7, 7, 9, 17, tzinfo=KOLKATA)
    dt4 = datetime(2026, 7, 7, 9, 21, tzinfo=KOLKATA)
    
    df = pd.DataFrame([
        {'timestamp': dt1, 'session_date': '2026-07-07', 'open': 10, 'high': 15, 'low': 9, 'close': 14, 'volume': 100, 'open_interest': 50},
        {'timestamp': dt2, 'session_date': '2026-07-07', 'open': 14, 'high': 16, 'low': 13, 'close': 16, 'volume': 150, 'open_interest': 60},
        {'timestamp': dt3, 'session_date': '2026-07-07', 'open': 16, 'high': 20, 'low': 15, 'close': 19, 'volume': 200, 'open_interest': 70},
        {'timestamp': dt4, 'session_date': '2026-07-07', 'open': 19, 'high': 21, 'low': 18, 'close': 20, 'volume': 300, 'open_interest': 80}
    ])
    df['interval'] = '1minute'
    
    agg = aggregate_5m(df)
    assert agg.shape[0] == 2
    assert agg.iloc[0]['open'] == 10
    assert agg.iloc[0]['high'] == 20
    assert agg.iloc[0]['low'] == 9
    assert agg.iloc[0]['close'] == 19
    assert agg.iloc[0]['volume'] == 450
    assert agg.iloc[0]['source_bar_count'] == 3
    assert not agg.iloc[0]['is_complete_5m_bar']
    
    assert agg.iloc[1]['open'] == 19
    assert agg.iloc[1]['source_bar_count'] == 1
