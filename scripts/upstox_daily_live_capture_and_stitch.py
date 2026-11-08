#!/usr/bin/env python3
"""
Automated Upstox Daily Live Capture & Post-Market Stitching Pipeline

1. MARKET HOURS (09:00 - 15:38 IST):
   - Downloads BOD instrument master
   - Subscribes in Full Mode (LTP, bid/ask, 5-level L2 depth, volume, OI)
   - Flushes atomic PyArrow Parquet chunks every 60 seconds to:
     /Volumes/TradeBotData/live market capture/YYYY-MM-DD/chunks/

2. POST-MARKET CLOSE (15:38 - 15:40 IST):
   - Gracefully closes WebSocket streamer
   - Concatenates & deduplicates all daily chunks
   - Generates upstox_full_ticks_YYYYMMDD_stitched.parquet
   - Fetches official 1m historical OHLCV candles
   - Generates stitching_summary_YYYYMMDD.json audit report
"""

import os
import sys
import time
import glob
import json
import gzip
import io
import urllib.request
import urllib.parse
import threading
import signal
import logging
import fcntl
from typing import Optional
from datetime import datetime, timezone, time as dt_time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import upstox_client
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("upstox_daily_pipeline")

from core.upstox_stream_broadcaster import (
    UpstoxStreamBroadcaster,
    UpstoxAsyncParquetRecorder,
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor

PRIMARY_BASE_DIRS = [
    ROOT / ".runtime" / "market_data",
    Path("/Volumes/TradeBotFast/live market capture"),
]
FALLBACK_BASE_DIR = ROOT / ".runtime" / "market_data"

def get_today_data_dir() -> Path:
    today_str = datetime.now().strftime("%Y-%m-%d")
    primary_dir = next((p for p in PRIMARY_BASE_DIRS if p.exists()), None)
    base_dir = primary_dir if primary_dir is not None else FALLBACK_BASE_DIR
    d = base_dir / today_str
    d.mkdir(parents=True, exist_ok=True)
    return d

def ensure_single_instance():
    lock_file_path = "/tmp/upstox_daily_pipeline.lock"
    lock_file = open(lock_file_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("Another instance of upstox_daily_pipeline is already running. Exiting.")
        sys.exit(0)
    return lock_file

def get_access_token() -> str:
    return os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()

def get_api_client(access_token: str = None):
    token = access_token or get_access_token()
    configuration = upstox_client.Configuration()
    configuration.access_token = token
    return upstox_client.ApiClient(configuration)

def fetch_instruments() -> pd.DataFrame:
    logger.info("Downloading instrument definitions from Upstox...")
    urls = ["https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"]
    instruments = []
    import ssl
    ssl_contexts = [None, ssl._create_unverified_context()]

    for url in urls:
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "Mozilla/5.0"})
        for ctx in ssl_contexts:
            try:
                kw = {"context": ctx} if ctx else {}
                with urllib.request.urlopen(req, timeout=15, **kw) as response:
                    with gzip.GzipFile(fileobj=io.BytesIO(response.read())) as f:
                        data = json.loads(f.read().decode("utf-8"))
                        instruments.extend(data)
                        logger.info(f"Downloaded {len(data)} instruments from Upstox.")
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")

    if not instruments:
        local_paths = [
            ROOT / "runtime/upstox_instruments/complete.json",
            ROOT / "runtime/upstox_instruments/complete.json.gz",
            ROOT / ".runtime/upstox_instruments.json.gz",
        ]
        for p in local_paths:
            if p.exists():
                try:
                    logger.info(f"Loading local cached instruments from {p}...")
                    if p.suffix == ".gz":
                        with gzip.open(p, "rt", encoding="utf-8") as f:
                            instruments = json.load(f)
                    else:
                        with open(p, "r", encoding="utf-8") as f:
                            instruments = json.load(f)
                    if isinstance(instruments, dict):
                        instruments = list(instruments.values())
                    break
                except Exception as e:
                    logger.error(f"Failed to read local file {p}: {e}")

    return pd.DataFrame(instruments) if instruments else pd.DataFrame()

def get_underlying_prices(access_token: str = None) -> dict[str, float]:
    import requests
    token = access_token or get_access_token()
    keys = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank", "BSE_INDEX|SENSEX"]
    encoded_keys = ",".join([urllib.parse.quote(k) for k in keys])
    headers = {"accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}"}
    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={encoded_keys}"
    fallback_prices = {"NIFTY": 24500.0, "BANKNIFTY": 52200.0, "SENSEX": 80000.0}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", {})
            nifty = data.get("NSE_INDEX:Nifty 50", {}).get("last_price") or fallback_prices["NIFTY"]
            banknifty = data.get("NSE_INDEX:Nifty Bank", {}).get("last_price") or fallback_prices["BANKNIFTY"]
            sensex = data.get("BSE_INDEX:SENSEX", {}).get("last_price") or fallback_prices["SENSEX"]
            return {"NIFTY": float(nifty), "BANKNIFTY": float(banknifty), "SENSEX": float(sensex)}
    except Exception as e:
        logger.warning(f"Error fetching underlying prices: {e}")
    return fallback_prices

def get_options_subscriptions(df_inst: pd.DataFrame, underlying_prices: dict[str, float]) -> dict[str, str]:
    subs = {}
    if df_inst.empty or "name" not in df_inst.columns:
        subs["NSE_INDEX|Nifty 50"] = "NIFTY 50"
        subs["NSE_INDEX|Nifty Bank"] = "NIFTY BANK"
        subs["BSE_INDEX|SENSEX"] = "SENSEX"
        return subs

    configs = {
        "NIFTY": {"name": "NIFTY", "interval": 50},
        "BANKNIFTY": {"name": "BANKNIFTY", "interval": 100},
        "SENSEX": {"name": "SENSEX", "interval": 100},
    }
    today_date = pd.to_datetime(datetime.now().date())

    for symbol, cfg in configs.items():
        ltp = underlying_prices.get(symbol, 0.0)
        if not ltp:
            continue
        interval = cfg["interval"]
        atm = round(ltp / interval) * interval
        strikes = [atm + (i * interval) for i in range(-10, 11)]

        df_sym = df_inst[(df_inst["name"] == cfg["name"]) & (df_inst["instrument_type"].isin(["CE", "PE"]))].copy()
        if df_sym.empty:
            continue
        df_sym["expiry_date"] = pd.to_datetime(df_sym["expiry"], unit="ms")
        df_future = df_sym[df_sym["expiry_date"] >= today_date]
        nearest_expiry = df_future["expiry_date"].min() if not df_future.empty else df_sym["expiry_date"].max()
        df_exp = df_sym[df_sym["expiry_date"] == nearest_expiry]
        df_strikes = df_exp[df_exp["strike_price"].isin(strikes)]

        for _, row in df_strikes.iterrows():
            subs[row["instrument_key"]] = row["trading_symbol"]

    subs["NSE_INDEX|Nifty 50"] = "NIFTY 50"
    subs["NSE_INDEX|Nifty Bank"] = "NIFTY BANK"
    subs["BSE_INDEX|SENSEX"] = "SENSEX"
    return subs

PER_ASSET_TOKEN_CEILINGS = {
    "NIFTY": 36,
    "SENSEX": 26,
    "BANKNIFTY": 26,
}
GLOBAL_MAX_TOTAL_TOKENS = 88

def count_asset_tokens(subscriptions: dict[str, str] | set[str], index_name: str) -> int:
    """Counts active option strike subscriptions belonging to a specific underlying asset."""
    idx_upper = index_name.upper()
    count = 0
    if isinstance(subscriptions, dict):
        for k, sym in subscriptions.items():
            if sym.startswith(idx_upper + " "):
                count += 1
    elif isinstance(subscriptions, (set, list)):
        for item in subscriptions:
            # item may be symbol or instrument key
            if item.startswith(idx_upper + " ") or f"|{idx_upper}_" in item:
                count += 1
    return count

def recenter_premarket_option_subscriptions(
    streamer,
    subscriptions: dict[str, str],
    df_inst: pd.DataFrame,
    premarket_spot: float,
    index_name: str = "NIFTY",
    max_total_tokens: int = 85,
    per_asset_max_tokens: Optional[int] = None,
) -> int:
    """Calculates updated ATM strike from pre-market (or 09:15 JIT) spot auction,
    identifies ATM +- 10 strikes, adds union of new contracts up to token quota ceilings,
    prioritizing nearest to ATM outward. Calls streamer.subscribe in 'full' mode.
    Enforces per-asset quota partitioning to prevent one gapping asset from starving others.
    Returns count of newly added strikes.
    """
    if df_inst is None or df_inst.empty or not premarket_spot or premarket_spot <= 0.0 or streamer is None:
        return 0

    idx_cfg = {
        "NIFTY": {"name": "NIFTY", "interval": 50},
        "BANKNIFTY": {"name": "BANKNIFTY", "interval": 100},
        "SENSEX": {"name": "SENSEX", "interval": 100},
    }
    cfg = idx_cfg.get(index_name.upper(), idx_cfg["NIFTY"])
    interval = cfg["interval"]
    atm = round(premarket_spot / interval) * interval

    # Order desired strikes from ATM outward: [0, 1, -1, 2, -2, ..., 10, -10]
    strike_offsets = [0]
    for i in range(1, 11):
        strike_offsets.extend([i, -i])
    ordered_desired_strikes = [atm + (off * interval) for off in strike_offsets]

    today_date = pd.to_datetime(datetime.now().date())
    df_sym = df_inst[(df_inst["name"] == cfg["name"]) & (df_inst["instrument_type"].isin(["CE", "PE"]))].copy()
    if df_sym.empty:
        return 0

    df_sym["expiry_date"] = pd.to_datetime(df_sym["expiry"], unit="ms")
    df_future = df_sym[df_sym["expiry_date"] >= today_date]
    nearest_expiry = df_future["expiry_date"].min() if not df_future.empty else df_sym["expiry_date"].max()
    df_exp = df_sym[df_sym["expiry_date"] == nearest_expiry]

    # Candidate keys mapped by strike priority
    candidate_keys_ordered = []
    for strike in ordered_desired_strikes:
        df_match = df_exp[df_exp["strike_price"] == strike]
        for _, row in df_match.iterrows():
            k = row["instrument_key"]
            sym = row["trading_symbol"]
            candidate_keys_ordered.append((k, sym, strike))

    # Add-only / Union subscription with quota partitioning
    new_keys_to_add = []
    current_tokens_count = len(subscriptions)
    global_available = max(0, max_total_tokens - current_tokens_count)

    # Per-asset token ceiling check
    asset_ceiling = per_asset_max_tokens if per_asset_max_tokens is not None else PER_ASSET_TOKEN_CEILINGS.get(index_name.upper(), 36)
    current_asset_tokens = count_asset_tokens(subscriptions, index_name)
    asset_available = max(0, asset_ceiling - current_asset_tokens)

    available_slots = min(global_available, asset_available)

    for k, sym, strike in candidate_keys_ordered:
        if k not in subscriptions:
            if len(new_keys_to_add) < available_slots:
                if isinstance(subscriptions, dict):
                    subscriptions[k] = sym
                elif isinstance(subscriptions, set):
                    subscriptions.add(k)
                new_keys_to_add.append(k)

    if new_keys_to_add:
        try:
            streamer.subscribe(new_keys_to_add, mode="full")
            logger.info(
                f"[Pre-Market Re-Centering ({index_name})] Spot: ₹{premarket_spot:.1f} | ATM: ₹{atm:.0f} | "
                f"Subscribed {len(new_keys_to_add)} new strikes (Asset tokens: {current_asset_tokens + len(new_keys_to_add)}/{asset_ceiling}, "
                f"Total tokens: {len(subscriptions)}/{max_total_tokens})."
            )
        except Exception as e:
            logger.error(f"[Pre-Market Re-Centering ({index_name})] Subscription failed: {e}")

    return len(new_keys_to_add)

def check_and_recenter_intraday_drift(
    streamer,
    subscriptions: dict[str, str],
    df_inst: pd.DataFrame,
    current_spot: float,
    last_subscribed_atm: float,
    index_name: str = "NIFTY",
    max_total_tokens: int = 88,
    per_asset_max_tokens: Optional[int] = None,
) -> tuple[int, float]:
    """Watches intraday spot drift against last subscribed ATM strike.
    If spot drifts >= 2 strikes from last subscribed ATM:
      - NIFTY: >= 100 pts drift
      - SENSEX: >= 200 pts drift
      - BANKNIFTY: >= 200 pts drift
    Expands subscription basket around new ATM up to per-asset and global token budget caps.
    Returns (added_count, updated_last_subscribed_atm).
    """
    if not current_spot or current_spot <= 0 or not last_subscribed_atm or last_subscribed_atm <= 0:
        return 0, last_subscribed_atm

    idx_intervals = {"NIFTY": 50, "SENSEX": 100, "BANKNIFTY": 100}
    interval = idx_intervals.get(index_name.upper(), 50)
    drift_threshold = 2 * interval

    drift_pts = abs(current_spot - last_subscribed_atm)
    if drift_pts < drift_threshold:
        return 0, last_subscribed_atm

    new_atm = round(current_spot / interval) * interval
    logger.info(
        f"[Intraday Strike Drift Detected ({index_name})] Current Spot: ₹{current_spot:.1f} drifted {drift_pts:.1f}pts "
        f"from Last ATM ₹{last_subscribed_atm:.0f} (Threshold: {drift_threshold}pts). Re-centering to new ATM ₹{new_atm:.0f}..."
    )

    added = recenter_premarket_option_subscriptions(
        streamer=streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        premarket_spot=current_spot,
        index_name=index_name,
        max_total_tokens=max_total_tokens,
        per_asset_max_tokens=per_asset_max_tokens,
    )
    return added, new_atm

def format_depth(market_level) -> str:
    depth = {"bids": [], "asks": []}
    quotes = market_level.get("bidAskQuote", [])[:5]
    for item in quotes:
        depth["bids"].append({"price": float(item.get("bidP", 0.0)), "quantity": int(item.get("bidQ", 0)), "orders": int(item.get("bqo", 0))})
        depth["asks"].append({"price": float(item.get("askP", 0.0)), "quantity": int(item.get("askQ", 0)), "orders": int(item.get("aqo", 0))})
    return json.dumps(depth)

# ----------------- POST MARKET STITCHING -----------------
def execute_post_market_stitching(date_str: str, date_compact: str, data_dir: Path):
    logger.info("=== STARTING AUTOMATIC POST-MARKET STITCHING ===")
    chunks_dir = data_dir / "chunks"
    chunk_files = sorted(glob.glob(str(chunks_dir / "*.parquet")))

    if not chunk_files:
        logger.warning(f"No chunk files found in {chunks_dir} to stitch.")
        return

    logger.info(f"Reading {len(chunk_files)} chunks...")
    dfs = []
    for cf in chunk_files:
        try:
            dfs.append(pd.read_parquet(cf))
        except Exception as e:
            logger.warning(f"Error reading chunk {cf}: {e}")

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        ts_col = "exchange_timestamp_ms" if "exchange_timestamp_ms" in df_all.columns else ("ts" if "ts" in df_all.columns else None)
        if ts_col:
            df_all = df_all.sort_values(ts_col).reset_index(drop=True)
            subset_cols = [ts_col, "token"] if "token" in df_all.columns else [ts_col]
            df_all = df_all.drop_duplicates(subset=subset_cols).reset_index(drop=True)
        initial_count = len(df_all)
        final_count = len(df_all)

        out_file = data_dir / f"upstox_full_ticks_{date_compact}_stitched.parquet"
        table = pa.Table.from_pandas(df_all)
        pq.write_table(table, out_file, compression="snappy")
        logger.info(f"[✓] Stitched master saved: {out_file.name} ({final_count:,} ticks, {out_file.stat().st_size / (1024*1024):.2f} MB)")

        summary = {
            "date": date_str,
            "total_chunks": len(chunk_files),
            "total_ticks": final_count,
            "duplicates_removed": initial_count - final_count,
            "unique_tokens": df_all["symbol"].nunique(),
            "file_path": str(out_file),
            "stitched_at_utc": datetime.now(timezone.utc).isoformat()
        }
        with open(data_dir / f"stitching_summary_{date_compact}.json", "w") as f:
            json.dump(summary, f, indent=2)

    # Fetch 1m historical index candles
    try:
        logger.info("Fetching official 1m index candles from Upstox API...")
        indices = {
            "NIFTY 50": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "SENSEX": "BSE_INDEX|SENSEX",
            "INDIA VIX": "NSE_INDEX|India VIX",
        }
        all_candles = []
        for name, key in indices.items():
            url_key = urllib.parse.quote(key)
            urls = [
                f"https://api.upstox.com/v2/historical-candle/intraday/{url_key}/1minute",
                f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/1/{date_str}/{date_str}"
            ]
            candles = []
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"Accept": "application/json", "Api-Version": "2.0", "User-Agent": "TradeBot/1.0", "Authorization": f"Bearer {get_access_token()}"})
                    with urllib.request.urlopen(req) as resp:
                        data = json.loads(resp.read().decode())
                        candles = data.get("data", {}).get("candles", [])
                        if candles:
                            break
                except Exception as e:
                    logger.debug(f"Attempt failed for {url}: {e}")

            logger.info(f" - {name}: retrieved {len(candles)} 1m candles")
            for c in candles:
                all_candles.append({
                    "timestamp": datetime.fromisoformat(c[0].replace("+05:30", "")),
                    "symbol": name,
                    "instrument_key": key,
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]),
                    "volume": float(c[5]), "oi": float(c[6]) if len(c) > 6 else 0.0
                })

        if all_candles:
            df_c = pd.DataFrame(all_candles).sort_values(["timestamp", "symbol"]).reset_index(drop=True)
            out_c_file = data_dir / f"indices_1m_{date_compact}.parquet"
            pq.write_table(pa.Table.from_pandas(df_c), out_c_file, compression="snappy")
            logger.info(f"[✓] Saved official 1m candles: {out_c_file.name} ({len(df_c):,} rows)")
    except Exception as e:
        logger.error(f"Error in historical candle fetch: {e}")

    logger.info("=== POST-MARKET STITCHING PIPELINE COMPLETED SUCCESSFULLY ===")

# ----------------- MAIN STREAMING LOOP -----------------
def main():
    lock_file = ensure_single_instance()

    access_token = get_access_token()
    if not access_token:
        logger.error("Missing UPSTOX_ACCESS_TOKEN in .env")
        sys.exit(1)

    api_client = get_api_client(access_token)

    df_inst = fetch_instruments()
    prices = get_underlying_prices(access_token)
    subscriptions = get_options_subscriptions(df_inst, prices)
    logger.info(f"Subscribing to {len(subscriptions)} tokens (ATM +- 10 options + indices).")

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_compact = datetime.now().strftime("%Y%m%d")
    data_dir = get_today_data_dir()
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # 1. Asynchronous Level-5 Parquet Recorder (Non-blocking Research Tape Writer)
    recorder = UpstoxAsyncParquetRecorder(
        output_dir=chunks_dir,
        chunk_size=2000,
        flush_interval_sec=10.0,
        max_queue_size=50000,
        watermark_ratio=0.8,
        fail_closed_on_saturation=False,
    )

    # 2. In-Memory Sentinel Adapter (O(1) latest state coalescing & cross-strike skew gate)
    sentinel_adapter = InMemorySentinelAdapter(
        skew_threshold_ms=250.0,
        staleness_timeout_ms=1000.0,
    )

    # 3. Embedded Sentinel Live Advisory Engine (< 1ms live paper evaluation)
    sentinel_advisor = SentinelLiveStreamAdvisor(
        adapter=sentinel_adapter,
        spread_veto_threshold=0.04,
        enable_stdout=True,
    )

    # 3b. Automatic Prior-Day Reference Level Seeding (Dynamic fail-closed reference bounds)
    try:
        primary_dir = next((p for p in PRIMARY_BASE_DIRS if p.exists()), None)
        search_dir = primary_dir if primary_dir is not None else FALLBACK_BASE_DIR
        if search_dir.exists():
            date_dirs = sorted([d for d in search_dir.iterdir() if d.is_dir() and d.name.startswith("2026-") and d.name < today_str])
            if date_dirs:
                last_session_dir = date_dirs[-1]
                compact_date = last_session_dir.name.replace("-", "")
                idx_file = last_session_dir / f"indices_1m_{compact_date}.parquet"
                if idx_file.exists():
                    import pandas as pd
                    df_idx = pd.read_parquet(idx_file)
                    sym_map = {"NIFTY": "NIFTY 50", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
                    for target, src_sym in sym_map.items():
                        sub = df_idx[df_idx["symbol"] == src_sym]
                        if not sub.empty:
                            pdh = float(sub["high"].max())
                            pdl = float(sub["low"].min())
                            pdc = float(sub.iloc[-1]["close"])
                            pdr = float(pdh - pdl)
                            sentinel_advisor.seed_prior_day_levels(
                                index_name=target,
                                pdh=pdh,
                                pdl=pdl,
                                pdc=pdc,
                                session_date=datetime.strptime(last_session_dir.name, "%Y-%m-%d").date(),
                                atr_20=pdr,
                            )
    except Exception as e:
        logger.warning(f"Failed to auto-seed prior-day levels: {e}")

    # 4. Stream Broadcaster (Fan-out to Sentinel in-memory + Async Parquet recorder)
    broadcaster = UpstoxStreamBroadcaster([
        recorder,
        sentinel_adapter,
        sentinel_advisor,
    ])
    logger.info("🛰️ Initialized UpstoxStreamBroadcaster with Async Recorder and Embedded Sentinel Advisor.")

    last_msg_time = time.time()
    streamer = None

    def on_message(message):
        nonlocal last_msg_time
        last_msg_time = time.time()
        if not isinstance(message, dict) or "feeds" not in message:
            return

        now_mono = time.monotonic_ns()
        now_utc = datetime.now(timezone.utc).isoformat()

        for key, feed in message["feeds"].items():
            ff = feed.get("fullFeed") or feed.get("ff")
            if not ff:
                continue
            market_ff = ff.get("marketFF") or ff.get("marketFf")
            index_ff = ff.get("indexFF") or ff.get("indexFf")

            sym_name = subscriptions.get(key, key)

            if market_ff:
                ltpc = market_ff.get("ltpc", {})
                ltp = float(ltpc.get("ltp", 0.0))
                market_level = market_ff.get("marketLevel", {})
                vol = int(float(market_ff.get("vtt", 0.0)))
                oi = int(float(market_ff.get("oi", 0.0)))
                quotes = market_level.get("bidAskQuote", [])

                depth_list = []
                for item in quotes[:5]:
                    depth_list.append({
                        "bid_price": float(item.get("bidP", 0.0)),
                        "bid_quantity": int(item.get("bidQ", 0)),
                        "bid_orders": int(item.get("bqo", 0)),
                        "ask_price": float(item.get("askP", 0.0)),
                        "ask_quantity": int(item.get("askQ", 0)),
                        "ask_orders": int(item.get("aqo", 0)),
                    })

                raw_depth = {
                    "token": key,
                    "symbol": sym_name,
                    "exchange_timestamp_ms": int(float(ltpc.get("ltt", 0) or time.time() * 1000)),
                    "ltp": ltp,
                    "volume": vol,
                    "open_interest": oi,
                    "depth": depth_list,
                }
                broadcaster.dispatch_depth(raw_depth, now_ns=now_mono, now_utc=now_utc)

            elif index_ff:
                ltpc = index_ff.get("ltpc", {})
                ltp = float(ltpc.get("ltp", 0.0))
                raw_tick = {
                    "token": key,
                    "symbol": sym_name,
                    "exchange_timestamp_ms": int(float(ltpc.get("ltt", 0) or time.time() * 1000)),
                    "ltp": ltp,
                    "volume": 0,
                    "open_interest": 0,
                    "best_bid": ltp,
                    "best_ask": ltp,
                }
                broadcaster.dispatch_tick(raw_tick, now_ns=now_mono, now_utc=now_utc)
                if ltp > 0:
                    if key in ("NSE_INDEX|Nifty 50", "NSE_INDEX:Nifty 50"):
                        prices["NIFTY"] = ltp
                    elif key in ("NSE_INDEX|Nifty Bank", "NSE_INDEX:Nifty Bank"):
                        prices["BANKNIFTY"] = ltp
                    elif key in ("BSE_INDEX|SENSEX", "BSE_INDEX:SENSEX"):
                        prices["SENSEX"] = ltp

    def on_open():
        logger.info("Connected to Upstox WebSocket (Full Mode). Subscribing...")
        if streamer:
            streamer.subscribe(list(subscriptions.keys()), mode="full")

    def on_close(code, reason):
        logger.warning(f"WebSocket closed: {code} - {reason}")

    def on_error(error):
        logger.error(f"WebSocket error: {error}")

    def start_streamer():
        nonlocal streamer
        if streamer:
            try:
                streamer.disconnect()
            except Exception:
                pass
        try:
            streamer = upstox_client.MarketDataStreamerV3(api_client)
            streamer.on("message", on_message)
            streamer.on("open", on_open)
            streamer.on("close", on_close)
            streamer.on("error", on_error)
            logger.info("Connecting to Upstox MarketDataStreamer...")
            streamer.connect()
        except Exception as e:
            logger.error(f"Failed to connect streamer: {e}")

    running = True

    def handle_shutdown(signum, frame):
        nonlocal running
        logger.info(f"Received shutdown signal ({signum}). Stopping live capture...")
        running = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    start_streamer()
    last_flush_time = time.time()
    market_close_time = dt_time(15, 41)  # Collect CAS data through 15:40 PM, stop stream and stitch at 15:41 IST
    premarket_recenter_done = False
    jit_opening_expansion_done = False
    late_day_refresh_done = False

    # Muhurat Session Awareness: Today is Sunday Diwali Muhurat (14:05 pre-open, 14:20 market open)
    is_sunday_muhurat = (datetime.now().weekday() == 6)
    pm_window_start = dt_time(14, 8, 45) if is_sunday_muhurat else dt_time(9, 8, 45)
    pm_window_end = dt_time(14, 15, 0) if is_sunday_muhurat else dt_time(9, 9, 30)
    jit_window_start = dt_time(14, 20, 5) if is_sunday_muhurat else dt_time(9, 15, 5)
    jit_window_end = dt_time(14, 21, 30) if is_sunday_muhurat else dt_time(9, 15, 30)
    drift_window_start = dt_time(14, 20, 0) if is_sunday_muhurat else dt_time(9, 30, 0)
    if is_sunday_muhurat:
        logger.info("🪔 [MUHURAT TRADING CONFIG] Pre-Open: 14:05 - 14:15 IST | Re-Centering: 14:08 - 14:15 IST | JIT Open: 14:20 IST.")

    # Track last subscribed ATM strikes per index for dynamic intraday drift watcher
    last_subscribed_atms: dict[str, float] = {
        "NIFTY": round(prices.get("NIFTY", 24500.0) / 50.0) * 50.0,
        "SENSEX": round(prices.get("SENSEX", 80000.0) / 100.0) * 100.0,
        "BANKNIFTY": round(prices.get("BANKNIFTY", 52200.0) / 100.0) * 100.0,
    }
    last_drift_check_time = time.time()

    while running:
        now = datetime.now()
        now_ts = time.time()

        # Check market close threshold (15:41 IST after CAS completes)
        if now.time() >= market_close_time:
            logger.info("Market close & CAS complete (15:41 IST). Ending streaming session...")
            break

        # Dynamic Multi-Asset Pre-Market Re-Centering Hook (09:08:45-09:09:30 or Muhurat 14:08:45-14:15:00)
        if not premarket_recenter_done and pm_window_start <= now.time() < pm_window_end:
            try:
                pm_quotes = get_underlying_prices(access_token)
                total_pm_added = 0
                for idx_key in ["NIFTY", "SENSEX", "BANKNIFTY"]:
                    pm_spot = pm_quotes.get(idx_key, 0.0)
                    idx_levels = sentinel_advisor.prior_day_levels.get(idx_key)
                    prev_close = idx_levels.pdc if (idx_levels and idx_levels.pdc > 0) else prices.get(idx_key, 0.0)
                    atr_20 = idx_levels.atr_20 if (idx_levels and idx_levels.atr_20 > 0) else 0.0
                    default_gap_thresh = 50.0 if idx_key == "NIFTY" else (150.0 if idx_key == "BANKNIFTY" else 200.0)
                    gap_threshold = (0.25 * atr_20) if atr_20 > 0 else default_gap_thresh

                    if pm_spot > 0:
                        gap_pts = abs(pm_spot - prev_close)
                        if gap_pts >= gap_threshold:
                            logger.info(
                                f"[Pre-Market Re-Centering Triggered ({idx_key})] PM Spot: ₹{pm_spot:.1f}, Prev Close: ₹{prev_close:.1f}, "
                                f"Gap: {gap_pts:.1f}pts >= Threshold: {gap_threshold:.1f}pts (0.25 * ATR={atr_20:.1f})."
                            )
                            added = recenter_premarket_option_subscriptions(
                                streamer=streamer,
                                subscriptions=subscriptions,
                                df_inst=df_inst,
                                premarket_spot=pm_spot,
                                index_name=idx_key,
                                max_total_tokens=85,
                            )
                            total_pm_added += added
                            logger.info(f"[Pre-Market Re-Centering ({idx_key})] Subscribed {added} new option strikes.")
                        else:
                            logger.info(
                                f"[Pre-Market Re-Centering ({idx_key})] Gap {gap_pts:.1f}pts < Threshold {gap_threshold:.1f}pts. Retaining initial basket."
                            )
                premarket_recenter_done = True
                logger.info(f"[Pre-Market Re-Centering Complete] Subscribed {total_pm_added} total new strikes across indices.")
            except Exception as e:
                logger.warning(f"[Pre-Market Re-Centering Warning] Encountered non-fatal error: {e}")
                # Guard to avoid tight retry loop during error
                premarket_recenter_done = True

        # JIT Opening Strike Expansion Hook (09:15:05-09:15:30 or Muhurat 14:20:05-14:21:30)
        # If open tick spot gaps beyond pre-market range, expand strike basket immediately
        if not jit_opening_expansion_done and jit_window_start <= now.time() < jit_window_end:
            try:
                jit_added = 0
                for idx_key in ["NIFTY", "SENSEX", "BANKNIFTY"]:
                    live_spot = prices.get(idx_key, 0.0) or sentinel_advisor.spots.get(idx_key, 0.0)
                    idx_levels = sentinel_advisor.prior_day_levels.get(idx_key)
                    prev_close = idx_levels.pdc if (idx_levels and idx_levels.pdc > 0) else 0.0
                    atr_20 = idx_levels.atr_20 if (idx_levels and idx_levels.atr_20 > 0) else 0.0
                    default_thresh = 40.0 if idx_key == "NIFTY" else (120.0 if idx_key == "BANKNIFTY" else 150.0)
                    gap_threshold = (0.20 * atr_20) if atr_20 > 0 else default_thresh

                    if live_spot > 0 and prev_close > 0:
                        gap_pts = abs(live_spot - prev_close)
                        if gap_pts >= gap_threshold:
                            logger.info(
                                f"[JIT Opening Expansion ({idx_key})] Live Spot: ₹{live_spot:.1f}, Prev Close: ₹{prev_close:.1f}, "
                                f"Gap: {gap_pts:.1f}pts >= Threshold: {gap_threshold:.1f}pts."
                            )
                            added = recenter_premarket_option_subscriptions(
                                streamer=streamer,
                                subscriptions=subscriptions,
                                df_inst=df_inst,
                                premarket_spot=live_spot,
                                index_name=idx_key,
                                max_total_tokens=95,
                            )
                            jit_added += added
                jit_opening_expansion_done = True
                if jit_added > 0:
                    logger.info(f"[JIT Opening Expansion Complete] Subscribed {jit_added} JIT strikes at market open.")
            except Exception as e:
                logger.warning(f"[JIT Opening Expansion Warning] Non-fatal error: {e}")
                jit_opening_expansion_done = True

        # Dynamic Intraday Strike Drift Watcher (09:30-15:20 or Muhurat 14:20-15:30)
        # Evaluates spot drift every 30 seconds and dynamically expands subscription if spot drifts >= 2 strikes
        if drift_window_start <= now.time() < dt_time(15, 30) and (now_ts - last_drift_check_time >= 30.0):
            last_drift_check_time = now_ts
            try:
                for idx_key in ["NIFTY", "SENSEX", "BANKNIFTY"]:
                    cur_spot = prices.get(idx_key, 0.0) or sentinel_advisor.spots.get(idx_key, 0.0)
                    last_atm = last_subscribed_atms.get(idx_key, 0.0)
                    if cur_spot > 0 and last_atm > 0:
                        added, updated_atm = check_and_recenter_intraday_drift(
                            streamer=streamer,
                            subscriptions=subscriptions,
                            df_inst=df_inst,
                            current_spot=cur_spot,
                            last_subscribed_atm=last_atm,
                            index_name=idx_key,
                            max_total_tokens=GLOBAL_MAX_TOTAL_TOKENS,
                        )
                        if added > 0:
                            last_subscribed_atms[idx_key] = updated_atm
            except Exception as e:
                logger.warning(f"[Intraday Drift Watcher Warning] Error: {e}")

        # Dynamic late-day option refresh at 15:23:00 - 15:24:00 IST
        # Subscribes ATM and ATM +/- 100 strikes around current spot to ensure 15:26 depth availability
        if not late_day_refresh_done and dt_time(15, 23) <= now.time() <= dt_time(15, 24):
            latest_spot = sentinel_advisor.latest_spot or underlying_prices.get("NIFTY", 0.0)

            if latest_spot > 0:
                try:
                    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions
                    added = refresh_late_day_option_subscriptions(streamer, subscriptions, df_inst, latest_spot)
                    logger.info(f"[Late-Day Refresh Triggered] Added {added} strikes around spot {latest_spot:.1f}")
                    late_day_refresh_done = True
                except Exception as e:
                    logger.error(f"[Late-Day Refresh Error] {e}")

        # Flush recorder chunks every 30s is handled internally by UpstoxAsyncParquetRecorder background worker thread
        if now_ts - last_msg_time > 35:
            logger.warning("Watchdog alert: No tick received for 35s. Reconnecting streamer...")
            start_streamer()
            last_msg_time = now_ts

        time.sleep(1)

    # 1. Final Flush & Stop Async Recorder
    logger.info("Stopping UpstoxAsyncParquetRecorder and flushing remaining depth records...")
    recorder.flush_and_stop()

    if streamer:
        try:
            streamer.disconnect()
        except Exception:
            pass

    # 2. Automatic Post-Market Stitching & Archival
    execute_post_market_stitching(today_str, today_compact, data_dir)
    sys.exit(0)

if __name__ == "__main__":
    main()
