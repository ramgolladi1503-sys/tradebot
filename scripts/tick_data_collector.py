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
    """Dynamically resolves instrument tokens for NIFTY/BANKNIFTY ATM +/- wide range, SENSEX, and INDIA VIX."""
    logger.info("Fetching instruments from NFO/NSE/BSE...")
    kite_client.ensure()
    nfo_insts = kite_client.instruments_cached("NFO")
    nse_insts = kite_client.instruments_cached("NSE")
    bse_insts = kite_client.instruments_cached("BSE")

    nifty_token = None
    banknifty_token = None
    for inst in nse_insts:
        if inst["tradingsymbol"] == "NIFTY 50":
            nifty_token = inst["instrument_token"]
        if inst["tradingsymbol"] == "NIFTY BANK":
            banknifty_token = inst["instrument_token"]

    sensex_token = None
    for inst in bse_insts:
        if inst["tradingsymbol"] == "SENSEX":
            sensex_token = inst["instrument_token"]
            break

    vix_token = None
    for inst in nse_insts:
        if inst["tradingsymbol"] == "INDIA VIX":
            vix_token = inst["instrument_token"]
            break

    prices = kite_client.ltp([f"NSE:NIFTY 50", f"NSE:NIFTY BANK"])
    nifty_spot = prices.get("NSE:NIFTY 50", {}).get("last_price", 22000.0)
    banknifty_spot = prices.get("NSE:NIFTY BANK", {}).get("last_price", 48000.0)

    nifty_atm = round(nifty_spot / 50.0) * 50.0
    banknifty_atm = round(banknifty_spot / 100.0) * 100.0

    today = datetime.now().date()
    nifty_opts = [
        i
        for i in nfo_insts
        if i["name"] == "NIFTY"
        and i["instrument_type"] in ["CE", "PE"]
        and i["expiry"] >= today
    ]
    banknifty_opts = [
        i
        for i in nfo_insts
        if i["name"] == "BANKNIFTY"
        and i["instrument_type"] in ["CE", "PE"]
        and i["expiry"] >= today
    ]

    nifty_expiries = sorted(list(set([i["expiry"] for i in nifty_opts])))
    banknifty_expiries = sorted(list(set([i["expiry"] for i in banknifty_opts])))

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
            if opt["expiry"] == exp and abs(opt["strike"] - nifty_atm) <= 1000:
                target_tokens[opt["instrument_token"]] = opt["tradingsymbol"]

    if banknifty_expiries:
        exp = banknifty_expiries[0]
        for opt in banknifty_opts:
            if opt["expiry"] == exp and abs(opt["strike"] - banknifty_atm) <= 2000:
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

    date_str = datetime.now().strftime("%Y%m%d")
    out_dir = ROOT / ".runtime" / "market_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"ticks_{date_str}.jsonl"

    f_out = open(out_file, "a", buffering=1)  # Line buffered

    stop_time = datetime_time(15, 35)
    kws = None

    def on_ticks(ws, ticks):
        now = datetime.now()
        if now.time() >= stop_time:
            logger.info("Market close reached. Shutting down tick collector.")
            try:
                ws.close()
            except:
                pass
            f_out.close()
            sys.exit(0)

        for t in ticks:
            try:
                record = {
                    "ts": time.time(),
                    "token": t.get("instrument_token"),
                    "symbol": target_tokens.get(
                        t.get("instrument_token"), str(t.get("instrument_token"))
                    ),
                    "ltp": t.get("last_price"),
                    "bid": t.get("depth", {}).get("buy", [{}])[0].get("price")
                    if "depth" in t and t["depth"].get("buy")
                    else None,
                    "ask": t.get("depth", {}).get("sell", [{}])[0].get("price")
                    if "depth" in t and t["depth"].get("sell")
                    else None,
                    "vol": t.get("volume_traded"),
                }
                f_out.write(json.dumps(record) + "\n")
            except Exception as e:
                pass

    def on_connect(ws, response):
        logger.info("Connected to Kite WebSocket.")
        tokens = list(target_tokens.keys())
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)

    def on_close(ws, code, reason):
        logger.warning(f"WebSocket closed: {code} - {reason}")

    def on_error(ws, code, reason):
        logger.error(f"WebSocket error: {code} - {reason}")

    def handle_sigint(*args):
        logger.info("Shutting down collector due to signal...")
        if kws is not None:
            try:
                kws.close()
            except:
                pass
        try:
            f_out.close()
        except:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    while True:
        now = datetime.now()
        if now.time() >= stop_time:
            logger.info("Market close reached. Shutting down tick collector.")
            break

        logger.info("Initializing KiteTicker client...")
        kws = KiteTicker(API_KEY, ACCESS_TOKEN)
        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_close = on_close
        kws.on_error = on_error

        try:
            logger.info("Starting KiteTicker loop...")
            kws.connect(threaded=False)
        except Exception as e:
            logger.error(f"KiteTicker exception in loop: {e}")

        if datetime.now().time() >= stop_time:
            break

        logger.info("Reconnection cooldown. Waiting 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    main()
