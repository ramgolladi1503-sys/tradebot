import hashlib
import json
import pyarrow.parquet as pq
from typing import Dict, Any, Tuple, List, Optional
import pandas as pd
from pathlib import Path

def compute_schema_fingerprint(schema) -> str:
    # Sort schema columns by name to get a deterministic schema fingerprint
    cols = sorted([(name, str(type_val)) for name, type_val in zip(schema.names, schema.types)])
    schema_str = ",".join(f"{n}:{t}" for n, t in cols)
    return hashlib.sha256(schema_str.encode("utf-8")).hexdigest()

def detect_parquet_metadata(filepath: str) -> Dict[str, Any]:
    meta = {
        "row_count": 0,
        "row_group_count": 0,
        "schema_dict": {},
        "schema_fingerprint": "",
        "min_timestamp": None,
        "max_timestamp": None,
        "timezone": "UNKNOWN",
        "instruments": [],
        "data_family": "unknown",
        "error": ""
    }
    try:
        pf = pq.ParquetFile(filepath)
        schema = pf.schema.to_arrow_schema()
        meta["row_count"] = pf.metadata.num_rows
        meta["row_group_count"] = pf.metadata.num_row_groups
        meta["schema_dict"] = {name: str(type_val) for name, type_val in zip(schema.names, schema.types)}
        meta["schema_fingerprint"] = compute_schema_fingerprint(schema)
        
        # Classify data family based on schema columns
        cols = set(schema.names)
        
        # Check columns
        has_ts = "timestamp" in cols or "time" in cols or "exchange_timestamp" in cols
        ts_col = "timestamp" if "timestamp" in cols else ("exchange_timestamp" if "exchange_timestamp" in cols else ("time" if "time" in cols else None))
        
        has_symbol = "symbol" in cols or "tradingsymbol" in cols or "instrument_token" in cols
        sym_col = "symbol" if "symbol" in cols else ("tradingsymbol" if "tradingsymbol" in cols else ("instrument_token" if "instrument_token" in cols else None))

        # Tick data check
        is_tick = ("bid" in cols or "ask" in cols or "bid_price" in cols or "ask_price" in cols or "ltp" in cols)
        
        # Option indicators
        is_option = ("strike" in cols or "option_type" in cols or "expiry" in cols)
        
        if is_tick:
            meta["data_family"] = "ticks"
        elif is_option:
            meta["data_family"] = "option_candles"
        elif "open" in cols and "high" in cols and "low" in cols and "close" in cols:
            meta["data_family"] = "underlying_candles"
        else:
            meta["data_family"] = "unknown"
            
        # Extract min/max timestamps and instruments safely
        if ts_col and pf.metadata.num_rows > 0:
            # Let's project just the ts_col and sym_col to avoid full read
            # Read first and last row group, or just project the whole column if small.
            # Reading the column from parquet doesn't load the whole file.
            projection_cols = [ts_col]
            if sym_col:
                projection_cols.append(sym_col)
                
            table = pf.read(columns=projection_cols)
            df = table.to_pandas()
            
            if not df.empty:
                # Timestamps
                ts_series = pd.to_datetime(df[ts_col])
                meta["min_timestamp"] = ts_series.min().isoformat()
                meta["max_timestamp"] = ts_series.max().isoformat()
                if ts_series.dt.tz is not None:
                    meta["timezone"] = str(ts_series.dt.tz)
                else:
                    meta["timezone"] = "naive"
                
                # Instruments
                if sym_col:
                    meta["instruments"] = sorted(df[sym_col].dropna().unique().tolist())
                    
    except Exception as e:
        meta["error"] = str(e)
        meta["data_family"] = "unknown"
        
    return meta
