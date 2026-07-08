#!/usr/bin/env python3
"""
Scheduled Tick Data Collector
Connects to Kite WebSocket and logs full tick data (LTP, bid, ask) for all active options.
Automatically stops at 15:35 IST.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, time as datetime_time
from pathlib import Path

# Setup paths and imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.kite_client import kite_client
from kiteconnect import KiteTicker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("tick_collector")


def get_target_tokens() -> dict[int, str]:
    """Dynamically resolves instrument tokens for NIFTY/BANKNIFTY/SENSEX ATM +/- wide range and VIX."""
    logger.info("Fetching instruments from NFO/NSE/BFO/BSE...")
    kite_client.ensure()

    nfo_insts = []
    nse_insts = []
    bfo_insts = []
    bse_insts = []

    try:
        nfo_insts = kite_client.instruments_cached("NFO")
    except Exception as e:
        logger.warning(f"Failed to fetch NFO instruments: {e}")

    try:
        nse_insts = kite_client.instruments_cached("NSE")
    except Exception as e:
        logger.warning(f"Failed to fetch NSE instruments: {e}")

    try:
        bfo_insts = kite_client.instruments_cached("BFO")
    except Exception as e:
        logger.warning(f"Failed to fetch BFO instruments: {e}")

    try:
        bse_insts = kite_client.instruments_cached("BSE")
    except Exception as e:
        logger.warning(f"Failed to fetch BSE instruments: {e}")

    nifty_token = None
    banknifty_token = None
    vix_token = None
    sensex_token = None

    for inst in nse_insts:
        if inst.get("tradingsymbol") == "NIFTY 50":
            nifty_token = inst.get("instrument_token")
        if inst.get("tradingsymbol") == "NIFTY BANK":
            banknifty_token = inst.get("instrument_token")
        if inst.get("tradingsymbol") == "INDIA VIX":
            vix_token = inst.get("instrument_token")

    for inst in bse_insts:
        if inst.get("tradingsymbol") == "SENSEX":
            sensex_token = inst.get("instrument_token")

    # Fetch spot prices for indices
    spot_symbols = []
    if nifty_token:
        spot_symbols.append("NSE:NIFTY 50")
    if banknifty_token:
        spot_symbols.append("NSE:NIFTY BANK")
    if sensex_token:
        spot_symbols.append("BSE:SENSEX")
    if vix_token:
        spot_symbols.append("NSE:INDIA VIX")

    prices = {}
    if spot_symbols:
        try:
            prices = kite_client.ltp(spot_symbols)
        except Exception as e:
            logger.warning(f"Failed to fetch LTP for spot symbols {spot_symbols}: {e}")

    nifty_spot = prices.get("NSE:NIFTY 50", {}).get("last_price") or 22000.0
    banknifty_spot = prices.get("NSE:NIFTY BANK", {}).get("last_price") or 48000.0
    sensex_spot = prices.get("BSE:SENSEX", {}).get("last_price") or 77000.0

    nifty_atm = round(nifty_spot / 50.0) * 50.0
    banknifty_atm = round(banknifty_spot / 100.0) * 100.0
    sensex_atm = round(sensex_spot / 100.0) * 100.0

    today = datetime.now().date()

    nifty_opts = [
        i
        for i in nfo_insts
        if i.get("name") == "NIFTY"
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry")
        and i.get("expiry") >= today
    ]
    banknifty_opts = [
        i
        for i in nfo_insts
        if i.get("name") == "BANKNIFTY"
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry")
        and i.get("expiry") >= today
    ]
    sensex_opts = [
        i
        for i in bfo_insts
        if i.get("name") == "SENSEX"
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry")
        and i.get("expiry") >= today
    ]

    nifty_expiries = sorted(list(set([i["expiry"] for i in nifty_opts])))
    banknifty_expiries = sorted(list(set([i["expiry"] for i in banknifty_opts])))
    sensex_expiries = sorted(list(set([i["expiry"] for i in sensex_opts])))

    target_tokens = {}
    if nifty_token:
        target_tokens[nifty_token] = "NIFTY 50"
    if banknifty_token:
        target_tokens[banknifty_token] = "NIFTY BANK"
    if sensex_token:
        target_tokens[sensex_token] = "SENSEX"
    if vix_token:
        target_tokens[vix_token] = "INDIA VIX"

    if nifty_expiries:
        exp = nifty_expiries[0]
        for opt in nifty_opts:
            if opt.get("expiry") == exp and abs(opt.get("strike", 0.0) - nifty_atm) <= 1000:
                target_tokens[opt["instrument_token"]] = opt["tradingsymbol"]

    if banknifty_expiries:
        exp = banknifty_expiries[0]
        for opt in banknifty_opts:
            if opt.get("expiry") == exp and abs(opt.get("strike", 0.0) - banknifty_atm) <= 2000:
                target_tokens[opt["instrument_token"]] = opt["tradingsymbol"]

    if sensex_expiries:
        exp = sensex_expiries[0]
        for opt in sensex_opts:
            if opt.get("expiry") == exp and abs(opt.get("strike", 0.0) - sensex_atm) <= 2000:
                target_tokens[opt["instrument_token"]] = opt["tradingsymbol"]

    return target_tokens


def main():
    target_tokens = get_target_tokens()
    logger.info(f"Subscribing to {len(target_tokens)} tokens for full tick collection.")

    TOKEN_PATH = ROOT / ".runtime" / "kite_access_token"
    API_KEY = os.getenv("KITE_API_KEY", "").strip()
    ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "").strip()

    # Wait 15 minutes per retry, for up to 10 tries (2.5 hours total)
    max_retries = 10
    for attempt in range(max_retries):
        if not ACCESS_TOKEN and TOKEN_PATH.exists():
            try:
                ACCESS_TOKEN = TOKEN_PATH.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        if API_KEY and ACCESS_TOKEN:
            break

        logger.warning(
            f"Waiting 15m for Kite API credentials... (Attempt {attempt + 1}/{max_retries})"
        )
        time.sleep(15 * 60)

    if not API_KEY or not ACCESS_TOKEN:
        logger.error("Missing Kite API credentials after timeout. Exiting.")
        sys.exit(1)

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / ".runtime" / "market_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"ticks_{date_str}.parquet"

    import pyarrow as pa
    import pyarrow.parquet as pq
    import pandas as pd

    schema = pa.schema([
        ("ts", pa.float64()),
        ("token", pa.int64()),
        ("symbol", pa.string()),
        ("ltp", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("vol", pa.int64())
    ])

    writer = pq.ParquetWriter(out_file, schema)
    tick_buffer = []
    BUFFER_SIZE = 5000

    def flush_buffer():
        nonlocal tick_buffer
        if not tick_buffer:
            return
        try:
            df = pd.DataFrame(tick_buffer)
            table = pa.Table.from_pandas(df, schema=schema)
            writer.write_table(table)
            tick_buffer.clear()
            logger.info(f"Flushed {len(df)} ticks to parquet.")
        except Exception as e:
            logger.error(f"Error flushing parquet: {e}")

    kws = KiteTicker(API_KEY, ACCESS_TOKEN)
    stop_time = datetime_time(15, 35)

    def on_ticks(ws, ticks):
        now = datetime.now()
        if now.time() >= stop_time:
            logger.info("Market close reached. Shutting down tick collector.")
            flush_buffer()
            try:
                writer.close()
                ws.close()
            except:
                pass
            sys.exit(0)

        for t in ticks:
            try:
                record = {
                    "ts": time.time(),
                    "token": int(t.get("instrument_token", 0)),
                    "symbol": target_tokens.get(
                        t.get("instrument_token"), str(t.get("instrument_token"))
                    ),
                    "ltp": float(t.get("last_price", 0.0)),
                    "bid": float(t.get("depth", {}).get("buy", [{}])[0].get("price", 0.0))
                    if "depth" in t and t["depth"].get("buy") else None,
                    "ask": float(t.get("depth", {}).get("sell", [{}])[0].get("price", 0.0))
                    if "depth" in t and t["depth"].get("sell") else None,
                    "vol": int(t.get("volume_traded", 0)),
                }
                tick_buffer.append(record)
            except Exception as e:
                pass
        
        if len(tick_buffer) >= BUFFER_SIZE:
            flush_buffer()

    def on_connect(ws, response):
        logger.info("Connected to Kite WebSocket.")
        tokens = list(target_tokens.keys())
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)

    def on_close(ws, code, reason):
        logger.warning(f"WebSocket closed: {code} - {reason}")

    def on_error(ws, code, reason):
        logger.error(f"WebSocket error: {code} - {reason}")

    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error

    def handle_sigint(*args):
        logger.info("Shutting down collector due to signal...")
        flush_buffer()
        try:
            writer.close()
            kws.close()
        except:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    logger.info("Starting KiteTicker loop...")
    kws.connect(threaded=False)


if __name__ == "__main__":
    main()
