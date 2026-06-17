import json
import pandas as pd
import numpy as np
from typing import Any, Dict, List

class MLLiveInference:
    def __init__(self, model_path: str) -> None:
        import xgboost as xgb
        self.model = xgb.XGBClassifier()
        self.model.load_model(model_path)
        
        with open(model_path, 'r') as f:
            data = json.load(f)
            # Find feature names if stored (often XGBoost stores them in feature_names attribute)
            self.feature_cols = data.get('learner', {}).get('feature_names', [
                "adx", "adx_slope", "macd", "macd_signal", "macd_hist", "rsi", "bb_width", "days_to_expiry"
            ])
            
    def predict(self, live_candles: pd.DataFrame, ticker: str = "NIFTY") -> bool:
        """
        Pass a dataframe of recent 5-min candles (at least 50 rows for indicator warmup).
        Returns True if the ML model approves a LONG trade.
        """
        if len(live_candles) < 30:
            return False # Not enough data for indicators
            
        df = self._calculate_indicators(live_candles.copy(), ticker)
        latest_row = df.iloc[-1:]
        
        # Ensure we have all features
        for col in self.feature_cols:
            if col not in latest_row.columns:
                return False
                
        X = latest_row[self.feature_cols]
        prob = self.model.predict_proba(X)[0][1]
        
        return prob > 0.5
        
    def _calculate_indicators(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        import talib
        from core.expiry_calendar import get_days_to_expiry
        
        # Calculate Expiry Days for the last row's date
        # Assuming the index is a datetime object or 'date' is a column
        if 'date' in df.columns:
            current_date = pd.to_datetime(df['date'].iloc[-1])
        elif isinstance(df.index, pd.DatetimeIndex):
            current_date = df.index[-1]
        else:
            current_date = pd.Timestamp.now()
            
        df['days_to_expiry'] = get_days_to_expiry(current_date, ticker)
        
        df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
        df['adx_slope'] = df['adx'].diff()
        
        macd, macdsignal, macdhist = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['macd'] = macd
        df['macd_signal'] = macdsignal
        df['macd_hist'] = macdhist
        
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)
        
        upper, middle, lower = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df['bb_width'] = (upper - lower) / middle
        
        df = df.dropna()
        return df
