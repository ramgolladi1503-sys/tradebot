import pandas as pd

def aggregate_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m.empty:
        return pd.DataFrame()
        
    df = df_1m.set_index('timestamp').copy()
    df['open_interest'] = df['open_interest'].replace(0, pd.NA).ffill().fillna(0)
    
    # Ensure timezone is kept correctly
    # resample by 5m, grouped by session date so we don't bridge sessions
    # actually resample directly works if we dropnas later, but session grouping is safer
    
    def agg_group(g):
        res = g.resample('5min', origin='start_day').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'open_interest': 'last'
        })
        res['source_bar_count'] = g['open'].resample('5min', origin='start_day').count()
        return res.dropna(subset=['open'])
        
    agg = df.groupby('session_date').apply(agg_group).reset_index(level=0, drop=True)
    agg['is_complete_5m_bar'] = agg['source_bar_count'] == 5
    
    # Copy metadata from first row of 1m
    meta_cols = [c for c in df_1m.columns if c not in ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'open_interest']]
    meta_vals = df_1m.iloc[0][meta_cols].to_dict()
    for k, v in meta_vals.items():
        if k != 'interval':
            agg[k] = v
    agg['interval'] = '5minute'
    
    return agg.reset_index()\n