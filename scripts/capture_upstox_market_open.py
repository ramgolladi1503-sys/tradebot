#!/usr/bin/env python3
"""
Upstox Market Open Data Capture Path

Connects to Upstox MarketDataStreamerV3 and logs full tick data.
Captures complete market payload natively received from Upstox, providing a full replay-safe and debuggable evidence trail.
Strictly read-only and offline-safe.
Automatically stops at 15:35 IST and produces a replay-grade provenance manifest.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import socket
import hashlib
from datetime import datetime, time as datetime_time, timezone, timedelta
from pathlib import Path
import threading

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
import upstox_client

# Setup paths and imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.upstox_instruments import load_instruments, default_instruments_path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("upstox_capture")

def get_target_keys(token: str) -> tuple[dict[str, str], str, list[str]]:
    """
    Dynamically resolves instrument keys for NIFTY/BANKNIFTY/SENSEX ATM +/- wide range and VIX.
    Returns:
        target_keys: dict mapping instrument_key to tradingsymbol
        instrument_hash: SHA256 of the loaded instrument master
        errors: list of error strings encountered during lookup
    """
    logger.info("Resolving instruments from local cache...")
    errors = []
    
    inst_path = default_instruments_path()
    if not inst_path or not inst_path.exists():
        logger.error(f"Instrument master missing at {inst_path}.")
        raise FileNotFoundError("Upstox instruments file not found. Run scripts/fetch_upstox_instruments.py first.")
        
    with open(inst_path, "rb") as f:
        instrument_hash = hashlib.sha256(f.read()).hexdigest()

    instruments = load_instruments(inst_path)
    
    nfo_insts = []
    nse_insts = []
    bfo_insts = []
    bse_insts = []
    
    for row in instruments:
        exch = (row.get("exchange") or "").upper()
        if exch == "NFO":
            nfo_insts.append(row)
        elif exch == "NSE_EQ" or exch == "NSE_INDEX":
            nse_insts.append(row)
        elif exch == "BFO":
            bfo_insts.append(row)
        elif exch == "BSE_EQ" or exch == "BSE_INDEX":
            bse_insts.append(row)
            
    nifty_key = None
    banknifty_key = None
    vix_key = None
    sensex_key = None
    
    for inst in nse_insts:
        if inst.get("tradingsymbol") == "NIFTY 50":
            nifty_key = inst.get("instrument_key")
        elif inst.get("tradingsymbol") == "NIFTY BANK":
            banknifty_key = inst.get("instrument_key")
        elif inst.get("tradingsymbol") == "INDIA VIX":
            vix_key = inst.get("instrument_key")
            
    for inst in bse_insts:
        if inst.get("tradingsymbol") == "SENSEX":
            sensex_key = inst.get("instrument_key")

    spot_keys = []
    if nifty_key: spot_keys.append(nifty_key)
    if banknifty_key: spot_keys.append(banknifty_key)
    if sensex_key: spot_keys.append(sensex_key)
    if vix_key: spot_keys.append(vix_key)
    
    nifty_spot = 22000.0
    banknifty_spot = 48000.0
    sensex_spot = 77000.0
    
    if spot_keys:
        import urllib.request
        keys_str = ",".join(spot_keys)
        url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={keys_str}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                resp_data = json.loads(response.read().decode())
                data = resp_data.get("data", {})
                if nifty_key and nifty_key in data:
                    nifty_spot = data[nifty_key].get("last_price", nifty_spot)
                if banknifty_key and banknifty_key in data:
                    banknifty_spot = data[banknifty_key].get("last_price", banknifty_spot)
                if sensex_key and sensex_key in data:
                    sensex_spot = data[sensex_key].get("last_price", sensex_spot)
        except Exception as e:
            err = f"Failed to fetch LTP for spot symbols: {e}. Using fallback prices."
            logger.warning(err)
            errors.append(err)

    if not nifty_key: errors.append("NIFTY 50 spot key not found.")
    if not banknifty_key: errors.append("NIFTY BANK spot key not found.")
    if not sensex_key: errors.append("SENSEX spot key not found.")

    nifty_atm = round(nifty_spot / 50.0) * 50.0
    banknifty_atm = round(banknifty_spot / 100.0) * 100.0
    sensex_atm = round(sensex_spot / 100.0) * 100.0

    today = datetime.now().date()
    
    def _coerce_date(value) -> datetime.date | None:
        if not value: return None
        try:
            return datetime.fromisoformat(str(value).split("T")[0]).date()
        except:
            return None
            
    nifty_opts = [
        i for i in nfo_insts
        if (i.get("name") or i.get("underlying")) == "NIFTY"
        and i.get("instrument_type") in ["CE", "PE"]
        and _coerce_date(i.get("expiry")) 
        and _coerce_date(i.get("expiry")) >= today
    ]
    banknifty_opts = [
        i for i in nfo_insts
        if (i.get("name") or i.get("underlying")) == "BANKNIFTY"
        and i.get("instrument_type") in ["CE", "PE"]
        and _coerce_date(i.get("expiry")) 
        and _coerce_date(i.get("expiry")) >= today
    ]
    sensex_opts = [
        i for i in bfo_insts
        if (i.get("name") or i.get("underlying")) == "SENSEX"
        and i.get("instrument_type") in ["CE", "PE"]
        and _coerce_date(i.get("expiry")) 
        and _coerce_date(i.get("expiry")) >= today
    ]

    nifty_expiries = sorted(list(set([_coerce_date(i.get("expiry")) for i in nifty_opts])))
    banknifty_expiries = sorted(list(set([_coerce_date(i.get("expiry")) for i in banknifty_opts])))
    sensex_expiries = sorted(list(set([_coerce_date(i.get("expiry")) for i in sensex_opts])))

    target_keys = {}
    if nifty_key:
        target_keys[nifty_key] = "NIFTY 50"
    if banknifty_key:
        target_keys[banknifty_key] = "NIFTY BANK"
    if sensex_key:
        target_keys[sensex_key] = "SENSEX"
    if vix_key:
        target_keys[vix_key] = "INDIA VIX"

    def _add_strikes(opts, exp, atm, spread):
        for opt in opts:
            if _coerce_date(opt.get("expiry")) == exp and abs(float(opt.get("strike_price") or opt.get("strike", 0.0)) - atm) <= spread:
                target_keys[opt["instrument_key"]] = opt["tradingsymbol"]

    if nifty_expiries:
        _add_strikes(nifty_opts, nifty_expiries[0], nifty_atm, 1000)
    else:
        errors.append("No NIFTY options found for current/future expiries.")
        
    if banknifty_expiries:
        _add_strikes(banknifty_opts, banknifty_expiries[0], banknifty_atm, 2000)
    else:
        errors.append("No BANKNIFTY options found for current/future expiries.")
        
    if sensex_expiries:
        _add_strikes(sensex_opts, sensex_expiries[0], sensex_atm, 2000)
    else:
        errors.append("No SENSEX options found for current/future expiries.")

    return target_keys, instrument_hash, errors


def parse_market_message(msg: dict, target_keys: dict[str, str], ts_recv: float) -> tuple[list[dict], int]:
    """
    Defensively parses the incoming websocket dictionary into normalized replay-grade ticks.
    Returns (list_of_parsed_records, missing_field_count)
    """
    records = []
    missing_count = 0
    
    def _safe_float(val):
        nonlocal missing_count
        if val is None or val == "":
            missing_count += 1
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            missing_count += 1
            return None

    raw_websocket_payload = json.dumps(msg) if isinstance(msg, dict) else "{}"
    feeds = msg.get("feeds") if isinstance(msg, dict) else None
    
    if not isinstance(feeds, dict):
        return records, missing_count

    for key, data in feeds.items():
        if not isinstance(data, dict):
            continue
            
        ff = data.get("ff") or data.get("if")
        if not isinstance(ff, dict):
            continue
            
        market_ff = ff.get("marketFF") or ff.get("indexFF")
        if not isinstance(market_ff, dict):
            continue
            
        ltpc = market_ff.get("ltpc", {})
        market_level = market_ff.get("marketLevel", {})
        market_depth = market_ff.get("marketDepth", {})
        eohc = market_ff.get("eohc", {})
        
        ltp = ltpc.get("ltp")
        ltt = ltpc.get("ltt")
        ltq = ltpc.get("ltq")
        cp = ltpc.get("cp") # close price (prev_close)

        ts_feed = None
        if ltt is not None:
            try:
                ltt_val = float(ltt)
                if ltt_val > 0:
                    ts_feed = ltt_val / 1000.0
            except:
                pass

        if ts_feed is not None:
            quote_age_sec = max(0.0, ts_recv - ts_feed)
        else:
            missing_count += 1
            quote_age_sec = 0.0

        bids = market_depth.get("buy", [])
        asks = market_depth.get("sell", [])
        
        bid = bids[0].get("price") if bids and isinstance(bids, list) and isinstance(bids[0], dict) else None
        ask = asks[0].get("price") if asks and isinstance(asks, list) and isinstance(asks[0], dict) else None
        
        vol = ltpc.get("vtt")
        oi = market_level.get("oi")
        
        # OHLC and additional fields
        open_p = eohc.get("open")
        high_p = eohc.get("high")
        low_p = eohc.get("low")
        close_p = eohc.get("close")
        
        vwap_p = market_level.get("atp") # ATP serves as VWAP
        
        change = None
        change_percent = None
        if ltp is not None and cp is not None:
            try:
                ltp_val = float(ltp)
                cp_val = float(cp)
                if cp_val > 0:
                    change = ltp_val - cp_val
                    change_percent = (change / cp_val) * 100.0
            except:
                pass

        if change is None: missing_count += 1
        if change_percent is None: missing_count += 1

        depth_json = json.dumps(market_depth) if market_depth else "{}"
        raw_payload = json.dumps(data) if data else "{}"
        
        exchange = str(key).split("|")[0] if "|" in str(key) else None
        if exchange is None:
            missing_count += 1
        
        record = {
            "ts_recv": ts_recv,
            "ts_feed": _safe_float(ts_feed if ts_feed else None),
            "token": str(key),
            "symbol": target_keys.get(key, str(key)),
            "exchange": exchange,
            "ltp": _safe_float(ltp),
            "bid": _safe_float(bid),
            "ask": _safe_float(ask),
            "vol": _safe_float(vol),
            "oi": _safe_float(oi),
            "depth": depth_json,
            "quote_age_sec": float(quote_age_sec),
            "quote_source": "upstox_websocket_v3",
            "ltq": _safe_float(ltq),
            "ltt": _safe_float(ltt),
            "open": _safe_float(open_p),
            "high": _safe_float(high_p),
            "low": _safe_float(low_p),
            "close": _safe_float(close_p),
            "prev_close": _safe_float(cp),
            "vwap": _safe_float(vwap_p),
            "change": _safe_float(change if change is not None else None),
            "change_percent": _safe_float(change_percent if change_percent is not None else None),
            "raw_payload": raw_payload,
            "raw_websocket_payload": raw_websocket_payload
        }
        records.append(record)
        
    return records, missing_count


UPSTOX_CAPTURE_SCHEMA = pa.schema([
    ("ts_recv", pa.float64()),
    ("ts_feed", pa.float64()),
    ("token", pa.string()),
    ("symbol", pa.string()),
    ("exchange", pa.string()),
    ("ltp", pa.float64()),
    ("bid", pa.float64()),
    ("ask", pa.float64()),
    ("vol", pa.float64()),
    ("oi", pa.float64()),
    ("depth", pa.string()),
    ("quote_age_sec", pa.float64()),
    ("quote_source", pa.string()),
    ("ltq", pa.float64()),
    ("ltt", pa.float64()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("prev_close", pa.float64()),
    ("vwap", pa.float64()),
    ("change", pa.float64()),
    ("change_percent", pa.float64()),
    ("raw_payload", pa.string()),
    ("raw_websocket_payload", pa.string())
])

def main():
    logger.info("Initializing Upstox read-only market data capture with Hardened FULL payload upgrade...")
    
    API_KEY = os.getenv("UPSTOX_API_KEY", "").strip()
    ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    
    if not ACCESS_TOKEN:
        logger.error("Missing UPSTOX_ACCESS_TOKEN. Exiting (Fail-closed).")
        sys.exit(1)

    try:
        target_keys, instrument_hash, resolution_errors = get_target_keys(ACCESS_TOKEN)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
        
    logger.info(f"Subscribing to {len(target_keys)} instrument keys for full tick collection.")

    date_str = datetime.now().strftime("%Y%m%d")
    out_dir = ROOT / ".runtime" / "market_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"upstox_full_ticks_{date_str}.parquet"

    writer = pq.ParquetWriter(out_file, UPSTOX_CAPTURE_SCHEMA)
    tick_buffer = []
    BUFFER_SIZE = 5000
    
    total_rows = 0
    start_time = datetime.now()
    feed_health = "UNKNOWN"
    last_msg_time = time.time()
    reconnect_count = 0
    dropped_message_count = 0
    missing_field_count = 0
    
    buffer_lock = threading.Lock()

    def flush_buffer():
        nonlocal total_rows
        with buffer_lock:
            if not tick_buffer:
                return
            try:
                df = pd.DataFrame(tick_buffer)
                table = pa.Table.from_pandas(df, schema=schema)
                writer.write_table(table)
                total_rows += len(tick_buffer)
                tick_buffer.clear()
                logger.info(f"Flushed {len(df)} ticks to parquet. Total: {total_rows}")
            except Exception as e:
                logger.error(f"Error flushing parquet (Fail-closed triggered): {e}")
                # Clean exit on serialization error to avoid corrupting records
                write_manifest("UPSTOX_CAPTURE_SERIALIZATION_FAIL")
                os._exit(1)

    def write_manifest(status="UPSTOX_CAPTURE_SUCCEEDED"):
        manifest_dir = ROOT / ".runtime" / "market_data" / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source_root": str(ROOT),
            "capture_date": date_str,
            "capture_start_ts": start_time.isoformat(),
            "capture_end_ts": datetime.now().isoformat(),
            "market_open_session": True,
            "data_source": "upstox_websocket_v3",
            "schema_version": "1.2.0",
            "feed_version": "upstox_v3",
            "instrument_master_hash": instrument_hash,
            "source_system": socket.gethostname(),
            "row_count": total_rows,
            "unique_symbols": len(target_keys),
            "reconnect_count": reconnect_count,
            "dropped_message_count": dropped_message_count,
            "missing_field_count": missing_field_count,
            "resolution_errors": resolution_errors,
            "capture_status": status,
            "feed_health_truth": feed_health
        }
        with open(manifest_dir / f"upstox_capture_manifest_{date_str}.json", "w") as f:
            json.dump(manifest, f, indent=2)

    streamer = upstox_client.MarketDataStreamerV3(
        upstox_client.Configuration(), 
        client_id="capture_agent", 
        access_token=ACCESS_TOKEN
    )
    
    stop_time = datetime_time(15, 35)

    def on_message(msg):
        nonlocal last_msg_time, feed_health, dropped_message_count, missing_field_count
        ts_recv = time.time()
        last_msg_time = ts_recv
        feed_health = "HEALTHY"
        
        now = datetime.now()
        if now.time() >= stop_time:
            logger.info("Market close reached. Shutting down tick collector.")
            flush_buffer()
            write_manifest()
            try:
                writer.close()
                streamer.disconnect()
            except:
                pass
            os._exit(0)
            
        try:
            records, m_count = parse_market_message(msg, target_keys, ts_recv)
            if not records and not isinstance(msg, dict):
                dropped_message_count += 1
                return
                
            with buffer_lock:
                missing_field_count += m_count
                tick_buffer.extend(records)
                
                if len(tick_buffer) >= BUFFER_SIZE:
                    flush_buffer()
                    
        except Exception as e:
            logger.error(f"Error executing message callback: {e}")
            dropped_message_count += 1

    def on_open():
        logger.info("Connected to Upstox WebSocket (Full Mode).")
        streamer.subscribe(list(target_keys.keys()), streamer.Mode.full)

    def on_close(code, reason):
        logger.warning(f"WebSocket closed: {code} - {reason}")
        nonlocal feed_health
        feed_health = "DISCONNECTED"

    def on_error(error):
        logger.error(f"WebSocket error: {error}")
        nonlocal feed_health
        feed_health = "ERROR"

    streamer.on("message", on_message)
    streamer.on("open", on_open)
    streamer.on("close", on_close)
    streamer.on("error", on_error)

    def handle_sigint(*args):
        logger.info("Shutting down collector due to signal...")
        flush_buffer()
        write_manifest("UPSTOX_CAPTURE_INTERRUPTED")
        try:
            writer.close()
            streamer.disconnect()
        except:
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    def watchdog():
        nonlocal last_msg_time, feed_health, reconnect_count
        while True:
            time.sleep(30)
            now = time.time()
            if now - last_msg_time > 30:
                logger.warning("Watchdog alert: No tick data received for 30 seconds.")
                feed_health = "STALE"
                try:
                    streamer.disconnect()
                except:
                    pass
                try:
                    logger.info("Reconnecting...")
                    streamer.connect()
                    reconnect_count += 1
                except Exception as e:
                    logger.error(f"Reconnect failed: {e}")
                last_msg_time = time.time()

    logger.info("Starting Upstox MarketDataStreamerV3 loop...")
    t = threading.Thread(target=watchdog, daemon=True)
    t.start()
    
    streamer.connect()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
