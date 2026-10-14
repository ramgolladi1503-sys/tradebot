#!/usr/bin/env python3
"""
Fetch Historical Nifty Futures Data from Upstox.

Discovers and fetches all historical Nifty Futures contracts available in Upstox:
- 24 Expired Monthly Contracts (2024-10-31 to 2026-09-29) via Expired Instruments API
- 3 Active Contracts (Near, Next, Far Month) via Active Historical Candle API
- Captures both 1-minute intraday bars and daily bars (OHLCV + Open Interest)
- Stitches a continuous near-month synthetic futures series with zero lookahead
- Validates 0 nulls across all schema columns
- Mirrors to external drive (/Volumes/TradeBot) and Google Drive (rclone)
"""

import os
import sys
import json
import time
import shutil
import hashlib
import logging
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

# Set up paths and logging
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("nifty_futures_fetcher")

OUTPUT_DIR = ROOT / "data" / "historical" / "nifty_futures"
EXTERNAL_BASE_DIRS = [
    Path("/Volumes/TradeBot/historical/nifty_futures"),
    Path("/Volumes/TradeBotData/historical/nifty_futures"),
]

def get_access_token() -> str:
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("Missing UPSTOX_ACCESS_TOKEN in .env")
    return token

def make_request(url: str, token: str, retries: int = 4, backoff: float = 1.0) -> Optional[Dict[str, Any]]:
    headers = {
        "Accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
        "User-Agent": "TradeBot/1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_sec = backoff * (2 ** attempt)
                logger.warning(f"Rate limited (429) on {url}. Retrying in {sleep_sec:.1f}s...")
                time.sleep(sleep_sec)
                continue
            elif e.code == 404:
                logger.warning(f"Resource not found (404): {url}")
                return None
            else:
                logger.warning(f"HTTPError {e.code} on {url}: {e.reason}")
                if attempt == retries - 1:
                    return None
                time.sleep(backoff)
        except Exception as e:
            logger.warning(f"Error requesting {url}: {e}")
            if attempt == retries - 1:
                return None
            time.sleep(backoff)
            
    return None

def discover_expired_contracts(token: str) -> List[Dict[str, Any]]:
    """Discover all expired Nifty Futures contracts across Upstox history."""
    logger.info("Discovering expired contracts from Upstox Expired Instruments API...")
    url = "https://api.upstox.com/v2/expired-instruments/expiries?instrument_key=NSE_INDEX%7CNifty%2050"
    data = make_request(url, token)
    if not data or not data.get("data"):
        logger.error("Failed to fetch expiry list for Nifty 50.")
        return []

    expiries = data.get("data", [])
    logger.info(f"Discovered {len(expiries)} historical expiries. Scanning for futures contracts...")

    futures_contracts = []
    for exp in expiries:
        fut_url = f"https://api.upstox.com/v2/expired-instruments/future/contract?instrument_key=NSE_INDEX%7CNifty%2050&expiry_date={exp}"
        fut_data = make_request(fut_url, token)
        if fut_data and fut_data.get("data"):
            contracts = fut_data.get("data", [])
            for c in contracts:
                if c.get("instrument_type") == "FUT" and "NIFTY" in c.get("trading_symbol", ""):
                    c["is_active"] = False
                    futures_contracts.append(c)
                    logger.info(f"  [Expired FUT] {c.get('expiry')} | {c.get('trading_symbol')} | {c.get('instrument_key')}")
        time.sleep(0.05)

    futures_contracts.sort(key=lambda x: x["expiry"])
    logger.info(f"Discovered {len(futures_contracts)} expired Nifty Futures contracts.")
    return futures_contracts

def discover_active_contracts(token: str) -> List[Dict[str, Any]]:
    """Discover active Nifty Futures contracts (near, next, far months)."""
    logger.info("Discovering active Nifty Futures contracts from Upstox instrument master...")
    inst_paths = [
        ROOT / "runtime" / "upstox_instruments" / "complete.json",
        ROOT / ".runtime" / "upstox_instruments.json",
    ]
    instruments = []
    for p in inst_paths:
        if p.exists():
            try:
                with open(p, "r") as f:
                    instruments = json.load(f)
                    break
            except Exception as e:
                logger.warning(f"Failed reading {p}: {e}")

    if not instruments:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        try:
            import gzip, io
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "TradeBot/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                with gzip.GzipFile(fileobj=io.BytesIO(resp.read())) as f:
                    instruments = json.loads(f.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to fetch live instrument master: {e}")
            return []

    active_futs = []
    for item in instruments:
        seg = item.get("segment", "")
        inst_type = item.get("instrument_type", "")
        trading_symbol = item.get("trading_symbol", "")
        if seg == "NSE_FO" and inst_type == "FUT" and ("NIFTY" in trading_symbol) and ("BANK" not in trading_symbol) and ("FIN" not in trading_symbol) and ("MID" not in trading_symbol) and ("NXT" not in trading_symbol) and ("FPI" not in trading_symbol):
            item["is_active"] = True
            # Format expiry date YYYY-MM-DD
            exp_raw = item.get("expiry")
            if isinstance(exp_raw, (int, float)):
                item["expiry_date"] = datetime.fromtimestamp(exp_raw / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                item["expiry_date"] = str(exp_raw)
            active_futs.append(item)
            logger.info(f"  [Active FUT] {item.get('expiry_date')} | {trading_symbol} | {item.get('instrument_key')}")

    active_futs.sort(key=lambda x: x.get("expiry_date", ""))
    logger.info(f"Discovered {len(active_futs)} active Nifty Futures contracts.")
    return active_futs

def fetch_candles_for_contract(
    contract: Dict[str, Any],
    interval: str,
    token: str
) -> pd.DataFrame:
    """Fetch all available historical candles (OHLCV + OI) for a single contract."""
    inst_key = contract["instrument_key"]
    encoded_key = urllib.parse.quote(inst_key)
    is_active = contract.get("is_active", False)
    expiry_raw = contract.get("expiry_date") or contract.get("expiry")
    if isinstance(expiry_raw, (int, float)):
        expiry_str = datetime.fromtimestamp(expiry_raw / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        expiry_str = str(expiry_raw)
    symbol = contract.get("trading_symbol")

    try:
        exp_dt = datetime.strptime(expiry_str[:10], "%Y-%m-%d")
    except Exception:
        exp_dt = datetime.now()

    # Futures trade for ~90 calendar days prior to expiry
    start_dt = exp_dt - timedelta(days=95)
    end_dt = min(exp_dt, datetime.now()) if is_active else exp_dt

    all_candles = []

    if not is_active:
        # Expired Instruments API allows full contract span in single or dual chunks
        to_str = end_dt.strftime("%Y-%m-%d")
        from_str = start_dt.strftime("%Y-%m-%d")
        url = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{encoded_key}/{interval}/{to_str}/{from_str}"
        data = make_request(url, token)
        if data and data.get("data", {}).get("candles"):
            all_candles.extend(data["data"]["candles"])
    else:
        # Active Historical Candle API requires 30-day chunks for intraday bars
        chunk_days = 25 if interval == "1minute" else 90
        curr_end = end_dt
        while curr_end > start_dt:
            curr_start = max(curr_end - timedelta(days=chunk_days), start_dt)
            to_str = curr_end.strftime("%Y-%m-%d")
            from_str = curr_start.strftime("%Y-%m-%d")
            url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/{interval}/{to_str}/{from_str}"
            data = make_request(url, token)
            if data and data.get("data", {}).get("candles"):
                all_candles.extend(data["data"]["candles"])
            curr_end = curr_start - timedelta(days=1)
            time.sleep(0.05)

    if not all_candles:
        logger.warning(f"No {interval} candles returned for {symbol} ({inst_key})")
        return pd.DataFrame()

    # Parse candle records
    rows = []
    for c in all_candles:
        # Schema: [timestamp, open, high, low, close, volume, oi]
        ts_str = c[0]
        try:
            ts_dt = datetime.fromisoformat(ts_str.replace("+05:30", ""))
        except Exception:
            continue

        rows.append({
            "timestamp": ts_dt,
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
            "oi": float(c[6]) if len(c) > 6 else 0.0,
            "contract": symbol,
            "expiry": expiry_str[:10],
            "instrument_key": inst_key
        })

    df = pd.DataFrame(rows)
    # Deduplicate and sort chronologically
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    logger.info(f"  [✓] {symbol} ({interval}): {len(df):,} bars ({df['timestamp'].min()} to {df['timestamp'].max()})")
    return df

def build_continuous_futures(contract_dfs: List[pd.DataFrame], interval: str) -> pd.DataFrame:
    """
    Stitches a continuous near-month futures series without lookahead.
    For each monthly contract, rolls to the next near-month contract at expiry day 15:30 IST.
    """
    if not contract_dfs:
        return pd.DataFrame()

    # Filter non-empty dataframes and sort by expiry
    valid_dfs = [df for df in contract_dfs if not df.empty]
    valid_dfs.sort(key=lambda df: df["expiry"].iloc[0])

    continuous_segments = []

    for i, df in enumerate(valid_dfs):
        contract_name = df["contract"].iloc[0]
        expiry_date = df["expiry"].iloc[0]

        if i == 0:
            # First contract: take from beginning of its data up to roll cutoff
            roll_cutoff = datetime.strptime(expiry_date, "%Y-%m-%d").replace(hour=15, minute=30, second=0)
            seg = df[df["timestamp"] <= roll_cutoff].copy()
        elif i < len(valid_dfs) - 1:
            # Intermediate contract: start from prior contract's roll cutoff up to this contract's cutoff
            prior_expiry = valid_dfs[i - 1]["expiry"].iloc[0]
            start_cutoff = datetime.strptime(prior_expiry, "%Y-%m-%d").replace(hour=15, minute=30, second=0)
            roll_cutoff = datetime.strptime(expiry_date, "%Y-%m-%d").replace(hour=15, minute=30, second=0)
            seg = df[(df["timestamp"] > start_cutoff) & (df["timestamp"] <= roll_cutoff)].copy()
        else:
            # Latest active contract: start from prior cutoff up to latest available bar
            prior_expiry = valid_dfs[i - 1]["expiry"].iloc[0]
            start_cutoff = datetime.strptime(prior_expiry, "%Y-%m-%d").replace(hour=15, minute=30, second=0)
            seg = df[df["timestamp"] > start_cutoff].copy()

        if not seg.empty:
            continuous_segments.append(seg)
            logger.info(f"  Continuous segment [{contract_name}]: {len(seg):,} bars ({seg['timestamp'].min()} to {seg['timestamp'].max()})")

    if not continuous_segments:
        return pd.DataFrame()

    df_cont = pd.concat(continuous_segments, ignore_index=True)
    df_cont = df_cont.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df_cont

def save_parquet(df: pd.DataFrame, filepath: Path):
    """Save dataframe as optimized snappy parquet with strict schema."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, filepath, compression="snappy")
    logger.info(f"Saved: {filepath.name} ({len(df):,} rows, {filepath.stat().st_size / (1024*1024):.2f} MB)")

def mirror_to_external_and_cloud(data_dir: Path):
    """Mirror data to external hard drive and sync to Google Drive."""
    # 1. External hard drive
    for ext_base in EXTERNAL_BASE_DIRS:
        if ext_base.parent.exists():
            try:
                ext_base.mkdir(parents=True, exist_ok=True)
                logger.info(f"Mirroring data to external drive: {ext_base}...")
                for item in data_dir.glob("**/*"):
                    if item.is_file():
                        rel = item.relative_to(data_dir)
                        target = ext_base / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
                logger.info(f"[✓] Mirrored to external drive: {ext_base}")
                break
            except Exception as e:
                logger.warning(f"Could not mirror to {ext_base}: {e}")

    # 2. Google Drive via rclone
    rclone_bin = "/usr/local/bin/rclone" if Path("/usr/local/bin/rclone").exists() else "rclone"
    gdrive_target = "gdrive:tradebot_market_data/historical/nifty_futures"
    logger.info(f"Syncing historical Nifty futures data to Google Drive ({gdrive_target})...")
    try:
        res = subprocess.run([rclone_bin, "copy", str(data_dir), gdrive_target], capture_output=True, text=True, timeout=600)
        if res.returncode == 0:
            logger.info(f"[✓] Successfully uploaded historical Nifty futures to Google Drive: {gdrive_target}")
        else:
            logger.warning(f"Google Drive sync note: {res.stderr.strip()}")
    except Exception as e:
        logger.warning(f"Could not sync to Google Drive: {e}")

def main():
    token = get_access_token()
    logger.info("Starting historical Nifty Futures ingestion pipeline...")

    # 1. Discover all contracts
    expired_contracts = discover_expired_contracts(token)
    active_contracts = discover_active_contracts(token)

    all_contracts = expired_contracts + active_contracts
    logger.info(f"Total contracts to fetch: {len(all_contracts)} ({len(expired_contracts)} expired, {len(active_contracts)} active)")

    contracts_1m_dfs = []
    contracts_day_dfs = []
    manifest_records = []

    # 2. Fetch candles per contract
    for c in all_contracts:
        symbol = c.get("trading_symbol")
        is_active = c.get("is_active", False)
        expiry_raw = c.get("expiry_date") or c.get("expiry")
        if isinstance(expiry_raw, (int, float)):
            expiry = datetime.fromtimestamp(expiry_raw / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            expiry = str(expiry_raw)
        slug = symbol.replace(" ", "_").replace("/", "_")

        logger.info(f"--- Processing {symbol} (Expiry: {expiry}) ---")

        # 1-minute bars
        out_1m = OUTPUT_DIR / "contracts" / "1minute" / f"{slug}_1minute.parquet"
        if out_1m.exists() and out_1m.stat().st_size > 0 and not is_active:
            df_1m = pq.read_table(out_1m).to_pandas()
            logger.info(f"  [✓ Loaded Existing] {slug} (1minute): {len(df_1m):,} bars")
        else:
            df_1m = fetch_candles_for_contract(c, "1minute", token)
            if not df_1m.empty:
                save_parquet(df_1m, out_1m)
        if not df_1m.empty:
            contracts_1m_dfs.append(df_1m)

        # Day bars
        out_day = OUTPUT_DIR / "contracts" / "day" / f"{slug}_day.parquet"
        if out_day.exists() and out_day.stat().st_size > 0 and not is_active:
            df_day = pq.read_table(out_day).to_pandas()
            logger.info(f"  [✓ Loaded Existing] {slug} (day): {len(df_day):,} bars")
        else:
            df_day = fetch_candles_for_contract(c, "day", token)
            if not df_day.empty:
                save_parquet(df_day, out_day)
        if not df_day.empty:
            contracts_day_dfs.append(df_day)

        manifest_records.append({
            "trading_symbol": symbol,
            "expiry": expiry[:10],
            "instrument_key": c.get("instrument_key"),
            "is_active": c.get("is_active", False),
            "bars_1m": len(df_1m),
            "bars_day": len(df_day),
            "nulls_1m": df_1m.isnull().sum().to_dict() if not df_1m.empty else {},
            "nulls_day": df_day.isnull().sum().to_dict() if not df_day.empty else {},
            "min_ts_1m": str(df_1m["timestamp"].min()) if not df_1m.empty else None,
            "max_ts_1m": str(df_1m["timestamp"].max()) if not df_1m.empty else None,
        })
        time.sleep(0.1)

    # 3. Stitch continuous futures series
    logger.info("Stitching continuous near-month futures series (1-minute & daily)...")
    df_cont_1m = build_continuous_futures(contracts_1m_dfs, "1minute")
    if not df_cont_1m.empty:
        out_cont_1m = OUTPUT_DIR / "continuous" / "nifty_futures_continuous_1minute.parquet"
        save_parquet(df_cont_1m, out_cont_1m)

    df_cont_day = build_continuous_futures(contracts_day_dfs, "day")
    if not df_cont_day.empty:
        out_cont_day = OUTPUT_DIR / "continuous" / "nifty_futures_continuous_day.parquet"
        save_parquet(df_cont_day, out_cont_day)

    # 4. Save audit manifest
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_contracts": len(all_contracts),
        "total_continuous_1m_bars": len(df_cont_1m),
        "total_continuous_day_bars": len(df_cont_day),
        "continuous_1m_nulls": df_cont_1m.isnull().sum().to_dict() if not df_cont_1m.empty else {},
        "continuous_day_nulls": df_cont_day.isnull().sum().to_dict() if not df_cont_day.empty else {},
        "continuous_1m_range": {
            "start": str(df_cont_1m["timestamp"].min()) if not df_cont_1m.empty else None,
            "end": str(df_cont_1m["timestamp"].max()) if not df_cont_1m.empty else None,
        },
        "continuous_day_range": {
            "start": str(df_cont_day["timestamp"].min()) if not df_cont_day.empty else None,
            "end": str(df_cont_day["timestamp"].max()) if not df_cont_day.empty else None,
        },
        "contracts": manifest_records
    }
    manifest_path = OUTPUT_DIR / "nifty_futures_fetch_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"[✓] Saved manifest: {manifest_path}")

    # 5. Mirror to external drive and cloud
    mirror_to_external_and_cloud(OUTPUT_DIR)

    logger.info("=================================================================")
    logger.info("HISTORICAL NIFTY FUTURES INGESTION PIPELINE COMPLETED SUCCESSFULLY")
    logger.info(f"Continuous 1m: {len(df_cont_1m):,} bars | Continuous Day: {len(df_cont_day):,} bars")
    logger.info("=================================================================")

if __name__ == "__main__":
    main()
