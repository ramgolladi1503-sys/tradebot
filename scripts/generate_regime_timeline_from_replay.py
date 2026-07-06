import sys
import json
import pandas as pd
from pathlib import Path
from core.market_context import derive_market_context

def aggregate_tick_jsonl(filepath):
    """
    Reads a tick jsonl file, extracts ts/ltp/bid, aggregates into 1min OHLC.
    """
    records = []
    with open(filepath, 'r') as f:
        for line in f:
            if not line.strip(): continue
            try:
                row = json.loads(line)
                ts = row.get("ts") or row.get("timestamp") or row.get("time")
                if not ts: continue
                # We want a price field
                price = row.get("ltp") or row.get("last_price") or row.get("tick") or row.get("bid") or row.get("close")
                if price is None: continue
                records.append({"ts": ts, "price": float(price)})
            except:
                pass
                
    if not records:
        return None
        
    df = pd.DataFrame(records)
    df['ts'] = pd.to_datetime(df['ts'])
    df = df.set_index('ts')
    ohlc = df['price'].resample('1min').ohlc()
    # Drop rows where all are NaN (no forward fill)
    ohlc = ohlc.dropna(how='all')
    ohlc = ohlc.reset_index()
    # rename columns to standard
    ohlc.rename(columns={"ts": "timestamp"}, inplace=True)
    return ohlc

def load_ohlc_csv(filepath):
    try:
        if filepath.endswith('.parquet'):
            df = pd.read_parquet(filepath)
        else:
            df = pd.read_csv(filepath, encoding='utf-8', encoding_errors='replace')
    except Exception:
        return None
    # Validate required fields
    cols = set(df.columns)
    if not {"open", "high", "low", "close"}.issubset(cols):
        return None
    if "timestamp" not in cols and "datetime" not in cols and "date" not in cols and "ts" not in cols:
        return None
    
    # Rename time column to timestamp if needed
    for tc in ["datetime", "date", "ts"]:
        if tc in cols and "timestamp" not in cols:
            df.rename(columns={tc: "timestamp"}, inplace=True)
            break
            
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def select_auto_source(date_str):
    inv_path = Path("runtime/strategy_validation/regime_audit_data_inventory.json")
    if not inv_path.exists():
        return None, None
        
    with open(inv_path, 'r') as f:
        inv = json.load(f)
        
    inventory = inv.get("inventory", [])
    
    # 1. 2026-07-06 if tick_jsonl can produce OHLC
    # Actually just search for the best file for the given date
    best_source = None
    best_path = None
    
    # Priority:
    # 1. USABLE_OHLC (csv/parquet)
    # 2. USABLE_TICK_LTP (jsonl)
    
    for item in inventory:
        if date_str in item.get("dates", []):
            if item["classification"] == "USABLE_OHLC":
                return "ohlc_csv", item["path"]
                
    for item in inventory:
        if date_str in item.get("dates", []):
            if item["classification"] == "USABLE_TICK_LTP":
                if item["path"].endswith(".jsonl"):
                    return "tick_jsonl", item["path"]
                    
    # Also fallback to checking truth_dataset
    truth_path = Path(".runtime/truth_dataset.parquet")
    if truth_path.exists():
        try:
            df = pd.read_parquet(truth_path)
            if "ts" in df.columns:
                if date_str in pd.to_datetime(df["ts"]).dt.strftime('%Y-%m-%d').unique():
                    return "truth_dataset", str(truth_path)
        except:
            pass
            
    return None, None

def write_report(date_str, source, input_path, ohlc_df, verdict, tradebot_generated):
    report_path = Path("runtime/strategy_validation/regime_source_adapter_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    num_bars = len(ohlc_df) if ohlc_df is not None else 0
    cols_used = list(ohlc_df.columns) if ohlc_df is not None else []
    
    md = f"# Regime Source Adapter Report\n\n"
    md += f"**Date**: {date_str}\n"
    md += f"**Source Selected**: {source}\n"
    md += f"**Input Path**: {input_path}\n"
    md += f"**Why Selected**: Matches requested date and source priority rules.\n"
    md += f"**Columns Used**: {cols_used}\n"
    md += f"**Number of OHLC bars**: {num_bars}\n"
    md += f"**TradeBot Regime Timeline Generated**: {tradebot_generated}\n"
    md += f"**Independent Reference Regime Generated**: {num_bars > 0}\n"
    md += f"**Final Verdict**: {verdict}\n"
    
    with open(report_path, "w") as f:
        f.write(md)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--source", default="truth_dataset", choices=["auto", "truth_dataset", "ohlc_csv", "tick_jsonl"])
    parser.add_argument("--input-path", default=None)
    args = parser.parse_args()

    date_str = args.date
    source = args.source
    input_path = args.input_path
    
    if source == "auto":
        source, input_path = select_auto_source(date_str)
        if not source:
            print(f"No usable source found for {date_str}.")
            write_report(date_str, "None", "None", None, "NO_USABLE_REPLAY_DATA", False)
            return

    if source == "truth_dataset":
        if not input_path: input_path = ".runtime/truth_dataset.parquet"
        path = Path(input_path)
        if not path.exists():
            print(f"truth_dataset {path} missing")
            write_report(date_str, source, input_path, None, "NO_USABLE_REPLAY_DATA", False)
            return
            
        df = pd.read_parquet(path)
        if "ts" in df.columns:
            df['ts_datetime'] = pd.to_datetime(df['ts'])
            df = df[df['ts_datetime'].dt.strftime('%Y-%m-%d') == date_str]
            
        if len(df) == 0:
            print(f"No rows for {date_str} in {path}")
            write_report(date_str, source, input_path, None, "NO_USABLE_REPLAY_DATA", False)
            return
            
        # Ensure OHLC
        if not {"open", "high", "low", "close"}.issubset(df.columns):
            print("truth_dataset missing OHLC columns")
            write_report(date_str, source, input_path, None, "INCOMPLETE_REFERENCE", False)
            return
            
        ohlc_df = df
        
    elif source == "tick_jsonl":
        if not input_path:
            print("input-path required for tick_jsonl")
            return
            
        ohlc_df = aggregate_tick_jsonl(input_path)
        if ohlc_df is None:
            print("Failed to aggregate tick jsonl or missing required fields")
            write_report(date_str, source, input_path, None, "INSUFFICIENT_SCHEMA", False)
            return
            
    elif source == "ohlc_csv":
        if not input_path:
            print("input-path required for ohlc_csv")
            return
            
        ohlc_df = load_ohlc_csv(input_path)
        if ohlc_df is None:
            print("Failed to load ohlc csv or missing required fields")
            write_report(date_str, source, input_path, None, "INSUFFICIENT_SCHEMA", False)
            return
            
    else:
        print("Unknown source")
        return
        
    # Save the standardized OHLC for the audit script
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    ohlc_df.to_parquet(out_dir / f"reference_ohlc_{date_str}.parquet")
    
    # Generate TradeBot regime timeline by simulating snapshots
    count = 0
    for idx, row in ohlc_df.iterrows():
        price = row.get("close")
        if pd.isna(price): continue
        snapshot = {
            "symbol": "NIFTY",
            "segment": "NSE_FNO",
            "ltp": float(price),
            "market_open": True,
            "primary_regime": None,
            "regime_confidence": 0.5,
            "adx": None,
            "atr": None,
            "vwap": float(price),
            "vwap_slope": 0.0,
            "realized_vol": 0.0,
            "entropy": None,
            "market_context_id": f"replay_{idx}",
            "execution_mode": "SIM",
            "market_timestamp": str(row.get("timestamp")),
            "open": float(row.get("open", price)),
            "high": float(row.get("high", price)),
            "low": float(row.get("low", price)),
            "close": float(row.get("close", price)),
            "source_file": input_path
        }
        derive_market_context(snapshot)
        count += 1
        
    print(f"Generated {count} regime timeline entries from {source}.")
    verdict = "DATA_FOUND_REGIME_READY" if count > 0 else "NO_USABLE_REPLAY_DATA"
    write_report(date_str, source, input_path, ohlc_df, verdict, count > 0)

if __name__ == "__main__":
    main()
