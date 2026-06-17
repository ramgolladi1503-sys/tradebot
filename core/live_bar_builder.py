import pandas as pd
from datetime import datetime, timedelta

from typing import Any, Dict, List, Optional

class LiveBarBuilder:
    def __init__(self, interval_minutes: int = 5) -> None:
        self.interval_minutes: int = interval_minutes
        self.current_bar_start: datetime | None = None
        self.current_bar: Dict[str, Any] | None = None
        self.historical_bars: List[Dict[str, Any]] = []
        
    def hydrate_from_broker(self, kite_client: Any, instrument_token: int, days_back: int = 5) -> None:
        """
        PRODUCTION UPGRADE: State Hydration
        Fetches historical candles to instantly warm up the ML indicators on startup.
        """
        if not kite_client:
            print("[Hydration] Skipped: No Kite client provided (Paper Mode fallback)")
            return
            
        print(f"[Hydration] Fetching last {days_back} days of historical 5-minute candles...")
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days_back)
        
        try:
            # interval string in Kite format: "minute", "3minute", "5minute", etc.
            interval_str = f"{self.interval_minutes}minute" if self.interval_minutes > 1 else "minute"
            
            historical_data = kite_client.historical_data(
                instrument_token, 
                start_dt, 
                end_dt, 
                interval=interval_str
            )
            
            if not historical_data:
                print("[Hydration] WARNING: No historical data returned. Bot will run blind until enough live candles form.")
                return
                
            for row in historical_data:
                # row format: {'date': datetime, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': int}
                bar_date = row['date']
                
                # Strip timezone info if necessary, or just store it
                # Convert to match process_tick logic
                self.historical_bars.append({
                    'date': bar_date,
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row.get('volume', 0)
                })
                
            print(f"[Hydration] SUCCESS: Pre-loaded {len(self.historical_bars)} candles. ML Indicators are fully warmed up!")
            
            # Set the current bar start so process_tick doesn't overlap the last historical candle
            if self.historical_bars:
                last_bar_date = self.historical_bars[-1]['date']
                self.current_bar_start = last_bar_date
                
        except Exception as e:
            print(f"[Hydration] CRITICAL API ERROR: {e}. Bot will run blind until live candles form.")
        
    def process_tick(self, tick: Dict[str, Any]) -> None:
        """
        Ingest a tick dictionary containing {'timestamp': datetime, 'last_price': float, 'volume': int}
        Returns a complete 5-min DataFrame if a new bar just finished, otherwise None.
        """
        ts = tick['timestamp']
        price = tick['last_price']
        vol = tick.get('volume', 0)
        
        # Round down to nearest interval
        minute = ts.minute - (ts.minute % self.interval_minutes)
        bar_start = ts.replace(minute=minute, second=0, microsecond=0)
        
        # If this is the first tick ever
        if self.current_bar_start is None:
            self.current_bar_start = bar_start
            self._init_new_bar(bar_start, price, vol)
            return None
            
        # If tick belongs to a NEW bar
        if bar_start > self.current_bar_start:
            # Save the completed bar
            completed_bar = self.current_bar.copy()
            self.historical_bars.append(completed_bar)
            
            # Start the new bar
            self.current_bar_start = bar_start
            self._init_new_bar(bar_start, price, vol)
            
            return self.get_dataframe()
            
        # If tick belongs to CURRENT bar
        self.current_bar['high'] = max(self.current_bar['high'], price)
        self.current_bar['low'] = min(self.current_bar['low'], price)
        self.current_bar['close'] = price
        self.current_bar['volume'] += vol
        
        return None
        
    def _init_new_bar(self, start_time: datetime, price: float, volume: int) -> None:
        self.current_bar = {
            'date': start_time,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'volume': volume
        }
        
    def get_latest_bars(self, n: int = 30) -> List[Dict[str, Any]]:
        return self.historical_bars[-n:]

    def get_dataframe(self) -> pd.DataFrame:
        if not self.historical_bars:
            return pd.DataFrame()
        df = pd.DataFrame(self.historical_bars)
        df.set_index('date', inplace=True)
        return df
