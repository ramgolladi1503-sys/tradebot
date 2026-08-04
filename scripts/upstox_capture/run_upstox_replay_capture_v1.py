#!/usr/bin/env python3
"""Upstox V3 Market Session Capture Client.

Executes read-only market data capture, logs raw zstd frames, normalizes feed updates,
and records subscription lifecycle events.

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM: Does not claim any structural trading edge.
- NO_PROFITABILITY_CLAIM: No profitability is implied or guaranteed.
- NOT_A_KITE_LIVE_CERTIFICATION: Not a Zerodha Kite live trading certification.
"""

import sys
import os
import time
import json
import signal
import argparse
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone

from google.protobuf import json_format
import upstox_client
from upstox_client import MarketDataStreamerV3
from core.upstox_capture.authorization import preflight_auth
from core.upstox_capture.raw_writer import RawWriter
from core.upstox_capture.normalized_writer import NormalizedWriter
from core.upstox_capture.protobuf_decoder import decode_feed_response
from core.upstox_capture.lifecycle_ledger import LifecycleLedger

class ReplayQualityStreamer(MarketDataStreamerV3):
    def __init__(self, raw_callback, lifecycle_ledger, log_subscription_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_callback = raw_callback
        self.ledger = lifecycle_ledger
        self.log_subscription_event = log_subscription_callback
        self.reconnect_generation = 0

    def subscribe(self, keys, mode):
        for k in keys:
            self.log_subscription_event("SUBSCRIBE_REQUEST", k, mode)
        super().subscribe(keys, mode)

    def handle_message(self, ws, message):
        if self.raw_callback:
            try:
                self.raw_callback(message)
            except Exception as e:
                logger.error(f"Failed to record raw frame: {e}")
        try:
            decoded_data = self.decode_protobuf(message)
            data_dict = json_format.MessageToDict(decoded_data)
            self.emit(self.Event["MESSAGE"], data_dict)
        except Exception as e:
            logger.error(f"Failed to decode Protobuf: {e}")
            self.emit(self.Event["ERROR"], f"Protobuf decode error: {e}")

    def handle_open(self, ws):
        self.ledger.log_connection_event("OPEN", "WebSocket connected", self.reconnect_generation)
        self.log_subscription_event("CONNECT", "ws_conn", "OPEN")
        super().handle_open(ws)

    def handle_close(self, ws, code, msg):
        self.ledger.log_connection_event("CLOSE", f"Code: {code}, Msg: {msg}", self.reconnect_generation)
        self.log_subscription_event("DISCONNECT", "ws_conn", f"CLOSE_CODE_{code}")
        self.reconnect_generation += 1
        super().handle_close(ws, code, msg)

    def handle_error(self, ws, error):
        self.ledger.log_connection_event("ERROR", f"Err: {error}", self.reconnect_generation)
        self.log_subscription_event("ERROR", "ws_conn", str(error))
        super().handle_error(ws, error)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("run_upstox_replay_capture")

def calculate_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def verify_premarket_plan(evidence_root: Path) -> tuple[dict, dict]:
    sub_dir = evidence_root / "subscription"
    manifest_path = sub_dir / "premarket_manifest.json"
    plan_path = sub_dir / "universe_plan.json"

    if not manifest_path.exists() or not plan_path.exists():
        raise RuntimeError(f"Premarket plan missing in {sub_dir}. Run prepare_premarket_data.py first.")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    with open(plan_path, "r") as f:
        plan = json.load(f)

    # Verify Universe Hash Consistency
    curr_univ_hash = calculate_sha256(plan_path)
    if manifest.get("universe_sha256") != curr_univ_hash:
        raise RuntimeError(f"Universe plan hash mismatch: {manifest.get('universe_sha256')} != {curr_univ_hash}")

    # Verify Master Hash Consistency
    master_path = evidence_root / "upstox_instruments" / "complete.json"
    if master_path.exists():
        curr_master_hash = calculate_sha256(master_path)
        if manifest.get("instrument_master_sha256") != curr_master_hash:
            raise RuntimeError("Instrument master hash mismatch with premarket manifest.")

    logger.info(f"Pmarket plan verified: Session {manifest.get('session_date')}, Spot {manifest.get('spot_price')}")
    return manifest, plan

def parse_args():
    parser = argparse.ArgumentParser(description="Upstox V3 Market Capture Execution")
    parser.add_argument("--session-date", help="Session date in YYYYMMDD format")
    parser.add_argument("--auth-only", action="store_true", help="Perform auth preflight only")
    return parser.parse_args()

def main():
    args = parse_args()
    session_date = args.session_date or datetime.now(timezone.utc).strftime("%Y%m%d")

    worktree_root = Path(__file__).resolve().parents[2]
    evidence_root = worktree_root / "runtime" / "market_data" / "upstox" / session_date / "full_day_replay_v1"

    # Preflight Auth Check
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        logger.error("UPSTOX_ACCESS_TOKEN not found in env.")
        sys.exit(1)

    if not preflight_auth(token):
        sys.exit(1)

    if args.auth_only:
        logger.info("Preflight authorization succeeded (--auth-only mode).")
        sys.exit(0)

    # Verify Premarket Plan before connection
    try:
        manifest, plan = verify_premarket_plan(evidence_root)
    except Exception as e:
        logger.error(f"Pre-connection plan verification failed: {e}")
        sys.exit(1)

    # Master index lookup
    master_json_path = evidence_root / "upstox_instruments" / "complete.json"
    master_dict = {}
    if master_json_path.exists():
        with open(master_json_path, "r") as f:
            m_list = json.load(f)
            if isinstance(m_list, dict):
                m_list = list(m_list.values())
            for item in m_list:
                k = item.get("instrument_key")
                if k:
                    master_dict[k] = item

    run_id = f"upstox_{session_date}_{int(time.time())}"

    # Output directories
    raw_dir = evidence_root / "raw"
    normalized_dir = evidence_root / "normalized"
    sub_dir = evidence_root / "subscription"
    ledger_path = evidence_root / "lifecycle_ledger.jsonl"
    events_log_path = sub_dir / "subscription_events.jsonl"

    ledger = LifecycleLedger(ledger_path)
    ledger.log_event("SESSION_START", {"run_id": run_id, "session_date": session_date})

    raw_writer = RawWriter(raw_dir, run_id=run_id)
    norm_writer = NormalizedWriter(evidence_root, run_id=run_id)

    full_keys = set(plan.get("full", []))
    ltpc_keys = set(plan.get("ltpc", []))
    all_requested_keys = full_keys | ltpc_keys
    observed_keys = set()
    local_sequence = 0

    logger.info("Raw provenance tracking: File offsets unavailable in live streaming mode (set to null).")

    def log_sub_event(event_type: str, instrument_key: str, details: str = ""):
        evt = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "instrument_key": instrument_key,
            "details": details
        }
        with open(events_log_path, "a") as f:
            f.write(json.dumps(evt) + "\n")

    def raw_callback(binary_data: bytes):
        nonlocal local_sequence
        local_sequence += 1

        # 1. Write raw zstd compressed payload
        raw_writer.write_frame(binary_data)

        # 2. Decode protobuf and normalize
        try:
            feed_dict = decode_feed_response(binary_data)
            feeds = feed_dict.get("feeds", {})

            for key, data in feeds.items():
                if key not in observed_keys:
                    observed_keys.add(key)
                    log_sub_event("FIRST_EVENT_OBSERVED", key, "ACTIVE")

                meta = master_dict.get(key, {})
                ff = data.get("fullFeed", {})
                market_ff = ff.get("marketFF", ff.get("indexFF", {}))
                if not market_ff:
                    market_ff = ff.get("marketFf", ff.get("indexFf", {}))

                ltpc = market_ff.get("ltpc", {})
                ltp = ltpc.get("ltp") if ltpc.get("ltp") is not None else ltpc.get("cp")

                option_greeks = market_ff.get("optionGreeks", {})
                iv = market_ff.get("iv") or option_greeks.get("iv")

                record = {
                    "schema_version": "1.0",
                    "capture_run_id": run_id,
                    "provider": "upstox",
                    "feed_version": "v3",
                    "connection_id": "conn_active",
                    "subscription_lane": "critical" if key in full_keys else "broad",
                    "subscription_mode": "full" if key in full_keys else "ltpc",
                    "instrument_key": key,
                    "tradingsymbol": meta.get("trading_symbol") or meta.get("tradingsymbol") or key,
                    "exchange_token": meta.get("exchange_token") or key.split("|")[-1],
                    "exchange": meta.get("exchange"),
                    "segment": meta.get("segment"),
                    "instrument_type": meta.get("instrument_type"),
                    "underlying_symbol": meta.get("underlying_symbol"),
                    "expiry": str(meta.get("expiry")) if meta.get("expiry") is not None else None,
                    "strike": float(meta.get("strike_price")) if meta.get("strike_price") is not None else None,
                    "lot_size": int(meta.get("lot_size")) if meta.get("lot_size") is not None else None,
                    "tick_size": float(meta.get("tick_size")) if meta.get("tick_size") is not None else None,
                    "ltp": float(ltp) if ltp is not None else None,
                    "last_traded_quantity": int(ltpc.get("ltq")) if ltpc.get("ltq") is not None else None,
                    "close_price": float(ltpc.get("cp")) if ltpc.get("cp") is not None else None,
                    "open": float(market_ff.get("open")) if market_ff.get("open") is not None else None,
                    "high": float(market_ff.get("high")) if market_ff.get("high") is not None else None,
                    "low": float(market_ff.get("low")) if market_ff.get("low") is not None else None,
                    "volume": int(market_ff.get("vtt")) if market_ff.get("vtt") is not None else (int(market_ff.get("volume")) if market_ff.get("volume") is not None else None),
                    "average_traded_price": float(market_ff.get("atp")) if market_ff.get("atp") is not None else None,
                    "open_interest": int(market_ff.get("oi")) if market_ff.get("oi") is not None else None,
                    "previous_open_interest": int(market_ff.get("poi")) if market_ff.get("poi") is not None else None,
                    "implied_volatility": float(iv) if iv is not None else None,
                    "total_buy_quantity": int(market_ff.get("tbq")) if market_ff.get("tbq") is not None else None,
                    "total_sell_quantity": int(market_ff.get("tsq")) if market_ff.get("tsq") is not None else None,
                    "delta": float(option_greeks.get("delta")) if option_greeks.get("delta") is not None else None,
                    "gamma": float(option_greeks.get("gamma")) if option_greeks.get("gamma") is not None else None,
                    "theta": float(option_greeks.get("theta")) if option_greeks.get("theta") is not None else None,
                    "vega": float(option_greeks.get("vega")) if option_greeks.get("vega") is not None else None,
                    "rho": float(option_greeks.get("rho")) if option_greeks.get("rho") is not None else None,
                    "market_status": market_ff.get("marketStatus") or market_ff.get("market_status"),

                    "source_exchange_ts": int(ltpc.get("ltt")) if ltpc.get("ltt") is not None else None,
                    "provider_current_ts": int(feed_dict.get("currentTs")) if feed_dict.get("currentTs") is not None else None,
                    "provider_last_trade_ts": int(ltpc.get("ltt")) if ltpc.get("ltt") is not None else None,
                    "receive_wall_ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "receive_monotonic_ns": time.monotonic_ns(),
                    "local_sequence": local_sequence,
                    "reconnect_generation": streamer.reconnect_generation if 'streamer' in locals() else 0,

                    "raw_chunk_id": None,
                    "raw_frame_offset": None,
                    "raw_frame_sha256": None
                }
                norm_writer.write_record(record)
        except Exception as e:
            logger.error(f"Error decoding raw frame: {e}")

    # Build Streamer
    api_client = upstox_client.ApiClient(upstox_client.Configuration())
    api_client.configuration.access_token = token
    streamer = ReplayQualityStreamer(
        raw_callback=raw_callback,
        lifecycle_ledger=ledger,
        log_subscription_callback=log_sub_event,
        api_client=api_client,
        instrumentKeys=list(plan.get("full", [])),
        mode="full"
    )

    def shutdown(signum=None, frame=None):
        logger.info("Initiating graceful shutdown...")
        streamer.disconnect()
        raw_writer.close()
        norm_writer.close()

        # Final Reconciliation
        unobserved = all_requested_keys - observed_keys
        for k in unobserved:
            log_sub_event("NEVER_OBSERVED", k, "FAIL")

        reconcile_report = norm_writer.get_reconciliation_report()
        logger.info(f"Writer durability report: {json.dumps(reconcile_report)}")

        # Mandatory instrument check
        mandatory_unobserved = [
            k for k in unobserved
            if "Nifty" in k or "FUT" in master_dict.get(k, {}).get("instrument_type", "") or master_dict.get(k, {}).get("instrument_type") in ["CE", "PE"]
        ]
        if mandatory_unobserved:
            logger.error(f"SESSION REJECTED: Mandatory instruments never observed ({len(mandatory_unobserved)} missing).")
            ledger.log_event("SESSION_REJECTED", {"unobserved": mandatory_unobserved})
            sys.exit(1)

        ledger.log_event("SESSION_END", {"reconciliation": reconcile_report})
        logger.info("Capture session shut down cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log_sub_event("CONNECT", "ALL", "INITIATED")
    streamer.connect()

    # Subscribe full and ltpc lanes
    if plan.get("full"):
        log_sub_event("SUBSCRIBE_SENT", ",".join(plan["full"]), "full")
        streamer.subscribe(plan["full"], mode="full")

    if plan.get("ltpc"):
        log_sub_event("SUBSCRIBE_SENT", ",".join(plan["ltpc"]), "ltpc")
        streamer.subscribe(plan["ltpc"], mode="ltpc")

    log_sub_event("MODE_ASSIGNED", "FULL_AND_LTPC", "ACTIVE")

    try:
        while True:
            time.sleep(1)
            norm_writer.check_periodic_flush()
    except Exception as e:
        logger.error(f"Runtime stream error: {e}")
        shutdown()

if __name__ == "__main__":
    main()
