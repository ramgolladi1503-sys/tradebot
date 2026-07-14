#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, time as datetime_time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
import requests

# We try to import Upstox SDK
try:
    import upstox_client
    from upstox_client import MarketDataStreamerV3

    UPSTOX_AVAILABLE = True
except ImportError:
    UPSTOX_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("capture_upstox_daily")


def fetch_bod_master():
    """Refresh Upstox’s BOD JSON instrument master after approximately 06:00 IST."""  # noqa: E501
    now = datetime.now()
    cutoff = now.replace(hour=6, minute=0, second=0, microsecond=0)

    out_dir = Path("runtime/upstox_instruments")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "complete.json"

    if out_path.exists():
        mtime = datetime.fromtimestamp(out_path.stat().st_mtime)
        if mtime > cutoff:
            logger.info(
                "BOD JSON master already refreshed today after 06:00 IST."
            )
            return True

    logger.info("Refreshing Upstox BOD JSON instrument master...")
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"  # noqa: E501
    try:
        import urllib.request
        import gzip

        req = urllib.request.Request(
            url, headers={"User-Agent": "tradebot_local/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        with open(out_path.with_suffix(".json.gz"), "wb") as f:
            f.write(data)

        with gzip.open(
            out_path.with_suffix(".json.gz"), "rt", encoding="utf-8"
        ) as f:
            jdata = json.load(f)

        # Convert dict to list if needed
        if isinstance(jdata, dict):
            jdata = list(jdata.values())

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(jdata, f)

        logger.info(
            f"Successfully refreshed BOD JSON. Saved {len(jdata)} instruments."
        )
        return True
    except Exception as e:
        logger.error(f"Failed to fetch BOD master: {e}")
        return False


def preflight_auth(token):
    """Generate a fresh access token before the session and perform a harmless authorization preflight."""  # noqa: E501
    url = "https://api.upstox.com/v2/user/profile"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info("Preflight auth successful.")
            return True
        else:
            logger.error(
                f"Preflight auth failed. Status: {resp.status_code}, "
                f"Response: {resp.text}"
            )
            if "UDAPI1221" in resp.text:
                logger.error(
                    "=> UPSTOX IP WHITELIST ERROR: The API key does not allow "
                    "this machine's IP. Please whitelist this VPS/machine IP in "  # noqa: E501
                    "the Upstox Developer Console."
                )
            return False
    except Exception as e:
        logger.error(f"Preflight auth exception: {e}")
        return False


def _find_nearest_expiry(instruments, symbol_name):
    # filtered by symbol_name and expiry > today
    today = datetime.now().date()
    opts = [
        i
        for i in instruments
        if i.get("name") == symbol_name
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry")
    ]

    if not opts:
        return []

    valid = []
    for opt in opts:
        try:
            exp_date = datetime.strptime(opt["expiry"], "%Y-%m-%d").date()
            if exp_date >= today:
                opt["_exp_date"] = exp_date
                valid.append(opt)
        except BaseException:
            # maybe timestamp
            if isinstance(opt["expiry"], (int, float)):
                exp_date = datetime.fromtimestamp(opt["expiry"] / 1000).date()
                if exp_date >= today:
                    opt["_exp_date"] = exp_date
                    valid.append(opt)

    if not valid:
        return []

    valid.sort(key=lambda x: x["_exp_date"])
    nearest = valid[0]["_exp_date"]
    return [o for o in valid if o["_exp_date"] == nearest]


def _find_futures(instruments, symbol_name):
    today = datetime.now().date()
    futs = [
        i
        for i in instruments
        if i.get("name") == symbol_name and i.get("instrument_type") == "FUT"
    ]
    valid = []
    for fut in futs:
        try:
            exp_date = datetime.strptime(
                fut.get("expiry", ""), "%Y-%m-%d"
            ).date()
            if exp_date >= today:
                fut["_exp_date"] = exp_date
                valid.append(fut)
        except BaseException:
            pass
    valid.sort(key=lambda x: x["_exp_date"])
    # Return up to 2 (current and next)
    unique_expiries = sorted(list(set([x["_exp_date"] for x in valid])))
    if not unique_expiries:
        return []
    targets = unique_expiries[:2]
    return [x for x in valid if x["_exp_date"] in targets]


def resolve_instruments():
    """Resolve instruments safely and strictly fail-closed."""
    out_path = Path("runtime/upstox_instruments/complete.json")
    if not out_path.exists():
        logger.error("BOD JSON missing. Cannot resolve.")
        return None

    with open(out_path, "r", encoding="utf-8") as f:
        instruments = json.load(f)

    resolved_keys = set()

    # 1. NIFTY 50 spot + options + futures
    nifty_spot = [
        i
        for i in instruments
        if i.get("trading_symbol") == "NIFTY 50"
        and i.get("instrument_type") == "INDEX"
    ]
    if not nifty_spot:
        logger.error("Could not resolve NIFTY 50 spot")
        return None
    resolved_keys.add(nifty_spot[0]["instrument_key"])

    opts = _find_nearest_expiry(instruments, "NIFTY")
    if not opts:
        logger.error("Could not resolve NIFTY nearest options")
        return None
    for o in opts:
        resolved_keys.add(o["instrument_key"])

    futs = _find_futures(instruments, "NIFTY")
    for f in futs:
        resolved_keys.add(f["instrument_key"])

    # 2. NIFTY BANK spot + options + futures
    bank_spot = [
        i
        for i in instruments
        if i.get("trading_symbol") == "NIFTY BANK"
        and i.get("instrument_type") == "INDEX"
    ]
    if not bank_spot:
        logger.error("Could not resolve NIFTY BANK spot")
        return None
    resolved_keys.add(bank_spot[0]["instrument_key"])

    opts = _find_nearest_expiry(instruments, "BANKNIFTY")
    if not opts:
        logger.error("Could not resolve BANKNIFTY nearest options")
        return None
    for o in opts:
        resolved_keys.add(o["instrument_key"])

    futs = _find_futures(instruments, "BANKNIFTY")
    for f in futs:
        resolved_keys.add(f["instrument_key"])

    # 3. SENSEX spot + options
    sensex_spot = [
        i
        for i in instruments
        if i.get("trading_symbol") == "SENSEX"
        and i.get("instrument_type") == "INDEX"
    ]
    if not sensex_spot:
        logger.error("Could not resolve SENSEX spot")
        return None
    resolved_keys.add(sensex_spot[0]["instrument_key"])

    opts = _find_nearest_expiry(instruments, "SENSEX")
    if not opts:
        logger.error("Could not resolve SENSEX nearest options")
        return None
    for o in opts:
        resolved_keys.add(o["instrument_key"])

    # 4. India VIX
    vix_spot = [
        i
        for i in instruments
        if i.get("trading_symbol") == "INDIA VIX"
        and i.get("instrument_type") == "INDEX"
    ]
    if not vix_spot:
        logger.error("Could not resolve INDIA VIX")
        return None
    resolved_keys.add(vix_spot[0]["instrument_key"])

    logger.info(f"Successfully resolved {len(resolved_keys)} instrument keys.")
    return list(resolved_keys)


class DataCollector:
    def __init__(self, token, keys):
        self.token = token
        self.keys = keys
        if UPSTOX_AVAILABLE:
            self.streamer = MarketDataStreamerV3(
                upstox_client.ApiClient(upstox_client.Configuration()),
                list(keys),
                "full",
            )
            self.streamer.api_client.configuration.access_token = token
        else:
            self.streamer = None

        self.buffer = []
        self.raw_buffer = []
        self.msg_count = 0
        self.dropped_msg_count = 0
        self.parse_failures = 0
        self.reconnects = 0

        self.chunk_interval = 10  # 10 mins
        self.last_flush = time.time()
        self.date_str = datetime.now().strftime("%Y%m%d")
        self.out_dir = Path(f"runtime/market_data/upstox/{self.date_str}")
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.schema = pa.schema(
            [
                ("ts", pa.float64()),
                ("instrument_key", pa.string()),
                ("ltp", pa.float64()),
                ("bid_price", pa.float64()),
                ("ask_price", pa.float64()),
                ("delta", pa.float64()),
                ("theta", pa.float64()),
                ("gamma", pa.float64()),
                ("vega", pa.float64()),
                ("iv", pa.float64()),
                ("volume", pa.int64()),
                ("oi", pa.float64()),
            ]
        )

    def flush(self):
        if not self.buffer:
            return

        now_ts = int(time.time())
        df = pd.DataFrame(self.buffer)
        table = pa.Table.from_pandas(df, schema=self.schema)
        pq_path = self.out_dir / f"ticks_{now_ts}.parquet"
        pq.write_table(table, pq_path)

        logger.info(f"Flushed {len(self.buffer)} records to {pq_path}")
        self.buffer.clear()
        self.last_flush = time.time()

    def on_market_update(self, message):
        self.msg_count += 1
        # Check chunk interval
        if time.time() - self.last_flush >= self.chunk_interval * 60:
            self.flush()

        try:
            # We must parse the message payload correctly. Upstox returns
            # dictionary for V3
            for key, data in message.items():
                if isinstance(data, dict):
                    # parse
                    rec = {
                        "ts": time.time(),
                        "instrument_key": key,
                        "ltp": (
                            float(data.get("ltpc", {}).get("ltp", 0.0))
                            if data.get("ltpc")
                            else None
                        ),
                        "volume": (
                            int(
                                data.get("ff", {})
                                .get("market_ff", {})
                                .get("vtt", 0)
                            )
                            if data.get("ff")
                            else None
                        ),
                        "oi": (
                            float(
                                data.get("ff", {})
                                .get("market_ff", {})
                                .get("oi", 0.0)
                            )
                            if data.get("ff")
                            else None
                        ),
                    }

                    # Depth
                    depth = data.get("depth", {})
                    buy = depth.get("buy", [])
                    sell = depth.get("sell", [])
                    rec["bid_price"] = (
                        float(buy[0].get("price", 0.0)) if buy else None
                    )
                    rec["ask_price"] = (
                        float(sell[0].get("price", 0.0)) if sell else None
                    )

                    # Greeks
                    option_greeks = data.get("option_greeks", {})
                    rec["delta"] = (
                        float(option_greeks.get("delta", 0.0))
                        if option_greeks
                        else None
                    )
                    rec["theta"] = (
                        float(option_greeks.get("theta", 0.0))
                        if option_greeks
                        else None
                    )
                    rec["gamma"] = (
                        float(option_greeks.get("gamma", 0.0))
                        if option_greeks
                        else None
                    )
                    rec["vega"] = (
                        float(option_greeks.get("vega", 0.0))
                        if option_greeks
                        else None
                    )
                    rec["iv"] = (
                        float(option_greeks.get("iv", 0.0))
                        if option_greeks
                        else None
                    )

                    self.buffer.append(rec)
        except Exception:
            self.parse_failures += 1

    def on_error(self, error):
        logger.error(f"Upstox WebSocket error: {error}")
        self.reconnects += 1

    def on_close(self, code, reason):
        logger.warning(
            f"Upstox WebSocket closed (Code: {code}, Reason: {reason})."
        )
        self.reconnects += 1

    def finalize(self):
        self.flush()
        manifest = {
            "session_date": self.date_str,
            "total_messages": self.msg_count,
            "dropped_messages": self.dropped_msg_count,
            "parse_failures": self.parse_failures,
            "reconnects": self.reconnects,
            "coverage_keys": len(self.keys),
            "finalized_at": datetime.now().isoformat(),
        }
        with open(self.out_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Session finalized. {manifest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--auth-only", action="store_true", help="Perform preflight only"
    )
    args = parser.parse_args()

    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        logger.error("UPSTOX_ACCESS_TOKEN not found in env.")
        sys.exit(1)

    if not fetch_bod_master():
        sys.exit(1)

    if not preflight_auth(token):
        sys.exit(1)

    keys = resolve_instruments()
    if not keys:
        sys.exit(1)

    if args.auth_only:
        logger.info("Auth-only mode requested. Preflight successful. Exiting.")
        sys.exit(0)

    # Wait for connect time
    now = datetime.now()
    connect_time = now.replace(hour=9, minute=10, second=0, microsecond=0)
    if now < connect_time:
        wait_sec = (connect_time - now).total_seconds()
        logger.info(f"Waiting {wait_sec:.1f}s until 09:10 IST to connect...")
        time.sleep(wait_sec)

    collector = DataCollector(token, keys)

    if not UPSTOX_AVAILABLE:
        logger.error(
            "Upstox client not available (pip install upstox-python-sdk). Exiting."  # noqa: E501
        )
        sys.exit(1)

    logger.info("Starting V3 Full Market Data Streamer...")
    collector.streamer.on("message", collector.on_market_update)
    collector.streamer.on("error", collector.on_error)
    collector.streamer.on("close", collector.on_close)
    collector.streamer.connect()

    stop_time = datetime_time(15, 35)

    try:
        while True:
            time.sleep(1)
            now_time = datetime.now().time()
            if now_time >= stop_time:
                logger.info("Market close (15:35). Shutting down.")
                break
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")

    collector.streamer.close()
    collector.finalize()


if __name__ == "__main__":
    main()
