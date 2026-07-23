#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, time as datetime_time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from core.upstox_v3_feed_parser import (
    UpstoxV3ParseError,
    assess_capture_quality,
    parse_upstox_v3_message,
)

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

MIN_ACTIVE_FO_DEPTH_COVERAGE_RATIO = 0.50
MIN_VALID_DEPTH_RECORDS_PER_INSTRUMENT = 1
DEPTH_CANARY_MIN_FO_RECORDS = 100


def fetch_bod_master() -> bool:
    """Refresh Upstox's BOD JSON instrument master after approximately 06:00 IST."""
    now = datetime.now()
    cutoff = now.replace(hour=6, minute=0, second=0, microsecond=0)

    out_dir = Path("runtime/upstox_instruments")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "complete.json"

    if out_path.exists():
        mtime = datetime.fromtimestamp(out_path.stat().st_mtime)
        if mtime > cutoff:
            logger.info("BOD JSON master already refreshed today after 06:00 IST.")
            return True

    logger.info("Refreshing Upstox BOD JSON instrument master...")
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "tradebot_local/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()

        compressed_path = out_path.with_suffix(".json.gz")
        compressed_path.write_bytes(data)
        with gzip.open(compressed_path, "rt", encoding="utf-8") as handle:
            instruments = json.load(handle)
        if isinstance(instruments, dict):
            instruments = list(instruments.values())
        out_path.write_text(json.dumps(instruments), encoding="utf-8")
        logger.info("Successfully refreshed BOD JSON. Saved %s instruments.", len(instruments))
        return True
    except Exception as exc:
        logger.error("Failed to fetch BOD master: %s", exc)
        return False


def preflight_auth(token: str) -> bool:
    """Perform a harmless authorization preflight before subscribing."""
    url = "https://api.upstox.com/v2/user/profile"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info("Preflight auth successful.")
            return True
        logger.error(
            "Preflight auth failed. Status: %s, Response: %s",
            response.status_code,
            response.text,
        )
        if "UDAPI1221" in response.text:
            logger.error(
                "UPSTOX IP WHITELIST ERROR: whitelist this machine in the Upstox Developer Console."
            )
        return False
    except Exception as exc:
        logger.error("Preflight auth exception: %s", exc)
        return False


def _expiry_date(value: Any):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0).date()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _find_nearest_expiry(instruments: list[dict[str, Any]], symbol_name: str) -> list[dict[str, Any]]:
    today = datetime.now().date()
    valid: list[dict[str, Any]] = []
    for instrument in instruments:
        if instrument.get("name") != symbol_name:
            continue
        if instrument.get("instrument_type") not in {"CE", "PE"}:
            continue
        expiry = _expiry_date(instrument.get("expiry"))
        if expiry is None or expiry < today:
            continue
        row = dict(instrument)
        row["_exp_date"] = expiry
        valid.append(row)
    if not valid:
        return []
    nearest = min(row["_exp_date"] for row in valid)
    return [row for row in valid if row["_exp_date"] == nearest]


def _find_futures(instruments: list[dict[str, Any]], symbol_name: str) -> list[dict[str, Any]]:
    today = datetime.now().date()
    valid: list[dict[str, Any]] = []
    for instrument in instruments:
        if instrument.get("name") != symbol_name:
            continue
        if instrument.get("instrument_type") != "FUT":
            continue
        expiry = _expiry_date(instrument.get("expiry"))
        if expiry is None or expiry < today:
            continue
        row = dict(instrument)
        row["_exp_date"] = expiry
        valid.append(row)
    expiries = sorted({row["_exp_date"] for row in valid})[:2]
    return [row for row in valid if row["_exp_date"] in expiries]


def resolve_instruments() -> list[str] | None:
    """Resolve index, nearest-expiry option and current/next future instrument keys."""
    out_path = Path("runtime/upstox_instruments/complete.json")
    if not out_path.exists():
        logger.error("BOD JSON missing. Cannot resolve instruments.")
        return None
    instruments = json.loads(out_path.read_text(encoding="utf-8"))

    resolved: set[str] = set()
    spot_contracts = (
        ("NIFTY 50", "NIFTY"),
        ("NIFTY BANK", "BANKNIFTY"),
        ("SENSEX", "SENSEX"),
    )
    for trading_symbol, derivative_name in spot_contracts:
        spot = [
            row
            for row in instruments
            if row.get("trading_symbol") == trading_symbol
            and row.get("instrument_type") == "INDEX"
        ]
        if not spot:
            logger.error("Could not resolve %s spot", trading_symbol)
            return None
        resolved.add(str(spot[0]["instrument_key"]))

        options = _find_nearest_expiry(instruments, derivative_name)
        if not options:
            logger.error("Could not resolve %s nearest options", derivative_name)
            return None
        resolved.update(str(row["instrument_key"]) for row in options)
        if derivative_name in {"NIFTY", "BANKNIFTY"}:
            resolved.update(
                str(row["instrument_key"])
                for row in _find_futures(instruments, derivative_name)
            )

    vix = [
        row
        for row in instruments
        if row.get("trading_symbol") == "INDIA VIX"
        and row.get("instrument_type") == "INDEX"
    ]
    if not vix:
        logger.error("Could not resolve INDIA VIX")
        return None
    resolved.add(str(vix[0]["instrument_key"]))

    logger.info("Successfully resolved %s instrument keys.", len(resolved))
    return sorted(resolved)


class DataCollector:
    def __init__(self, token: str, keys: list[str]):
        self.token = token
        self.keys = sorted({str(key) for key in keys})
        if UPSTOX_AVAILABLE:
            configuration = upstox_client.Configuration()
            configuration.access_token = token
            api_client = upstox_client.ApiClient(configuration)
            self.streamer = MarketDataStreamerV3(api_client, self.keys, "full")
        else:
            self.streamer = None

        self.buffer: list[dict[str, Any]] = []
        self.msg_count = 0
        self.control_message_count = 0
        self.record_count = 0
        self.records_written = 0
        self.dropped_msg_count = 0
        self.parse_failures = 0
        self.persistence_failures = 0
        self.reconnects = 0
        self.last_parse_error: str | None = None
        self.record_counts_by_instrument: Counter[str] = Counter()
        self.valid_depth_counts_by_instrument: Counter[str] = Counter()
        self.depth_canary_warned = False

        self.chunk_interval_minutes = 10
        self.last_flush = time.time()
        self.date_str = datetime.now().strftime("%Y%m%d")
        self.out_dir = Path(f"runtime/market_data/upstox/{self.date_str}")
        self.out_dir.mkdir(parents=True, exist_ok=True)

        depth_level = pa.struct(
            [
                pa.field("bid_price", pa.float64()),
                pa.field("bid_quantity", pa.int64()),
                pa.field("ask_price", pa.float64()),
                pa.field("ask_quantity", pa.int64()),
            ]
        )
        self.schema = pa.schema(
            [
                ("ts", pa.float64()),
                ("source_ts_epoch_ms", pa.int64()),
                ("instrument_key", pa.string()),
                ("message_type", pa.string()),
                ("feed_kind", pa.string()),
                ("ltp", pa.float64()),
                ("bid_price", pa.float64()),
                ("ask_price", pa.float64()),
                ("bid_quantity", pa.int64()),
                ("ask_quantity", pa.int64()),
                ("depth", pa.list_(depth_level)),
                ("depth_level_count", pa.int32()),
                ("depth_valid", pa.bool_()),
                ("delta", pa.float64()),
                ("theta", pa.float64()),
                ("gamma", pa.float64()),
                ("vega", pa.float64()),
                ("rho", pa.float64()),
                ("iv", pa.float64()),
                ("volume", pa.int64()),
                ("oi", pa.float64()),
            ]
        )

    def flush(self) -> bool:
        if not self.buffer:
            return True
        now_ts = int(time.time())
        rows = list(self.buffer)
        try:
            frame = pd.DataFrame(rows)
            table = pa.Table.from_pandas(frame, schema=self.schema, preserve_index=False)
            parquet_path = self.out_dir / f"ticks_{now_ts}.parquet"
            pq.write_table(table, parquet_path)
            self.records_written += len(rows)
            self.buffer.clear()
            self.last_flush = time.time()
            logger.info("Flushed %s records to %s", len(rows), parquet_path)
            return True
        except Exception as exc:
            self.persistence_failures += 1
            logger.exception("Failed to persist Upstox V3 records: %s", exc)
            return False

    def _warn_on_empty_fo_depth(self) -> None:
        if self.depth_canary_warned:
            return
        fo_records = sum(
            count
            for key, count in self.record_counts_by_instrument.items()
            if key.split("|", 1)[0].upper().endswith("_FO")
        )
        valid_depth = sum(self.valid_depth_counts_by_instrument.values())
        if fo_records >= DEPTH_CANARY_MIN_FO_RECORDS and valid_depth == 0:
            self.depth_canary_warned = True
            logger.error(
                "DEPTH CAPTURE CANARY FAILED: %s F&O records parsed with zero valid depth records.",
                fo_records,
            )

    def on_market_update(self, message: Any) -> None:
        self.msg_count += 1
        if time.time() - self.last_flush >= self.chunk_interval_minutes * 60:
            self.flush()

        try:
            records = parse_upstox_v3_message(message, received_ts_epoch=time.time())
        except UpstoxV3ParseError as exc:
            self.parse_failures += 1
            self.dropped_msg_count += 1
            self.last_parse_error = str(exc)
            logger.error("Upstox V3 parse failure: %s", exc)
            return
        except Exception as exc:
            self.parse_failures += 1
            self.dropped_msg_count += 1
            self.last_parse_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Unexpected Upstox V3 parse failure")
            return

        if not records:
            self.control_message_count += 1
            return

        for record in records:
            instrument_key = str(record["instrument_key"])
            self.record_count += 1
            self.record_counts_by_instrument[instrument_key] += 1
            if bool(record.get("depth_valid")):
                self.valid_depth_counts_by_instrument[instrument_key] += 1
            self.buffer.append(record)
        self._warn_on_empty_fo_depth()

    def on_error(self, error: Any) -> None:
        logger.error("Upstox WebSocket error: %s", error)
        self.reconnects += 1

    def on_close(self, code: Any, reason: Any) -> None:
        logger.warning("Upstox WebSocket closed (Code: %s, Reason: %s).", code, reason)
        self.reconnects += 1

    def finalize(self) -> bool:
        flush_ok = self.flush()
        quality = assess_capture_quality(
            subscribed_instrument_keys=self.keys,
            record_counts=self.record_counts_by_instrument,
            valid_depth_counts=self.valid_depth_counts_by_instrument,
            minimum_active_fo_depth_coverage_ratio=MIN_ACTIVE_FO_DEPTH_COVERAGE_RATIO,
            minimum_valid_depth_records_per_instrument=MIN_VALID_DEPTH_RECORDS_PER_INSTRUMENT,
        )
        additional_reasons: list[str] = []
        if not flush_ok or self.persistence_failures:
            additional_reasons.append(
                f"PERSISTENCE_FAILURES:{self.persistence_failures}"
            )
        if self.parse_failures:
            additional_reasons.append(f"PARSE_FAILURES:{self.parse_failures}")
        if self.dropped_msg_count:
            additional_reasons.append(
                f"DROPPED_MESSAGES:{self.dropped_msg_count}"
            )
        if self.records_written != self.record_count:
            additional_reasons.append(
                f"RECORD_RECONCILIATION_FAILED:{self.records_written}!={self.record_count}"
            )

        reasons = list(quality.reasons) + additional_reasons
        capture_valid = quality.research_depth_eligible and not additional_reasons
        manifest = {
            "schema_version": 2,
            "session_date": self.date_str,
            "capture_classification": (
                "UPSTOX_V3_DEPTH_CAPTURE_VALID"
                if capture_valid
                else "UPSTOX_V3_DEPTH_CAPTURE_INVALID"
            ),
            "capture_valid": capture_valid,
            "research_depth_eligible": capture_valid,
            "reasons": reasons,
            "total_messages": self.msg_count,
            "control_messages": self.control_message_count,
            "parsed_records": self.record_count,
            "records_written": self.records_written,
            "dropped_messages": self.dropped_msg_count,
            "parse_failures": self.parse_failures,
            "persistence_failures": self.persistence_failures,
            "last_parse_error": self.last_parse_error,
            "reconnects": self.reconnects,
            "coverage_keys": len(self.keys),
            "record_counts_by_instrument": dict(
                sorted(self.record_counts_by_instrument.items())
            ),
            "valid_depth_counts_by_instrument": dict(
                sorted(self.valid_depth_counts_by_instrument.items())
            ),
            "depth_quality": quality.as_dict(),
            "minimum_active_fo_depth_coverage_ratio": MIN_ACTIVE_FO_DEPTH_COVERAGE_RATIO,
            "minimum_valid_depth_records_per_instrument": MIN_VALID_DEPTH_RECORDS_PER_INSTRUMENT,
            "finalized_at": datetime.now().isoformat(),
        }
        manifest_path = self.out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if not capture_valid:
            invalid_path = self.out_dir / "INVALID_DEPTH_CAPTURE.json"
            invalid_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            logger.error("Session finalized INVALID. Reasons: %s", reasons)
        else:
            logger.info("Session finalized VALID with %s records.", self.records_written)
        return capture_valid


def _close_streamer(streamer: Any) -> None:
    if streamer is None:
        return
    if hasattr(streamer, "disconnect"):
        streamer.disconnect()
    elif hasattr(streamer, "close"):
        streamer.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Perform instrument refresh and authentication preflight only.",
    )
    args = parser.parse_args()

    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        logger.error("UPSTOX_ACCESS_TOKEN not found in env.")
        return 1
    if not fetch_bod_master():
        return 1
    if not preflight_auth(token):
        return 1

    keys = resolve_instruments()
    if not keys:
        return 1
    if args.auth_only:
        logger.info("Auth-only mode requested. Preflight successful. Exiting.")
        return 0

    now = datetime.now()
    connect_time = now.replace(hour=9, minute=10, second=0, microsecond=0)
    if now < connect_time:
        wait_seconds = (connect_time - now).total_seconds()
        logger.info("Waiting %.1fs until 09:10 IST to connect...", wait_seconds)
        time.sleep(wait_seconds)

    if not UPSTOX_AVAILABLE:
        logger.error("Upstox client not available (pip install upstox-python-sdk).")
        return 1

    collector = DataCollector(token, keys)
    logger.info("Starting V3 Full Market Data Streamer...")
    collector.streamer.on("message", collector.on_market_update)
    collector.streamer.on("error", collector.on_error)
    collector.streamer.on("close", collector.on_close)
    collector.streamer.connect()

    stop_time = datetime_time(15, 35)
    try:
        while datetime.now().time() < stop_time:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        _close_streamer(collector.streamer)

    return 0 if collector.finalize() else 2


if __name__ == "__main__":
    raise SystemExit(main())
