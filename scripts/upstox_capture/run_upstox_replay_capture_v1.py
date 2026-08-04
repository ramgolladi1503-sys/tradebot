#!/usr/bin/env python3
import os
import sys
import time
import signal
import logging
import argparse
from pathlib import Path
from datetime import datetime, time as datetime_time, timezone
from google.protobuf import json_format
import json

import upstox_client
from upstox_client import MarketDataStreamerV3
sys.path.append(str(Path(__file__).parent.parent.parent))

from core.upstox_capture.authorization import preflight_auth
from core.upstox_capture.subscription_planner import load_instrument_master, build_subscription_plan
from core.upstox_capture.raw_writer import RawWriter
from core.upstox_capture.normalized_writer import NormalizedWriter
from core.upstox_capture.lifecycle_ledger import LifecycleLedger
from core.upstox_capture.quality_monitor import QualityMonitor
from core.upstox_capture.protobuf_decoder import decode_feed_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("run_upstox_capture")

class ReplayQualityStreamer(MarketDataStreamerV3):
    def __init__(self, raw_callback, lifecycle_ledger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_callback = raw_callback
        self.ledger = lifecycle_ledger
        self.reconnect_generation = 0

    def handle_message(self, ws, message):
        # 1. Capture raw message bytes
        if self.raw_callback:
            try:
                self.raw_callback(message)
            except Exception as e:
                logger.error(f"Failed to record raw frame: {e}")

        # 2. Emits normal message dict
        try:
            decoded_data = self.decode_protobuf(message)
            data_dict = json_format.MessageToDict(decoded_data)
            self.emit(self.Event["MESSAGE"], data_dict)
        except Exception as e:
            logger.error(f"Failed to decode Protobuf: {e}")
            self.emit(self.Event["ERROR"], f"Protobuf decode error: {e}")

    def handle_open(self, ws):
        self.ledger.log_connection_event("OPEN", "WebSocket connected", self.reconnect_generation)
        super().handle_open(ws)

    def handle_close(self, ws, code, msg):
        self.ledger.log_connection_event("CLOSE", f"Code: {code}, Msg: {msg}", self.reconnect_generation)
        self.reconnect_generation += 1
        super().handle_close(ws, code, msg)

    def handle_error(self, ws, error):
        self.ledger.log_connection_event("ERROR", f"Err: {error}", self.reconnect_generation)
        super().handle_error(ws, error)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-only", action="store_true", help="Perform preflight only")
    args = parser.parse_args()

    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        logger.error("UPSTOX_ACCESS_TOKEN not found in env.")
        sys.exit(1)

    if not preflight_auth(token):
        sys.exit(1)

    # 0. Refresh instrument master daily
    try:
        from scripts.capture_upstox_market_daily import fetch_bod_master
        fetch_bod_master()
    except Exception as e:
        logger.error(f"Failed to refresh BOD instrument master: {e}")

    # 1. Resolve Universe & Planner
    inst_master_path = Path("runtime/upstox_instruments/complete.json")
    date_str_dashed = datetime.now().strftime("%Y-%m-%d")
    run_id = datetime.now().strftime("%H%M%S")
    output_dir = Path("/Users/madhuram/tradebot/.runtime/market_data/upstox_replay_capture_v1") / date_str_dashed / run_id
    
    # Simple LTP fallback prices to build universe
    fallback_prices = {"NIFTY": 24500.0, "BANKNIFTY": 52200.0, "SENSEX": 80000.0}
    preplanned = Path(f"runtime/market_data/upstox/{datetime.now().strftime('%Y%m%d')}/full_day_replay_v1/subscription/subscription_plan_{datetime.now().strftime('%Y%m%d')}.json")
    if preplanned.exists():
        logger.info(f"Loading pre-planned subscription plan from {preplanned}")
        with open(preplanned, "r") as f:
            plan = json.load(f)
    else:
        plan = build_subscription_plan(inst_master_path, output_dir, fallback_prices)
    
    all_keys = plan["full"] + plan["ltpc"]
    if not all_keys:
        logger.error("No keys resolved for subscription. Exiting.")
        sys.exit(1)

    if args.auth_only:
        logger.info("Preflight complete in auth-only mode. Exiting.")
        sys.exit(0)

    # Wait for connect time (09:00 IST)
    now = datetime.now()
    connect_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now < connect_time:
        wait_sec = (connect_time - now).total_seconds()
        logger.info(f"Waiting {wait_sec:.1f}s until 09:00 IST to connect...")
        time.sleep(wait_sec)

    # Initialize ledgers and writers
    ledger = LifecycleLedger(output_dir)
    raw_writer_a = RawWriter(output_dir, connection_id="conn_a")
    normalized_writer = NormalizedWriter(output_dir, run_id)
    quality_monitor = QualityMonitor(output_dir)

    msg_count = 0
    byte_count = 0
    decode_latencies = []
    local_sequence = 1

    def raw_callback(message_bytes: bytes):
        nonlocal byte_count
        byte_count += len(message_bytes)
        try:
            # Quick validation check (can we decode?)
            decode_feed_response(message_bytes)
            raw_writer_a.write_frame(message_bytes, message_class="FeedResponse", decode_success=True)
        except Exception:
            raw_writer_a.write_frame(message_bytes, message_class="FeedResponse", decode_success=False)

    def on_market_update(message):
        nonlocal msg_count, local_sequence
        msg_count += 1
        
        start_decode = time.perf_counter()
        try:
            feeds = message.get("feeds", message) if isinstance(message, dict) else {}
            for key, data in feeds.items():
                if not isinstance(data, dict):
                    continue

                ff = data.get("fullFeed", {})
                market_ff = ff.get("marketFF", ff.get("indexFF", {}))
                
                ltpc = market_ff.get("ltpc", {})
                ltp = ltpc.get("ltp")
                if ltp is None and "cp" in ltpc:
                    ltp = ltpc.get("cp")

                # Extract depth
                market_level = market_ff.get("marketLevel", {})
                bid_ask_quote = market_level.get("bidAskQuote", [])
                
                bids = []
                asks = []
                if bid_ask_quote and isinstance(bid_ask_quote, list):
                    for q in bid_ask_quote[:5]:
                        if isinstance(q, dict):
                            bids.append((q.get("bidP"), q.get("bidQ")))
                            asks.append((q.get("askP"), q.get("askQ")))

                # Option Greeks
                option_greeks = market_ff.get("optionGreeks", {})
                
                # Assemble provider-neutral normalized record
                record = {
                    "schema_version": "1.0",
                    "capture_run_id": run_id,
                    "provider": "upstox",
                    "feed_version": "v3",
                    "connection_id": "conn_a",
                    "subscription_lane": "broad" if key in plan["ltpc"] else "critical",
                    "subscription_mode": "ltpc" if key in plan["ltpc"] else "full",
                    "instrument_key": key,
                    "tradingsymbol": data.get("trading_symbol") or key,
                    "exchange_token": market_ff.get("exchange_token") or key.split("|")[-1],
                    "ltp": float(ltp) if ltp is not None else None,
                    "volume": int(market_ff.get("volume", 0)) if market_ff.get("volume") else None,
                    "open_interest": int(market_ff.get("oi", 0)) if market_ff.get("oi") else None,
                    "receive_wall_ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "receive_monotonic_ns": time.monotonic_ns(),
                    "local_sequence": local_sequence,
                    "reconnect_generation": streamer.reconnect_generation,
                    "delta": float(option_greeks.get("delta")) if option_greeks.get("delta") is not None else None,
                    "gamma": float(option_greeks.get("gamma")) if option_greeks.get("gamma") is not None else None,
                    "theta": float(option_greeks.get("theta")) if option_greeks.get("theta") is not None else None,
                    "vega": float(option_greeks.get("vega")) if option_greeks.get("vega") is not None else None,
                    "implied_volatility": float(market_ff.get("iv")) if market_ff.get("iv") is not None else None,
                }

                # Add L2 Depth slots
                for i in range(1, 6):
                    bp = bids[i-1][0] if i <= len(bids) else None
                    bq = bids[i-1][1] if i <= len(bids) else None
                    ap = asks[i-1][0] if i <= len(asks) else None
                    aq = asks[i-1][1] if i <= len(asks) else None
                    record[f"bid_price_{i}"] = float(bp) if bp is not None else None
                    record[f"bid_quantity_{i}"] = int(bq) if bq is not None else None
                    record[f"ask_price_{i}"] = float(ap) if ap is not None else None
                    record[f"ask_quantity_{i}"] = int(aq) if aq is not None else None

                normalized_writer.write_record(record)
                local_sequence += 1

            decode_latencies.append(time.perf_counter() - start_decode)
        except Exception as e:
            logger.error(f"Failed parsing market update: {e}")

    # Initialize subclassed streamer
    api_client = upstox_client.ApiClient(upstox_client.Configuration())
    api_client.configuration.access_token = token
    
    streamer = ReplayQualityStreamer(
        raw_callback=raw_callback,
        lifecycle_ledger=ledger,
        api_client=api_client,
        instrumentKeys=plan["full"],  # Start subscribing to critical full lane
        mode="full"
    )

    logger.info("Connecting ReplayQualityStreamer...")
    streamer.on("message", on_market_update)
    streamer.connect()

    running = True

    def handle_sigint(*args):
        nonlocal running
        logger.info("Shutdown signal received. Finalizing...")
        running = False
        streamer.disconnect()
        raw_writer_a.close()
        normalized_writer.flush_all()
        logger.info("Shutdown finalized.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    stop_time = datetime_time(15, 35)

    try:
        while running:
            time.sleep(1)
            # Periodic flush & quality checks
            normalized_writer.check_periodic_flush()
            quality_monitor.record_metrics(msg_count, byte_count, queue_depth=0, decode_latencies=decode_latencies)
            decode_latencies.clear()

            if datetime.now().time() >= stop_time:
                logger.info("Market close time reached. Exiting loop.")
                break
    except KeyboardInterrupt:
        pass

    handle_sigint()

if __name__ == "__main__":
    main()
