#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime, timedelta

# Add parent directory to path so we can import core modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.kite_client import kite_client
from config import config as cfg

def main():
    print("Initializing Kite Client...")
    # This will load credentials from .env and authenticate
    # Ensure client is authenticated
    kite_client.ensure()
    
    # 1. Fetch Instruments to map Symbols -> Instrument Tokens
    print("Fetching instruments from Kite...")
    instruments = kite_client.instruments_cached(exchange="NSE")
    
    symbol_to_token = {}
    for inst in instruments:
        tradingsymbol = inst.get("tradingsymbol")
        # Kite usually uses NIFTY 50 and NIFTY BANK for spot indices
        if tradingsymbol in ["NIFTY 50", "NIFTY BANK"]:
            symbol_to_token[tradingsymbol] = inst.get("instrument_token")
            
    if "NIFTY 50" not in symbol_to_token or "NIFTY BANK" not in symbol_to_token:
        print("ERROR: Could not find instrument tokens for NIFTY 50 or NIFTY BANK.")
        print("Found tokens:", symbol_to_token)
        sys.exit(1)
        
    print(f"Resolved Tokens: NIFTY 50 -> {symbol_to_token['NIFTY 50']}, NIFTY BANK -> {symbol_to_token['NIFTY BANK']}")
    
    # 2. Fetch Historical Data
    to_date = datetime.now()
    # Fetch last 5 days
    from_date = to_date - timedelta(days=5)
    
    print(f"Fetching 1-minute historical data from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}...")
    
    try:
        nifty_history = kite_client.historical(
            instrument_token=symbol_to_token['NIFTY 50'],
            from_date=from_date,
            to_date=to_date,
            interval="minute",
            _symbol="NSE:NIFTY 50",
            _caller="fetch_historical_pairs"
        )
        
        banknifty_history = kite_client.historical(
            instrument_token=symbol_to_token['NIFTY BANK'],
            from_date=from_date,
            to_date=to_date,
            interval="minute",
            _symbol="NSE:NIFTY BANK",
            _caller="fetch_historical_pairs"
        )
    except Exception as e:
        print(f"ERROR: Failed to fetch historical data. Make sure you have the historical data add-on. Error: {e}")
        sys.exit(1)
        
    print(f"Fetched {len(nifty_history)} candles for NIFTY.")
    print(f"Fetched {len(banknifty_history)} candles for BANKNIFTY.")
    
    # 3. Merge data by timestamp
    merged_data = []
    
    # Convert lists to dicts keyed by isoformat string for easy joining
    nifty_map = {}
    for candle in nifty_history:
        # candle['date'] is a datetime object in kiteconnect
        dt_str = candle['date'].isoformat() if hasattr(candle['date'], 'isoformat') else str(candle['date'])
        nifty_map[dt_str] = candle['close']
        
    banknifty_map = {}
    for candle in banknifty_history:
        dt_str = candle['date'].isoformat() if hasattr(candle['date'], 'isoformat') else str(candle['date'])
        banknifty_map[dt_str] = candle['close']
        
    # Get common timestamps, sort chronologically
    common_ts = sorted(list(set(nifty_map.keys()).intersection(set(banknifty_map.keys()))))
    
    for ts in common_ts:
        merged_data.append({
            "timestamp": ts,
            "NIFTY_INDEX": nifty_map[ts],
            "BANKNIFTY_INDEX": banknifty_map[ts]
        })
        
    print(f"Successfully merged {len(merged_data)} synchronous ticks.")
    
    # 4. Save to disk
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'data'), exist_ok=True)
    out_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'pairs_historical.json')
    
    with open(out_path, 'w') as f:
        json.dump(merged_data, f, indent=2)
        
    print(f"Data saved to {out_path}")

if __name__ == "__main__":
    main()
