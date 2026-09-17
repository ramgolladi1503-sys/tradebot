#!/usr/bin/env python3
import os
import glob
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

load_dotenv(".env")
TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN")

import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Target date YYYY-MM-DD")
args, _ = parser.parse_known_args()

DATE_STR = args.date
DATE_COMPACT = DATE_STR.replace("-", "")
DATA_DIR = Path(f"/Volumes/TradeBotData/live market capture/{DATE_STR}")
CHUNKS_DIR = DATA_DIR / "chunks"

def stitch_ticks():
    print(f"[*] Discovering tick chunks in {CHUNKS_DIR}...")
    chunk_files = sorted(glob.glob(str(CHUNKS_DIR / "*.parquet")))
    if not chunk_files:
        print("[!] No chunk files found to stitch.")
        return None

    print(f"[*] Reading {len(chunk_files)} chunk files...")
    dfs = []
    for idx, cf in enumerate(chunk_files):
        try:
            df_c = pd.read_parquet(cf)
            dfs.append(df_c)
        except Exception as e:
            print(f"[!] Warning reading chunk {cf}: {e}")

    if not dfs:
        print("[!] No valid DataFrames loaded.")
        return None

    print("[*] Concatenating and sorting ticks...")
    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.sort_values("ts").reset_index(drop=True)

    initial_rows = len(df_all)
    df_all = df_all.drop_duplicates(subset=["ts", "token"]).reset_index(drop=True)
    final_rows = len(df_all)

    out_file = DATA_DIR / f"upstox_full_ticks_{DATE_COMPACT}_stitched.parquet"
    print(f"[*] Writing stitched dataset to {out_file} ({final_rows:,} rows)...")

    table = pa.Table.from_pandas(df_all)
    pq.write_table(table, out_file, compression="snappy")

    file_size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"[✓] Stitched master saved successfully: {file_size_mb:.2f} MB")

    t_start = datetime.fromtimestamp(df_all["ts"].min())
    t_end = datetime.fromtimestamp(df_all["ts"].max())

    summary = {
        "date": DATE_STR,
        "total_chunks": len(chunk_files),
        "total_ticks": final_rows,
        "duplicates_removed": initial_rows - final_rows,
        "start_time": t_start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": t_end.strftime("%Y-%m-%d %H:%M:%S"),
        "unique_tokens": df_all["symbol"].nunique(),
        "file_path": str(out_file),
        "file_size_mb": round(file_size_mb, 2)
    }

    with open(DATA_DIR / f"stitching_summary_{DATE_COMPACT}.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary

def fetch_1m_historical_candles():
    print("\n[*] Fetching complete official 1m historical candles from Upstox API V3...")
    indices = {
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
        "INDIA VIX": "NSE_INDEX|India VIX"
    }

    all_candles = []
    for name, key in indices.items():
        url_key = urllib.parse.quote(key)
        url = f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/1/{DATE_STR}/{DATE_STR}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Api-Version": "3.0",
            "User-Agent": "TradeBot/1.0",
            "Authorization": f"Bearer {TOKEN}"
        })
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                candles = data.get("data", {}).get("candles", [])
                print(f" - {name}: retrieved {len(candles)} 1m candles")
                for c in candles:
                    ts = datetime.fromisoformat(c[0].replace("+05:30", ""))
                    all_candles.append({
                        "timestamp": ts,
                        "symbol": name,
                        "instrument_key": key,
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "oi": float(c[6]) if len(c) > 6 else 0.0
                    })
        except Exception as e:
            print(f" [!] Error fetching {name}: {e}")

    if all_candles:
        df_candles = pd.DataFrame(all_candles).sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        out_candles_file = DATA_DIR / f"indices_1m_{DATE_COMPACT}.parquet"
        table = pa.Table.from_pandas(df_candles)
        pq.write_table(table, out_candles_file, compression="snappy")
        print(f"[✓] Saved official 1m historical candles: {out_candles_file} ({len(df_candles):,} rows)")

if __name__ == "__main__":
    summary = stitch_ticks()
    fetch_1m_historical_candles()
    print("\n=== POST MARKET PIPELINE COMPLETE ===")
    if summary:
        for k, v in summary.items():
            print(f"{k}: {v}")
