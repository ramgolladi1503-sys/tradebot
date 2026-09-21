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
from datetime import datetime, timezone, time as dt_time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import upstox_client
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("upstox_daily_pipeline")

PRIMARY_BASE_DIR = Path("/Volumes/TradeBotData/live market capture")
FALLBACK_BASE_DIR = ROOT / ".runtime" / "market_data"

def get_today_data_dir() -> Path:
    today_str = datetime.now().strftime("%Y-%m-%d")
    d = (PRIMARY_BASE_DIR if PRIMARY_BASE_DIR.exists() else FALLBACK_BASE_DIR) / today_str
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
        df_all = pd.concat(dfs, ignore_index=True).sort_values("ts").reset_index(drop=True)
        initial_count = len(df_all)
        df_all = df_all.drop_duplicates(subset=["ts", "token"]).reset_index(drop=True)
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

    tick_buffer = []
    buffer_lock = threading.Lock()

    schema = pa.schema([
        ("ts", pa.float64()),
        ("token", pa.string()),
        ("symbol", pa.string()),
        ("ltp", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("vol", pa.float64()),
        ("oi", pa.float64()),
        ("depth", pa.string())
    ])

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_compact = datetime.now().strftime("%Y%m%d")
    data_dir = get_today_data_dir()
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    def flush_buffer():
        nonlocal tick_buffer
        with buffer_lock:
            if not tick_buffer:
                return
            to_flush = tick_buffer
            tick_buffer = []

        now_dt = datetime.now()
        chunk_file = chunks_dir / f"chunk_{today_compact}_{int(now_dt.timestamp() * 1000)}.parquet"
        df = pd.DataFrame(to_flush)
        df["ts"] = df["ts"].astype(float)
        df["token"] = df["token"].astype(str)
        df["symbol"] = df["symbol"].astype(str)
        df["ltp"] = df["ltp"].astype(float)
        df["bid"] = df["bid"].astype(float)
        df["ask"] = df["ask"].astype(float)
        df["vol"] = df["vol"].astype(float)
        df["oi"] = df["oi"].astype(float)
        df["depth"] = df["depth"].astype(str)

        try:
            table = pa.Table.from_pandas(df, schema=schema)
            pq.write_table(table, chunk_file, compression="snappy")
            logger.info(f"Flushed {len(df)} ticks to {chunk_file.name}")
        except Exception as e:
            logger.error(f"Failed to write parquet chunk: {e}")

    last_msg_time = time.time()
    streamer = None

    def on_message(message):
        nonlocal last_msg_time
        last_msg_time = time.time()
        if not isinstance(message, dict) or "feeds" not in message:
            return

        for key, feed in message["feeds"].items():
            ff = feed.get("fullFeed") or feed.get("ff")
            if not ff:
                continue
            market_ff = ff.get("marketFF") or ff.get("marketFf")
            index_ff = ff.get("indexFF") or ff.get("indexFf")

            ltp, bid, ask, vol, oi = 0.0, 0.0, 0.0, 0.0, 0.0
            depth_str = '{"bids": [], "asks": []}'

            if market_ff:
                ltpc = market_ff.get("ltpc", {})
                ltp = float(ltpc.get("ltp", 0.0))
                market_level = market_ff.get("marketLevel", {})
                depth_str = format_depth(market_level)
                quotes = market_level.get("bidAskQuote", [])
                if quotes:
                    bid = float(quotes[0].get("bidP", 0.0))
                    ask = float(quotes[0].get("askP", 0.0))
                vol = float(market_ff.get("vtt", 0.0))
                oi = float(market_ff.get("oi", 0.0))
            elif index_ff:
                ltpc = index_ff.get("ltpc", {})
                ltp = float(ltpc.get("ltp", 0.0))
            else:
                continue

            record = {
                "ts": time.time(),
                "token": key,
                "symbol": subscriptions.get(key, key),
                "ltp": ltp,
                "bid": bid,
                "ask": ask,
                "vol": vol,
                "oi": oi,
                "depth": depth_str
            }
            with buffer_lock:
                tick_buffer.append(record)

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
    late_day_refresh_done = False

    while running:
        now = datetime.now()
        now_ts = time.time()

        # Check market close threshold (15:41 IST after CAS completes)
        if now.time() >= market_close_time:
            logger.info("Market close & CAS complete (15:41 IST). Ending streaming session...")
            break

        # Dynamic late-day option refresh at 15:23:00 - 15:24:00 IST
        # Subscribes ATM and ATM +/- 100 strikes around current spot to ensure 15:26 depth availability
        if not late_day_refresh_done and dt_time(15, 23) <= now.time() <= dt_time(15, 24):
            latest_spot = 0.0
            with buffer_lock:
                for t in reversed(tick_buffer):
                    if t.get("token") == "NSE_INDEX|Nifty 50":
                        latest_spot = float(t.get("ltp", 0.0))
                        break
            if not latest_spot:
                latest_spot = underlying_prices.get("NIFTY", 0.0)

            if latest_spot > 0:
                try:
                    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions
                    added = refresh_late_day_option_subscriptions(streamer, subscriptions, df_inst, latest_spot)
                    logger.info(f"[Late-Day Refresh Triggered] Added {added} strikes around spot {latest_spot:.1f}")
                    late_day_refresh_done = True
                except Exception as e:
                    logger.error(f"[Late-Day Refresh Error] {e}")

        if now_ts - last_flush_time >= 60:
            flush_buffer()
            last_flush_time = now_ts

        if now_ts - last_msg_time > 35:
            logger.warning("Watchdog alert: No tick received for 35s. Reconnecting streamer...")
            start_streamer()
            last_msg_time = now_ts

        time.sleep(1)

    # 1. Final Flush
    flush_buffer()
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
