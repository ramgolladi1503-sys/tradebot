import pandas as pd
import numpy as np
import os
import glob
from typing import Dict, Tuple

class HTFEngine:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.df_1m = None
        self.df_5m = None
        self.df_15m = None
        self.df_30m = None
        
    def load_and_resample(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        dfs = [pd.read_csv(f) for f in files]
        df = pd.concat(dfs, ignore_index=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        df['date'] = df['timestamp'].dt.date
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['cum_vol_price'] = df.groupby('date').apply(lambda x: (x['typical_price'] * df.loc[x.index, 'volume']).cumsum()).reset_index(level=0, drop=True)
        df['cum_vol'] = df.groupby('date')['volume'].cumsum()
        df['vwap'] = df['cum_vol_price'] / df['cum_vol']
        df['vwap'] = df['vwap'].fillna(df['close'])
        
        df.set_index('timestamp', inplace=True)
        
        def resample_tf(rule: str, shift_mins: int) -> pd.DataFrame:
            resampled = []
            for date, group in df.groupby('date'):
                # resample label='left' means 09:15 is the 09:15-09:30 candle
                agg_df = group.resample(rule, label='left', closed='left').agg({
                    'symbol': 'first',
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum',
                    'vwap': 'last'
                }).dropna()
                agg_df['date'] = date
                resampled.append(agg_df)
            res_df = pd.concat(resampled).reset_index()
            
            # CAUSALITY FIX: The data from the 09:15-09:30 candle is only known exactly AT 09:30.
            # So we shift the timestamp forward by the timeframe duration.
            res_df['timestamp_closed'] = res_df['timestamp'] + pd.Timedelta(minutes=shift_mins)
            
            res_df['tr0'] = abs(res_df['high'] - res_df['low'])
            res_df['tr1'] = abs(res_df['high'] - res_df['close'].shift())
            res_df['tr2'] = abs(res_df['low'] - res_df['close'].shift())
            res_df['tr'] = res_df[['tr0', 'tr1', 'tr2']].max(axis=1)
            res_df['atr'] = res_df['tr'].rolling(14).mean().bfill()
            
            return res_df
            
        df_5m = resample_tf('5min', 5)
        df_15m = resample_tf('15min', 15)
        df_30m = resample_tf('30min', 30)
        
        df_30m['ema9'] = df_30m['close'].rolling(9).mean()
        df_30m['ema21'] = df_30m['close'].rolling(21).mean()
        
        df_15m['ema9'] = df_15m['close'].rolling(9).mean()
        df_15m['ema21'] = df_15m['close'].rolling(21).mean()
        
        daily_vol = df_30m.groupby('date').apply(lambda x: (x['high'].max() - x['low'].min()) / x['open'].iloc[0])
        mean_vol = daily_vol.mean()
        
        conditions_15m = [
            (df_15m['ema9'] > df_15m['ema21']) & (df_15m['close'] > df_15m['ema9']),
            (df_15m['ema9'] < df_15m['ema21']) & (df_15m['close'] < df_15m['ema9'])
        ]
        df_15m['trend_15m'] = np.select(conditions_15m, [1, -1], default=0)
        
        conditions_30m = [
            (df_30m['ema9'] > df_30m['ema21']) & (df_30m['close'] > df_30m['ema9']),
            (df_30m['ema9'] < df_30m['ema21']) & (df_30m['close'] < df_30m['ema9'])
        ]
        df_30m['trend_30m'] = np.select(conditions_30m, [1, -1], default=0)
        
        df_1m = df.reset_index()
        df_1m = df_1m.dropna(subset=['timestamp'])
        
        # Merge on timestamp using the timestamp_closed to ensure no lookahead
        # E.g. at 09:32, the closest backward timestamp_closed is 09:30 (from the 09:15 candle).
        df_1m = pd.merge_asof(
            df_1m.sort_values('timestamp'), 
            df_15m[['timestamp_closed', 'trend_15m']].rename(columns={'timestamp_closed': 'timestamp'}).sort_values('timestamp'), 
            on='timestamp', 
            direction='backward'
        )
        df_1m = pd.merge_asof(
            df_1m.sort_values('timestamp'), 
            df_30m[['timestamp_closed', 'trend_30m']].rename(columns={'timestamp_closed': 'timestamp'}).sort_values('timestamp'), 
            on='timestamp', 
            direction='backward'
        )
        
        df_1m['trend_15m'] = df_1m['trend_15m'].fillna(0)
        df_1m['trend_30m'] = df_1m['trend_30m'].fillna(0)
        
        regimes = []
        for i, row in df_1m.iterrows():
            d = row['date']
            v = daily_vol[d] if d in daily_vol else mean_vol
            t15 = row['trend_15m']
            t30 = row['trend_30m']
            
            if v > mean_vol * 1.5:
                regimes.append('VOL_EXPANSION')
            elif t15 == 1 and t30 == 1:
                regimes.append('TREND_UP')
            elif t15 == -1 and t30 == -1:
                regimes.append('TREND_DOWN')
            elif t15 == 0 and t30 == 0:
                if v < mean_vol * 0.5:
                    regimes.append('CHOP')
                else:
                    regimes.append('RANGE')
            else:
                regimes.append('CHOP')
                
        df_1m['regime'] = regimes
        
        self.df_1m = df_1m
        self.df_5m = df_5m
        self.df_15m = df_15m
        self.df_30m = df_30m
        
        return self.df_1m, self.df_5m, self.df_15m, self.df_30m
