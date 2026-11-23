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
import re
import hashlib
import shutil
import sys
import time
import json
import gzip
import io
import math
import urllib.request
import urllib.parse
import threading
import signal
import logging
import fcntl
import uuid
import atexit
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

def ensure_single_instance(lock_file_path: str = "/tmp/upstox_daily_pipeline.lock"):
    try:
        fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR, 0o644)
        lock_file = open(fd, "r+")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as e:
        logger.error(f"Another instance of upstox_daily_pipeline is already running or flock failed: {e}. Exiting.")
        sys.exit(1)
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
DEFAULT_MODE5_TRACE_HEALTH_INTERVAL_SEC = 60.0
MIN_MODE5_TRACE_HEALTH_INTERVAL_SEC = 5.0
MAX_MODE5_TRACE_HEALTH_INTERVAL_SEC = 3600.0
MODE5_TRACE_HEALTH_DEGRADED_HEARTBEAT_SEC = 300.0
CALLBACK_QUIESCENCE_TIMEOUT_SEC = 10.0
RECORDER_SHUTDOWN_TIMEOUT_SEC = 10.0
ADVISOR_TRACE_DRAIN_TIMEOUT_SEC = 10.0
STREAMER_DISCONNECT_TIMEOUT_SEC = 10.0

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
_LEVEL5_CHUNK_NAME = re.compile(r"^level5_chunk_(\d+)\.parquet$")
_TRACE_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def scan_existing_level5_chunks(chunks_dir: Path) -> tuple[tuple[Path, ...], int]:
    """Validate top-level numbered chunks and return numeric order plus max index."""
    chunks_dir = Path(chunks_dir)
    if not chunks_dir.exists():
        return (), 0
    if chunks_dir.is_symlink() or not chunks_dir.is_dir():
        raise ValueError("chunk directory is not a regular directory")

    by_index: dict[int, Path] = {}
    for entry in chunks_dir.iterdir():
        if not entry.name.startswith("level5_chunk_"):
            continue
        match = _LEVEL5_CHUNK_NAME.fullmatch(entry.name)
        if match is None or entry.is_symlink() or not entry.is_file():
            raise ValueError("malformed or non-regular level5 chunk entry")
        index = int(match.group(1))
        if index <= 0:
            raise ValueError("chunk index must be positive")
        if index in by_index:
            raise ValueError("duplicate numeric level5 chunk index")
        by_index[index] = entry
    ordered = tuple(by_index[index] for index in sorted(by_index))
    return ordered, max(by_index, default=0)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class PointerCommitDurabilityUnknown(OSError):
    """Pointer rename was visible, but parent-directory durability was not confirmed."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__("pointer replacement is visible but directory durability is unknown")
        self.path = Path(path)
        self.cause_type = type(cause).__name__


def _atomic_json(path: Path, payload: dict, *, replace: bool) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        with temp_path.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temp_path, path)
            try:
                _fsync_directory(path.parent)
            except Exception as exc:
                raise PointerCommitDurabilityUnknown(path, exc) from exc
        else:
            os.link(temp_path, path)
            _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_no_replace_file(source: Path, destination: Path) -> None:
    """Durably publish a file without ever replacing an existing destination."""
    source = Path(source)
    destination = Path(destination)
    with source.open("rb") as file_obj:
        os.fsync(file_obj.fileno())
    os.link(source, destination)
    _fsync_directory(destination.parent)


def _write_staged_parquet(path: Path, table: pa.Table) -> None:
    path = Path(path)
    temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        pq.write_table(table, temp_path, compression="snappy")
        with temp_path.open("rb") as parquet_file:
            os.fsync(parquet_file.fileno())
        os.link(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _valid_trace_run_id(run_id) -> bool:
    return (
        isinstance(run_id, str)
        and run_id != "UNKNOWN"
        and _TRACE_RUN_ID_PATTERN.fullmatch(run_id) is not None
    )


def execute_post_market_stitching(
    date_str: str,
    date_compact: str,
    data_dir: Path,
    *,
    chunk_manifest,
    capture_run_id: str,
    recorder_accounting: Optional[dict] = None,
    excluded_prior_chunk_count: int = 0,
):
    data_dir = Path(data_dir)
    chunks_dir = data_dir / "chunks"
    total_chunks = len(chunk_manifest) if isinstance(chunk_manifest, (tuple, list)) else 0
    if not _valid_trace_run_id(capture_run_id):
        return {"status": "INVALID_MANIFEST", "reason": "INVALID_RUN_ID", "total_chunks": total_chunks}
    if not isinstance(chunk_manifest, (tuple, list)):
        return {"status": "INVALID_MANIFEST", "reason": "MANIFEST_NOT_SEQUENCE", "total_chunks": 0}
    if type(excluded_prior_chunk_count) is not int or excluded_prior_chunk_count < 0:
        return {"status": "INVALID_MANIFEST", "reason": "INVALID_PRIOR_CHUNK_COUNT", "total_chunks": total_chunks}

    try:
        chunks_root = chunks_dir.resolve(strict=True)
        data_root = data_dir.resolve(strict=True)
    except Exception:
        return {"status": "INVALID_MANIFEST", "reason": "CHUNK_DIRECTORY_MISSING", "total_chunks": total_chunks}

    chunk_files: list[Path] = []
    seen: set[str] = set()
    for entry in chunk_manifest:
        try:
            candidate = Path(entry)
            if candidate.suffix != ".parquet" or candidate.is_symlink():
                return {"status": "INVALID_MANIFEST", "reason": "INVALID_CHUNK_ENTRY", "total_chunks": total_chunks}
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(chunks_root)
            identity = str(resolved)
            if identity in seen:
                return {"status": "INVALID_MANIFEST", "reason": "DUPLICATE_CHUNK_ENTRY", "total_chunks": total_chunks}
            seen.add(identity)
            if not resolved.exists():
                return {"status": "FAILED_CHUNK_READ", "reason": "MISSING_CHUNK", "total_chunks": total_chunks}
            if not resolved.is_file():
                return {"status": "INVALID_MANIFEST", "reason": "NONREGULAR_CHUNK_ENTRY", "total_chunks": total_chunks}
            chunk_files.append(resolved)
        except (TypeError, ValueError, OSError, RuntimeError):
            return {"status": "INVALID_MANIFEST", "reason": "INVALID_CHUNK_ENTRY", "total_chunks": total_chunks}

    if not isinstance(recorder_accounting, dict):
        return {"status": "INVALID_MANIFEST", "reason": "RECORDER_ACCOUNTING_MISSING", "total_chunks": total_chunks}
    count_fields = (
        "input_count", "total_records_written", "known_drops",
        "input_error_count", "unknown_telemetry_count",
    )
    if any(type(recorder_accounting.get(key)) is not int or recorder_accounting[key] < 0 for key in count_fields):
        return {"status": "INVALID_MANIFEST", "reason": "RECORDER_ACCOUNTING_INVALID", "total_chunks": total_chunks}
    if (
        recorder_accounting.get("accounting_known") is not True
        or recorder_accounting["input_error_count"] != 0
        or recorder_accounting["unknown_telemetry_count"] != 0
        or recorder_accounting["known_drops"] != 0
    ):
        return {"status": "INVALID_MANIFEST", "reason": "RECORDER_ACCOUNTING_DEGRADED", "total_chunks": total_chunks}

    dfs = []
    chunk_records = []
    try:
        for chunk_path in chunk_files:
            table = pq.read_table(chunk_path)
            df = table.to_pandas()
            chunk_records.append({
                "relative_path": chunk_path.relative_to(data_root).as_posix(),
                "row_count": int(table.num_rows),
                "size_bytes": int(chunk_path.stat().st_size),
                "sha256": _sha256_file(chunk_path),
            })
            dfs.append(df)
    except Exception as exc:
        logger.warning("Error reading expected chunk (%s)", type(exc).__name__)
        return {"status": "FAILED_CHUNK_READ", "reason": type(exc).__name__, "total_chunks": total_chunks}

    total_written = sum(item["row_count"] for item in chunk_records)
    if (
        recorder_accounting["total_records_written"] != total_written
        or recorder_accounting["input_count"] != total_written + recorder_accounting["known_drops"]
    ):
        return {"status": "INVALID_MANIFEST", "reason": "RECORDER_ACCOUNTING_MISMATCH", "total_chunks": total_chunks}

    source_manifest = {
        "schema_version": 1,
        "capture_run_id": capture_run_id,
        "trace_run_id": capture_run_id,
        "session_date": date_str,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_scope": "CURRENT_RUN_ONLY",
        "claims_whole_session_complete": False,
        "excluded_prior_chunk_count": excluded_prior_chunk_count,
        "recorder": {
            "input_count": recorder_accounting["input_count"],
            "total_records_written": recorder_accounting["total_records_written"],
            "known_drops": recorder_accounting["known_drops"],
            "drop_status": "NO_DROPS",
            "input_error_count": recorder_accounting["input_error_count"],
            "unknown_telemetry_count": recorder_accounting["unknown_telemetry_count"],
            "accounting_known": recorder_accounting["accounting_known"],
        },
        "chunks": chunk_records,
    }
    source_manifest_path = data_dir / f"capture_source_manifest_{date_compact}_{capture_run_id}.json"
    try:
        _atomic_json(source_manifest_path, source_manifest, replace=False)
        source_bytes = source_manifest_path.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        loaded_manifest = json.loads(source_bytes)
        if loaded_manifest != source_manifest:
            raise ValueError("source manifest readback mismatch")
        for item, chunk_path in zip(loaded_manifest["chunks"], chunk_files):
            if (
                item["relative_path"] != chunk_path.relative_to(data_root).as_posix()
                or item["size_bytes"] != chunk_path.stat().st_size
                or item["sha256"] != _sha256_file(chunk_path)
                or item["row_count"] != pq.ParquetFile(chunk_path).metadata.num_rows
            ):
                raise ValueError("source chunk verification mismatch")
    except Exception as exc:
        return {
            "status": "FAILED_SOURCE_MANIFEST",
            "error_type": type(exc).__name__,
            "total_chunks": total_chunks,
            "source_manifest_path": str(source_manifest_path),
        }

    if not dfs:
        return {
            "status": "NO_CHUNKS",
            "total_chunks": 0,
            "source_manifest_path": str(source_manifest_path),
            "source_manifest_sha256": source_hash,
        }

    try:
        df_all = pd.concat(dfs, ignore_index=True)
        input_rows = len(df_all)
        ts_col = "exchange_timestamp_ms" if "exchange_timestamp_ms" in df_all.columns else ("ts" if "ts" in df_all.columns else None)
        if ts_col:
            df_all = df_all.sort_values(ts_col).reset_index(drop=True)
            subset_cols = [ts_col, "token"] if "token" in df_all.columns else [ts_col]
            df_all = df_all.drop_duplicates(subset=subset_cols).reset_index(drop=True)
        final_count = len(df_all)
        table = pa.Table.from_pandas(df_all)

        generation_root = data_dir / "stitch_generations"
        generation_root_created = not generation_root.exists()
        generation_root.mkdir(parents=True, exist_ok=True)
        if generation_root_created:
            _fsync_directory(data_dir)
        generation_dir = generation_root / capture_run_id
        generation_dir.mkdir(exist_ok=False)
        _fsync_directory(generation_root)
        master_name = f"upstox_full_ticks_{date_compact}_{capture_run_id}.parquet"
        summary_name = f"stitching_summary_{date_compact}_{capture_run_id}.json"
        staged_master = generation_dir / master_name
        staged_summary = generation_dir / summary_name
        _write_staged_parquet(staged_master, table)
        staged_master_size = staged_master.stat().st_size
        staged_master_hash = _sha256_file(staged_master)
        if pq.read_table(staged_master).num_rows != final_count:
            raise ValueError("staged master verification failed")

        summary = {
            "date": date_str,
            "capture_run_id": capture_run_id,
            "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
            "source_manifest_sha256": source_hash,
            "total_chunks": len(chunk_files),
            "input_ticks": input_rows,
            "total_ticks": final_count,
            "duplicates_removed": input_rows - final_count,
            "unique_tokens": int(df_all["symbol"].nunique()) if "symbol" in df_all.columns else 0,
            "file_path": staged_master.relative_to(data_root).as_posix(),
            "file_sha256": staged_master_hash,
            "file_size_bytes": staged_master_size,
            "stitched_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_json(staged_summary, summary, replace=False)
        summary_size = staged_summary.stat().st_size
        summary_hash = _sha256_file(staged_summary)
        if json.loads(staged_summary.read_text(encoding="utf-8")) != summary:
            raise ValueError("staged summary verification failed")

        pointer = {
            "schema_version": 1,
            "capture_run_id": capture_run_id,
            "session_date": date_str,
            "status": "COMMITTED",
            "committed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_manifest": {
                "path": source_manifest_path.relative_to(data_root).as_posix(),
                "sha256": source_hash,
            },
            "master": {
                "path": staged_master.relative_to(data_root).as_posix(),
                "sha256": staged_master_hash,
                "size_bytes": staged_master_size,
            },
            "summary": {
                "path": staged_summary.relative_to(data_root).as_posix(),
                "sha256": summary_hash,
                "size_bytes": summary_size,
            },
        }
        _atomic_json(data_dir / "latest_stitch_manifest.json", pointer, replace=True)
    except PointerCommitDurabilityUnknown as exc:
        return {
            "status": "COMMIT_DURABILITY_UNKNOWN",
            "error_type": exc.cause_type,
            "capture_run_id": capture_run_id,
            "pointer_path": exc.path.relative_to(data_root).as_posix(),
            "pointer_visibility": "VISIBLE_DURABILITY_UNCONFIRMED",
            "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
            "source_manifest_sha256": source_hash,
            "total_chunks": total_chunks,
        }
    except FileExistsError as exc:
        return {
            "status": "GENERATION_COLLISION",
            "error_type": type(exc).__name__,
            "total_chunks": total_chunks,
            "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
            "source_manifest_sha256": source_hash,
        }
    except Exception as exc:
        logger.error("Stitch generation failed (%s)", type(exc).__name__)
        return {
            "status": "FAILED_STITCH_PUBLICATION",
            "error_type": type(exc).__name__,
            "total_chunks": total_chunks,
            "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
            "source_manifest_sha256": source_hash,
        }

    try:
        canonical_master = data_dir / f"upstox_full_ticks_{date_compact}_stitched.parquet"
        canonical_summary = data_dir / f"stitching_summary_{date_compact}.json"
        for source, destination in ((staged_master, canonical_master), (staged_summary, canonical_summary)):
            alias_temp = data_dir / f".{destination.name}.{uuid.uuid4().hex}.tmp"
            try:
                shutil.copyfile(source, alias_temp)
                with alias_temp.open("rb") as alias_file:
                    os.fsync(alias_file.fileno())
                os.replace(alias_temp, destination)
                _fsync_directory(data_dir)
            finally:
                try:
                    alias_temp.unlink()
                except FileNotFoundError:
                    pass
    except Exception as exc:
        return {
            "status": "ALIAS_UPDATE_FAILED",
            "error_type": type(exc).__name__,
            "capture_run_id": capture_run_id,
            "pointer_path": "latest_stitch_manifest.json",
            "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
            "source_manifest_sha256": source_hash,
        }

    # Preserve the existing supplemental official-candle capture after the pair
    # pointer is committed. It is not part of the stitched-pair commit contract.
    try:
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
                f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/1/{date_str}/{date_str}",
            ]
            candles = []
            for url in urls:
                try:
                    request = urllib.request.Request(
                        url,
                        headers={
                            "Accept": "application/json",
                            "Api-Version": "2.0",
                            "User-Agent": "TradeBot/1.0",
                            "Authorization": f"Bearer {get_access_token()}",
                        },
                    )
                    with urllib.request.urlopen(request) as response:
                        data = json.loads(response.read().decode())
                        candles = data.get("data", {}).get("candles", [])
                        if candles:
                            break
                except Exception as exc:
                    logger.debug("Historical candle attempt failed (%s)", type(exc).__name__)
            for candle in candles:
                all_candles.append({
                    "timestamp": datetime.fromisoformat(candle[0].replace("+05:30", "")),
                    "symbol": name,
                    "instrument_key": key,
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                    "oi": float(candle[6]) if len(candle) > 6 else 0.0,
                })
        if all_candles:
            candle_frame = pd.DataFrame(all_candles).sort_values(
                ["timestamp", "symbol"]
            ).reset_index(drop=True)
            candle_path = data_dir / f"indices_1m_{date_compact}.parquet"
            pq.write_table(pa.Table.from_pandas(candle_frame), candle_path, compression="snappy")
    except Exception as exc:
        logger.error("Official historical candle fetch failed (%s)", type(exc).__name__)

    return {
        "status": "COMPLETED",
        "total_chunks": len(chunk_files),
        "stitched": True,
        "capture_run_id": capture_run_id,
        "source_manifest_path": source_manifest_path.relative_to(data_root).as_posix(),
        "source_manifest_sha256": source_hash,
        "pointer_path": "latest_stitch_manifest.json",
        "master_path": pointer["master"]["path"],
        "summary_path": pointer["summary"]["path"],
    }


def parse_mode5_trace_health_interval(
    raw_value: Optional[str], warning_logger: logging.Logger = logger
) -> float:
    """Parse the bounded health-log interval without echoing configured values."""
    if raw_value is None:
        return DEFAULT_MODE5_TRACE_HEALTH_INTERVAL_SEC
    try:
        value = float(raw_value)
        if not math.isfinite(value) or not (
            MIN_MODE5_TRACE_HEALTH_INTERVAL_SEC
            <= value
            <= MAX_MODE5_TRACE_HEALTH_INTERVAL_SEC
        ):
            raise ValueError("out_of_range")
        return value
    except (TypeError, ValueError, OverflowError):
        try:
            warning_logger.warning(
                "Invalid MODE5_TRACE_HEALTH_INTERVAL_SEC; using default interval."
            )
        except Exception:
            pass
        return DEFAULT_MODE5_TRACE_HEALTH_INTERVAL_SEC


def _safe_trace_health_snapshot(advisor) -> dict:
    run_id = getattr(advisor, "trace_run_id", None)
    try:
        getter = getattr(advisor, "get_mode5_trace_health_snapshot", None)
        if not callable(getter):
            getter = getattr(advisor, "get_mode5_trace_health", None)
        if not callable(getter):
            raise AttributeError("health_getter_unavailable")
        raw = getter()
        if not isinstance(raw, dict):
            raise TypeError("health_snapshot_not_mapping")
        required_counters = (
            "capacity", "max_record_bytes", "queue_depth", "pending_unpersisted",
            "enqueued", "append_successes", "append_failures", "queue_full_drops",
            "oversize_drops", "writer_unavailable_drops", "active_writes",
        )
        required = (*required_counters, "last_persisted_sequence", "last_processed_sequence", "writer_status", "degraded")
        if any(key not in raw for key in required):
            raise ValueError("health_snapshot_missing_fields")
        result = {
            "status": "AVAILABLE",
            "trace_run_id": run_id or raw.get("trace_run_id") or "UNKNOWN",
        }
        if not isinstance(result["trace_run_id"], str) or not result["trace_run_id"] or result["trace_run_id"] == "UNKNOWN":
            raise ValueError("health_snapshot_missing_trace_run_id")
        for key in required_counters:
            value = raw[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("health_snapshot_invalid_counter")
            result[key] = value
        if result["append_successes"] > result["enqueued"]:
            raise ValueError("health_snapshot_successes_exceed_enqueued")
        for key in ("last_persisted_sequence", "last_processed_sequence"):
            value = raw[key]
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError("health_snapshot_invalid_sequence")
            result[key] = value
        if not isinstance(raw["writer_status"], str) or not raw["writer_status"]:
            raise ValueError("health_snapshot_invalid_writer_status")
        if not isinstance(raw["degraded"], bool):
            raise ValueError("health_snapshot_invalid_degraded")
        result["writer_status"] = raw["writer_status"]
        result["degraded"] = raw["degraded"]
        result["last_error_present"] = bool(raw.get("last_error"))
        return result
    except Exception as exc:
        return {
            "status": "ERROR",
            "trace_run_id": run_id or "UNKNOWN",
            "health_error_type": type(exc).__name__,
            "degraded": True,
        }


def _safe_pipeline_log(level: str, message: str, *args) -> None:
    try:
        getattr(logger, level)(message, *args)
    except Exception:
        try:
            rendered = message % args if args else message
            sys.stderr.write(f"{level.upper()}: {rendered}\n")
            sys.stderr.flush()
        except Exception:
            pass


class Mode5TraceHealthReporter:
    """Best-effort periodic, sanitized health telemetry isolated from callbacks."""

    def __init__(
        self,
        advisor,
        interval_sec: float = DEFAULT_MODE5_TRACE_HEALTH_INTERVAL_SEC,
        *,
        monotonic_clock=time.monotonic,
        log=logger,
    ) -> None:
        self.advisor = advisor
        self.interval_sec = interval_sec
        self.monotonic_clock = monotonic_clock
        self.log = log
        self.next_snapshot_at = monotonic_clock()
        self.last_snapshot: Optional[dict] = None
        self.last_degraded_warning_at: Optional[float] = None
        self.last_degraded_state = False
        self.reporting_failures = 0
        self.last_reporting_error_type: Optional[str] = None

    def _safe_log(self, level: str, message: str, payload: dict) -> None:
        try:
            method = getattr(self.log, level)
            method("%s %s", message, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        except Exception as exc:
            self.reporting_failures += 1
            self.last_reporting_error_type = type(exc).__name__

    def maybe_report(self, *, force: bool = False) -> Optional[dict]:
        """Take/log a report when due; never raise into the market loop."""
        try:
            now = self.monotonic_clock()
            if not force and now < self.next_snapshot_at:
                return self.last_snapshot
            snapshot = _safe_trace_health_snapshot(self.advisor)
            degraded = snapshot.get("status") != "AVAILABLE" or bool(snapshot.get("degraded"))
            self._safe_log("info", "Mode5 trace health snapshot", snapshot)
            self.next_snapshot_at = now + self.interval_sec
            if degraded and (
                not self.last_degraded_state
                or self.last_degraded_warning_at is None
                or now - self.last_degraded_warning_at >= MODE5_TRACE_HEALTH_DEGRADED_HEARTBEAT_SEC
            ):
                self._safe_log("warning", "Mode5 trace health degraded", snapshot)
                self.last_degraded_warning_at = now
            self.last_degraded_state = degraded
            self.last_snapshot = snapshot
            return snapshot
        except Exception as exc:
            self.reporting_failures += 1
            self.last_reporting_error_type = type(exc).__name__
            return None


class CallbackAdmissionGate:
    """Closeable admission gate for streamer callbacks with bounded drain waits."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._admission_open = True
        self._active_callbacks = 0
        self._late_callback_count = 0

    def wrap(self, callback):
        def admitted_callback(*args, **kwargs):
            with self._condition:
                if not self._admission_open:
                    self._late_callback_count += 1
                    return None
                self._active_callbacks += 1
            try:
                return callback(*args, **kwargs)
            finally:
                with self._condition:
                    self._active_callbacks = max(0, self._active_callbacks - 1)
                    self._condition.notify_all()
        return admitted_callback

    def close_admission(self) -> dict:
        with self._condition:
            self._admission_open = False
            self._condition.notify_all()
            return self.snapshot()

    def wait_for_quiescence(self, timeout_sec: float = CALLBACK_QUIESCENCE_TIMEOUT_SEC) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_sec)
        with self._condition:
            while self._active_callbacks > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "admission_open": self._admission_open,
                "active_callback_count": self._active_callbacks,
                "late_callback_rejects_at_snapshot": self._late_callback_count,
            }


class DispatchLease:
    """Lease covering one synchronous broadcaster dispatch and its state update."""

    def __init__(self, fence: "DispatchAdmissionFence") -> None:
        self._fence = fence
        self._released = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self._released:
            self._released = True
            self._fence._release()
        return False


class DispatchAdmissionFence:
    """Prevents new depth/tick dispatches once shutdown begins; existing leases drain."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._open = True
        self._active = 0
        self._denied = 0

    def acquire(self) -> Optional[DispatchLease]:
        with self._condition:
            if not self._open:
                self._denied += 1
                return None
            self._active += 1
            return DispatchLease(self)

    def close(self) -> dict:
        with self._condition:
            self._open = False
            self._condition.notify_all()
            return self.snapshot()

    def _release(self) -> None:
        with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    def wait_for_quiescence(self, timeout_sec: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_sec)
        with self._condition:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "dispatch_admission_open": self._open,
                "active_dispatch_count": self._active,
                "denied_dispatch_count": self._denied,
            }


def _dispatch_with_lease(fence, dispatch, state_update=None) -> bool:
    """Run synchronous dispatch and its associated state update under one lease."""
    lease = fence.acquire()
    if lease is None:
        return False
    with lease:
        dispatch()
        if state_update is not None:
            state_update()
    return True


class RecorderAccountingSink:
    """Counts recorder inputs and classifies persistence loss telemetry."""

    _KNOWN_EVENTS = {
        "QUEUE_HIGH_WATERMARK",
        "PERSISTENCE_QUEUE_DROPPED_BURST",
        "PERSISTENCE_QUEUE_EXHAUSTED",
    }

    def __init__(self, recorder) -> None:
        self.recorder = recorder
        self._lock = threading.RLock()
        self.input_count = 0
        self.known_drops = 0
        self.unknown_telemetry_count = 0
        self.input_error_count = 0
        self.last_error_type = None
        attach = getattr(recorder, "add_telemetry_callback", None)
        if not callable(attach):
            self.unknown_telemetry_count += 1
            self.last_error_type = "TelemetryCallbackUnavailable"
        else:
            try:
                attach(self._on_telemetry)
            except Exception as exc:
                self.unknown_telemetry_count += 1
                self.last_error_type = type(exc).__name__

    def _on_telemetry(self, event) -> None:
        with self._lock:
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                self.unknown_telemetry_count += 1
                self.last_error_type = "MalformedTelemetry"
                return
            name = event["event"]
            if name not in self._KNOWN_EVENTS:
                self.unknown_telemetry_count += 1
            elif name in {"PERSISTENCE_QUEUE_DROPPED_BURST", "PERSISTENCE_QUEUE_EXHAUSTED"}:
                self.known_drops += 1

    def on_depth(self, depth) -> None:
        with self._lock:
            self.input_count += 1
            drops_before = self.known_drops
        try:
            self.recorder.on_depth(depth)
        except Exception as exc:
            with self._lock:
                self.input_error_count += 1
                self.last_error_type = type(exc).__name__
                # Saturation is accounted through its telemetry event. An exception
                # without a corresponding known drop means the record disposition is unknown.
                if self.known_drops == drops_before:
                    self.unknown_telemetry_count += 1

    def on_tick(self, tick) -> None:
        callback = getattr(self.recorder, "on_tick", None)
        if callable(callback):
            callback(tick)

    def on_stream_status(self, status) -> None:
        callback = getattr(self.recorder, "on_stream_status", None)
        if callable(callback):
            callback(status)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "input_count": self.input_count,
                "known_drops": self.known_drops,
                "unknown_telemetry_count": self.unknown_telemetry_count,
                "input_error_count": self.input_error_count,
                "last_error_type": self.last_error_type,
                "accounting_known": self.unknown_telemetry_count == 0,
            }


def write_capture_health_report(path: Path, report: dict) -> None:
    """Atomically persist a JSON report so a pre-stitch snapshot survives stitch failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as report_file:
            json.dump(report, report_file, indent=2, sort_keys=True)
            report_file.flush()
            os.fsync(report_file.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _trace_capture_status(
    health: dict,
    *,
    disconnect_status: str,
    advisor_drain_status: str,
    callback_status: str,
    active_callback_count: int = 0,
    late_callback_count: int = 0,
) -> str:
    if health.get("status") != "AVAILABLE":
        return "UNKNOWN"
    enqueued = int(health.get("enqueued") or 0)
    persisted_sequence = health.get("last_persisted_sequence")
    processed_sequence = health.get("last_processed_sequence")
    if enqueued == 0:
        sequence_consistent = persisted_sequence in (None, 0) and processed_sequence in (None, 0)
    else:
        sequence_consistent = (
            persisted_sequence is not None
            and processed_sequence is not None
            and persisted_sequence == processed_sequence
        )
    has_drops = any(
        int(health.get(key) or 0) > 0
        for key in ("append_failures", "queue_full_drops", "oversize_drops", "writer_unavailable_drops")
    )
    if (
        health.get("degraded")
        or int(health.get("capacity") or 0) <= 0
        or int(health.get("max_record_bytes") or 0) <= 0
        or has_drops
        or int(health.get("append_successes") or 0) != enqueued
        or not sequence_consistent
        or int(health.get("pending_unpersisted") or 0) > 0
        or int(health.get("queue_depth") or 0) > 0
        or int(health.get("active_writes") or 0) > 0
        or health.get("writer_status") != "STOPPED"
        or disconnect_status != "RETURNED"
        or advisor_drain_status != "STOPPED"
        or callback_status != "QUIESCENT"
        or active_callback_count > 0
        or late_callback_count > 0
    ):
        return "DEGRADED"
    return "HEALTHY"


def _run_bounded_shutdown_call(name: str, callback, timeout_sec: float) -> dict:
    """Run shutdown work in a daemon so a blocked implementation cannot hang exit."""
    completed = threading.Event()
    result = {"status": "NOT_STARTED", "error_type": None, "value": None, "worker_alive": False}

    def invoke():
        try:
            result["value"] = callback()
            result["status"] = "RETURNED"
        except BaseException as exc:
            result["status"] = "RAISED"
            result["error_type"] = type(exc).__name__
        finally:
            completed.set()

    worker = threading.Thread(target=invoke, name=name, daemon=True)
    try:
        worker.start()
    except Exception as exc:
        result["status"] = "START_FAILED"
        result["error_type"] = type(exc).__name__
        return result
    if not completed.wait(max(0.0, timeout_sec)):
        result["status"] = "TIMED_OUT"
        result["worker_alive"] = worker.is_alive()
    else:
        worker.join(timeout=0.01)
        result["worker_alive"] = worker.is_alive()
    return result


def run_capture_loop_safely(run_loop, shutdown) -> tuple[Optional[dict], int]:
    """Always run shutdown; preserve process interrupts and classify ordinary failures."""
    loop_exception = None
    try:
        run_loop()
    except BaseException as exc:
        loop_exception = exc
        _safe_pipeline_log(
            "error", "Capture loop ended with %s; bounded shutdown will run", type(exc).__name__
        )
    try:
        report = shutdown(type(loop_exception).__name__ if loop_exception is not None else None)
    except BaseException as cleanup_exception:
        _safe_pipeline_log(
            "error", "Capture shutdown raised %s", type(cleanup_exception).__name__
        )
        if isinstance(loop_exception, (KeyboardInterrupt, SystemExit)):
            raise loop_exception
        if isinstance(cleanup_exception, (KeyboardInterrupt, SystemExit)):
            raise
        return None, 1
    if isinstance(loop_exception, (KeyboardInterrupt, SystemExit)):
        raise loop_exception
    if loop_exception is not None:
        return report, 1
    if not isinstance(report, dict):
        return None, 1
    return report, int(report.get("exit_code", 1))


def finalize_capture_session(
    *,
    streamer,
    callback_gate: CallbackAdmissionGate,
    dispatch_fence: Optional[DispatchAdmissionFence] = None,
    recorder,
    recorder_accounting: Optional[RecorderAccountingSink] = None,
    advisor,
    report_path: Path,
    date_str: str,
    date_compact: str,
    stitch_callable=execute_post_market_stitching,
    callback_timeout_sec: float = CALLBACK_QUIESCENCE_TIMEOUT_SEC,
    recorder_timeout_sec: float = RECORDER_SHUTDOWN_TIMEOUT_SEC,
    advisor_timeout_sec: float = ADVISOR_TRACE_DRAIN_TIMEOUT_SEC,
    disconnect_timeout_sec: float = STREAMER_DISCONNECT_TIMEOUT_SEC,
    loop_error_type: Optional[str] = None,
    health_reporting_failures: int = 0,
    health_reporting_last_error_type: Optional[str] = None,
    allow_stitch: bool = True,
    excluded_prior_chunk_count: int = 0,
) -> dict:
    """Bound shutdown; callback timeout fails closed and skips dependent cleanup/stitch."""
    report = {
        "schema_version": 1,
        "trace_run_id": getattr(advisor, "trace_run_id", None) or "UNKNOWN",
        "session_date": date_str,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_stage": "PRE_STITCH",
        "trace_capture_status": "UNKNOWN",
        "stitch_status": "PENDING",
        "disconnect_status": "NOT_CONNECTED",
        "disconnect_error_type": None,
        "disconnect_worker_alive": False,
        "callbacks_may_arrive_after_disconnect_timeout": False,
        "callback_quiescence_status": "NOT_STARTED",
        "dispatch_quiescence_status": "NOT_STARTED",
        "active_dispatch_count": None,
        "denied_dispatch_count": None,
        "order_action_may_be_in_flight": False,
        "late_callback_rejects_at_report": 0,
        "late_callback_rejects_at_report_timestamp_utc": None,
        "advisor_atexit_unregister_status": "NOT_ATTEMPTED",
        "advisor_atexit_unregister_error_type": None,
        "recorder_status": "NOT_STARTED",
        "recorder_data_status": "UNKNOWN",
        "source_manifest_status": "NOT_ATTEMPTED",
        "source_manifest_path": None,
        "source_manifest_sha256": None,
        "recorder_error_type": None,
        "recorder_shutdown_worker_alive": False,
        "advisor_drain_status": "NOT_STARTED",
        "advisor_drain_error_type": None,
        "advisor_shutdown_worker_alive": False,
        "pre_stitch_report_status": "NOT_ATTEMPTED",
        "final_report_update_status": "NOT_ATTEMPTED",
        "report_error_type": None,
        "stitch_error_type": None,
        "capture_loop_status": "ERROR" if loop_error_type else "COMPLETED",
        "capture_loop_error_type": loop_error_type,
        "health_reporting_failures": health_reporting_failures,
        "health_reporting_last_error_type": health_reporting_last_error_type,
    }

    # Fence depth/tick dispatches before disconnect starts. Callback admission remains
    # open until disconnect returns, raises, or times out.
    dispatch_fence_close_ok = dispatch_fence is not None
    if dispatch_fence is not None:
        try:
            dispatch_fence.close()
        except Exception as exc:
            dispatch_fence_close_ok = False
            report["dispatch_quiescence_status"] = "FENCE_ERROR"
            report["dispatch_fence_error_type"] = type(exc).__name__

    if streamer is None:
        report["disconnect_status"] = "NOT_CONNECTED"
    else:
        disconnect = _run_bounded_shutdown_call(
            "upstox-final-disconnect", streamer.disconnect, disconnect_timeout_sec
        )
        report["disconnect_status"] = disconnect["status"]
        report["disconnect_error_type"] = disconnect["error_type"]
        report["disconnect_worker_alive"] = disconnect["worker_alive"]
        report["callbacks_may_arrive_after_disconnect_timeout"] = disconnect["status"] == "TIMED_OUT"
        if disconnect["status"] != "RETURNED":
            _safe_pipeline_log(
                "warning", "Streamer disconnect shutdown status=%s error=%s",
                disconnect["status"], disconnect["error_type"] or "none",
            )

    try:
        callback_gate.close_admission()
    except Exception as exc:
        report["callback_quiescence_status"] = "GATE_ERROR"
        report["callback_gate_error_type"] = type(exc).__name__
    else:
        try:
            quiescent = callback_gate.wait_for_quiescence(callback_timeout_sec)
            report["callback_quiescence_status"] = (
                "QUIESCENT" if quiescent else "CALLBACK_QUIESCENCE_TIMEOUT"
            )
        except Exception as exc:
            report["callback_quiescence_status"] = "GATE_ERROR"
            report["callback_gate_error_type"] = type(exc).__name__
    try:
        callback_snapshot = callback_gate.snapshot()
        report["active_callback_count"] = callback_snapshot["active_callback_count"]
        report["late_callback_rejects_at_report"] = callback_snapshot[
            "late_callback_rejects_at_snapshot"
        ]
        report["late_callback_rejects_at_report_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        report.setdefault("callback_gate_error_type", type(exc).__name__)

    if dispatch_fence is None:
        report["dispatch_quiescence_status"] = "NOT_CONFIGURED"
        dispatch_snapshot = {"active_dispatch_count": 0, "denied_dispatch_count": 0}
    else:
        try:
            dispatch_quiet = dispatch_fence.wait_for_quiescence(callback_timeout_sec)
            if dispatch_fence_close_ok:
                report["dispatch_quiescence_status"] = (
                    "QUIESCENT" if dispatch_quiet else "DISPATCH_QUIESCENCE_TIMEOUT"
                )
            dispatch_snapshot = dispatch_fence.snapshot()
        except Exception as exc:
            report["dispatch_quiescence_status"] = "FENCE_ERROR"
            report["dispatch_fence_error_type"] = type(exc).__name__
            dispatch_snapshot = {"active_dispatch_count": None, "denied_dispatch_count": None}
    report["active_dispatch_count"] = dispatch_snapshot.get("active_dispatch_count")
    report["denied_dispatch_count"] = dispatch_snapshot.get("denied_dispatch_count")

    callback_safe = (
        report["callback_quiescence_status"] == "QUIESCENT"
        and (
            dispatch_fence_close_ok and report["dispatch_quiescence_status"] == "QUIESCENT"
            or (streamer is None and report["dispatch_quiescence_status"] == "NOT_CONFIGURED")
        )
        and report.get("active_dispatch_count") == 0
    )
    if not callback_safe:
        if report["callback_quiescence_status"] == "CALLBACK_QUIESCENCE_TIMEOUT":
            skip_reason = "CALLBACK_QUIESCENCE_TIMEOUT"
        elif report["dispatch_quiescence_status"] == "DISPATCH_QUIESCENCE_TIMEOUT":
            skip_reason = "DISPATCH_QUIESCENCE_TIMEOUT"
        else:
            skip_reason = "CALLBACK_OR_DISPATCH_GATE_ERROR"
        report["order_action_may_be_in_flight"] = bool(
            (report.get("active_callback_count") or 0) > 0
            or (report.get("active_dispatch_count") or 0) > 0
            or report.get("active_callback_count") is None
            or report.get("active_dispatch_count") is None
        )
        report["recorder_status"] = f"SKIPPED_{skip_reason}"
        report["advisor_drain_status"] = f"SKIPPED_{skip_reason}"
        atexit_callback = getattr(advisor, "_mode5_trace_atexit_callback", None)
        if atexit_callback is None:
            report["advisor_atexit_unregister_status"] = "NOT_REGISTERED_OR_UNAVAILABLE"
        else:
            try:
                atexit.unregister(atexit_callback)
                report["advisor_atexit_unregister_status"] = "UNREGISTERED"
            except Exception as exc:
                report["advisor_atexit_unregister_status"] = "ERROR"
                report["advisor_atexit_unregister_error_type"] = type(exc).__name__
                _safe_pipeline_log("error", "Advisor atexit unregister failed (%s)", type(exc).__name__)
        trace_health = _safe_trace_health_snapshot(advisor)
        report["trace_health"] = trace_health
        report["trace_capture_status"] = "DEGRADED"
        report["run_capture_status"] = "DEGRADED"
        report["stitch_status"] = f"SKIPPED_{skip_reason}"
        report["exit_code"] = 1
        try:
            write_capture_health_report(report_path, report)
            report["pre_stitch_report_status"] = "WRITTEN"
        except Exception as exc:
            report["pre_stitch_report_status"] = "FAILED"
            report["report_error_type"] = type(exc).__name__
            _safe_pipeline_log("error", "Pre-stitch capture report write failed (%s)", type(exc).__name__)
        report["report_stage"] = "FINAL_UPDATE"
        try:
            write_capture_health_report(report_path, report)
            report["final_report_update_status"] = "WRITTEN"
        except Exception as exc:
            report["final_report_update_status"] = "FAILED"
            report["report_error_type"] = type(exc).__name__
            _safe_pipeline_log("error", "Final capture report write failed (%s)", type(exc).__name__)
        return report

    recorder_stop_observation = {}

    def stop_recorder():
        recorder.flush_and_stop(timeout=recorder_timeout_sec)
        worker = getattr(recorder, "_worker_thread", None)
        recorder_stop_observation["recorder_worker_alive"] = worker.is_alive() if worker is not None else None
        recorder_queue = getattr(recorder, "_queue", None)
        recorder_stop_observation["recorder_queue_depth"] = recorder_queue.qsize() if recorder_queue is not None else None
    if recorder is None:
        report["recorder_status"] = "NOT_CREATED"
    else:
        recorder_result = _run_bounded_shutdown_call(
            "upstox-recorder-final-stop", stop_recorder, recorder_timeout_sec
        )
        report["recorder_shutdown_worker_alive"] = recorder_result["worker_alive"]
        if recorder_result["status"] == "RETURNED":
            report.update(recorder_stop_observation)
        if recorder_result["status"] == "TIMED_OUT":
            report["recorder_status"] = "TIMED_OUT"
        elif recorder_result["status"] in {"RAISED", "START_FAILED"}:
            report["recorder_status"] = "ERROR"
            report["recorder_error_type"] = recorder_result["error_type"]
            _safe_pipeline_log("error", "Recorder shutdown failed (%s)", recorder_result["error_type"])
        elif report.get("recorder_worker_alive") is False and report.get("recorder_queue_depth") == 0:
            report["recorder_status"] = "STOPPED"
        elif report.get("recorder_worker_alive") is True:
            report["recorder_status"] = "TIMED_OUT"
        else:
            report["recorder_status"] = "UNKNOWN"

    accounting = recorder_accounting.snapshot() if recorder_accounting is not None else None
    if accounting is not None:
        report["recorder_accounting"] = accounting
    if recorder is not None and recorder_result["status"] == "RETURNED":
        try:
            written = int(getattr(recorder, "total_records_written"))
            report["recorder_total_records_written"] = written
            if accounting is None:
                report["recorder_data_status"] = "ACCOUNTING_UNKNOWN"
            elif not accounting["accounting_known"]:
                report["recorder_data_status"] = "ACCOUNTING_UNKNOWN"
            elif accounting["known_drops"] > 0:
                report["recorder_data_status"] = "DROPPED_RECORDS"
            elif accounting["input_count"] != written + accounting["known_drops"]:
                report["recorder_data_status"] = "ACCOUNTING_MISMATCH"
            elif accounting["input_error_count"] > 0:
                report["recorder_data_status"] = "INPUT_ERROR"
            else:
                report["recorder_data_status"] = "ACCOUNTED"
                accounting["total_records_written"] = written
        except Exception as exc:
            report["recorder_data_status"] = "ACCOUNTING_UNKNOWN"
            report["recorder_accounting_error_type"] = type(exc).__name__

    drain_result = None
    try:
        shutdown = getattr(advisor, "shutdown_mode5_trace_writer", None) if advisor is not None else None
        if advisor is None:
            report["advisor_drain_status"] = "NOT_CREATED"
        elif not callable(shutdown):
            raise AttributeError("advisor_trace_shutdown_unavailable")
        else:
            advisor_result = _run_bounded_shutdown_call(
                "mode5-advisor-trace-drain",
                lambda: shutdown(timeout_sec=advisor_timeout_sec),
                advisor_timeout_sec,
            )
            if advisor_result["status"] == "TIMED_OUT":
                report["advisor_drain_status"] = "TIMED_OUT"
            elif advisor_result["status"] in {"RAISED", "START_FAILED"}:
                report["advisor_drain_status"] = "ERROR"
                report["advisor_drain_error_type"] = advisor_result["error_type"]
            else:
                drain_result = advisor_result["value"]
                report["advisor_drain_status"] = (
                    "STOPPED" if isinstance(drain_result, dict)
                    and drain_result.get("writer_status") == "STOPPED"
                    and drain_result.get("pending_unpersisted") == 0
                    and drain_result.get("queue_depth") == 0
                    and drain_result.get("active_writes") == 0
                    else "DEGRADED"
                )
            report["advisor_shutdown_worker_alive"] = advisor_result["worker_alive"]
    except Exception as exc:
        report["advisor_drain_status"] = "ERROR"
        report["advisor_drain_error_type"] = type(exc).__name__
        _safe_pipeline_log("error", "Advisor trace drain failed (%s)", type(exc).__name__)

    try:
        release_wal_owners = getattr(advisor, "shutdown_apm_wal_ownership", None) if advisor is not None else None
        if advisor is None:
            report["advisor_wal_ownership_release_status"] = "NOT_CREATED"
        elif not callable(release_wal_owners):
            raise AttributeError("advisor_wal_ownership_shutdown_unavailable")
        else:
            owner_result = _run_bounded_shutdown_call(
                "apm-wal-owner-release",
                release_wal_owners,
                advisor_timeout_sec,
            )
            if owner_result["status"] == "TIMED_OUT":
                report["advisor_wal_ownership_release_status"] = "TIMED_OUT"
            elif owner_result["status"] in {"RAISED", "START_FAILED"}:
                report["advisor_wal_ownership_release_status"] = "ERROR"
                report["advisor_wal_ownership_release_error_type"] = owner_result["error_type"]
            else:
                owner_value = owner_result["value"]
                report["advisor_wal_ownership_release_status"] = (
                    owner_value.get("status", "UNKNOWN")
                    if isinstance(owner_value, dict)
                    else "UNKNOWN"
                )
                if isinstance(owner_value, dict) and owner_value.get("failures"):
                    report["advisor_wal_ownership_release_failures"] = owner_value["failures"]
    except Exception as exc:
        report["advisor_wal_ownership_release_status"] = "ERROR"
        report["advisor_wal_ownership_release_error_type"] = type(exc).__name__
        _safe_pipeline_log("error", "APM WAL owner release failed (%s)", type(exc).__name__)

    if isinstance(drain_result, dict):
        trace_health = _safe_trace_health_snapshot_from_mapping(
            drain_result, report["trace_run_id"]
        )
    else:
        trace_health = _safe_trace_health_snapshot(advisor)
    report["trace_health"] = trace_health
    callback_status = report["callback_quiescence_status"]
    report["trace_capture_status"] = _trace_capture_status(
        trace_health,
        disconnect_status=report["disconnect_status"],
        advisor_drain_status=report["advisor_drain_status"],
        callback_status=callback_status,
        active_callback_count=int(report.get("active_callback_count") or 0),
        late_callback_count=int(report.get("late_callback_rejects_at_report") or 0),
    )
    report["run_capture_status"] = (
        "HEALTHY"
        if report["trace_capture_status"] == "HEALTHY"
        and report["recorder_status"] == "STOPPED"
        and report["recorder_data_status"] == "ACCOUNTED"
        and report["recorder_queue_depth"] == 0
        and report.get("denied_dispatch_count") == 0
        and loop_error_type is None
        and health_reporting_failures == 0
        else "DEGRADED"
    )

    try:
        write_capture_health_report(report_path, report)
        report["pre_stitch_report_status"] = "WRITTEN"
    except Exception as exc:
        report["pre_stitch_report_status"] = "FAILED"
        report["report_error_type"] = type(exc).__name__
        _safe_pipeline_log("error", "Pre-stitch health report write failed (%s)", type(exc).__name__)

    if streamer is not None and report["disconnect_status"] != "RETURNED":
        report["stitch_status"] = "SKIPPED_DISCONNECT_UNCONFIRMED"
    elif report["recorder_status"] != "STOPPED":
        report["stitch_status"] = "SKIPPED_RECORDER_NOT_POSITIVELY_STOPPED"
    elif report["recorder_data_status"] != "ACCOUNTED":
        report["stitch_status"] = "SKIPPED_RECORDER_DATA_LOSS"
    elif (report.get("denied_dispatch_count") or 0) > 0:
        report["stitch_status"] = "SKIPPED_DISPATCH_FENCE_REJECTIONS"
    elif report["pre_stitch_report_status"] != "WRITTEN":
        report["stitch_status"] = "SKIPPED_REPORT_PERSISTENCE_FAILURE"
    elif not allow_stitch:
        report["stitch_status"] = "SKIPPED_SETUP_FAILURE"
    else:
        try:
            if stitch_callable is execute_post_market_stitching:
                try:
                    chunk_manifest = tuple(getattr(recorder, "written_files"))
                except Exception as exc:
                    chunk_manifest = None
                    report["chunk_manifest_error_type"] = type(exc).__name__
                report["chunk_manifest_count"] = (
                    len(chunk_manifest) if chunk_manifest is not None else None
                )
                stitch_result = execute_post_market_stitching(
                    date_str,
                    date_compact,
                    Path(report_path).parent,
                    chunk_manifest=chunk_manifest,
                    capture_run_id=report["trace_run_id"],
                    recorder_accounting=accounting,
                    excluded_prior_chunk_count=excluded_prior_chunk_count,
                )
            else:
                stitch_result = stitch_callable(date_str, date_compact, Path(report_path).parent)
            if isinstance(stitch_result, dict) and isinstance(stitch_result.get("status"), str):
                report["stitch_status"] = stitch_result["status"]
                report["stitch_result"] = stitch_result
                report["source_manifest_status"] = (
                    "WRITTEN" if stitch_result.get("source_manifest_path") else
                    "FAILED" if stitch_result["status"] == "FAILED_SOURCE_MANIFEST" else
                    "NOT_CREATED"
                )
                report["source_manifest_path"] = stitch_result.get("source_manifest_path")
                report["source_manifest_sha256"] = stitch_result.get("source_manifest_sha256")
            elif stitch_result is False:
                report["stitch_status"] = "FAILED"
            else:
                report["stitch_status"] = "COMPLETED"
        except Exception as exc:
            report["stitch_status"] = "FAILED"
            report["stitch_error_type"] = type(exc).__name__
            _safe_pipeline_log("error", "Post-market stitch failed (%s)", type(exc).__name__)

    if report["stitch_status"] not in {"COMPLETED"}:
        report["run_capture_status"] = "DEGRADED"
    if report["pre_stitch_report_status"] != "WRITTEN":
        report["run_capture_status"] = "DEGRADED"
    report["exit_code"] = 0 if report["run_capture_status"] == "HEALTHY" else 1

    report["report_stage"] = "POST_STITCH_UPDATE"
    try:
        write_capture_health_report(report_path, report)
        report["final_report_update_status"] = "WRITTEN"
    except Exception as exc:
        report["final_report_update_status"] = "FAILED"
        report["report_error_type"] = type(exc).__name__
        _safe_pipeline_log("error", "Final capture health report update failed (%s)", type(exc).__name__)
        report["run_capture_status"] = "DEGRADED"
        report["exit_code"] = 1
    return report


def _safe_trace_health_snapshot_from_mapping(raw: dict, run_id: str) -> dict:
    class SnapshotAdapter:
        trace_run_id = run_id

        @staticmethod
        def get_mode5_trace_health_snapshot():
            return raw

    return _safe_trace_health_snapshot(SnapshotAdapter())


class CaptureResourceRegistry:
    """Tracks initialized worker-owning resources for setup-failure cleanup."""

    def __init__(self) -> None:
        self.recorder = None
        self.advisor = None
        self.streamer = None
        self.reporter = None
        self.callback_gate = CallbackAdmissionGate()
        self.dispatch_fence = DispatchAdmissionFence()
        self.recorder_accounting = None
        self.report_path: Optional[Path] = None
        self.date_str: Optional[str] = None
        self.date_compact: Optional[str] = None
        self.data_dir: Optional[Path] = None
        self.excluded_prior_chunk_count = 0
        self.setup_error_type: Optional[str] = None
        self.cleanup_started = False
        self.finalized = False
        self.started = False

    def cleanup_after_setup_failure(self) -> None:
        if not self.started or self.finalized or self.cleanup_started:
            return
        self.cleanup_started = True
        if self.report_path is None or self.date_str is None or self.date_compact is None or self.data_dir is None:
            _safe_pipeline_log("error", "Partial capture cleanup lacks report/session paths")
            return
        try:
            self.report = finalize_capture_session(
                streamer=self.streamer,
                callback_gate=self.callback_gate,
                dispatch_fence=self.dispatch_fence,
                recorder=self.recorder,
                recorder_accounting=self.recorder_accounting,
                advisor=self.advisor,
                report_path=self.report_path,
                date_str=self.date_str,
                date_compact=self.date_compact,
                loop_error_type=self.setup_error_type or "SETUP_FAILURE",
                health_reporting_failures=(self.reporter.reporting_failures if self.reporter else 0),
                health_reporting_last_error_type=(
                    self.reporter.last_reporting_error_type if self.reporter else None
                ),
                allow_stitch=False,
                excluded_prior_chunk_count=self.excluded_prior_chunk_count,
            )
            self.finalized = True
        except BaseException as exc:
            _safe_pipeline_log(
                "error", "Partial capture cleanup failed with %s", type(exc).__name__
            )
            raise

# ----------------- MAIN STREAMING LOOP -----------------
def _run_capture_pipeline(resources: CaptureResourceRegistry):
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
    resources.date_str = today_str
    resources.date_compact = today_compact
    resources.data_dir = data_dir
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    resources.report_path = data_dir / f"capture_health_summary_{today_compact}_UNKNOWN.json"
    resources.started = True
    try:
        prior_chunk_files, last_allocated_chunk_index = scan_existing_level5_chunks(chunks_dir)
    except Exception as exc:
        resources.setup_error_type = "INVALID_EXISTING_CHUNK_SET"
        _safe_pipeline_log(
            "error", "Existing chunk inventory failed closed (%s)", type(exc).__name__
        )
        raise RuntimeError("existing chunk inventory invalid") from exc
    resources.excluded_prior_chunk_count = len(prior_chunk_files)

    # 1. Asynchronous Level-5 Parquet Recorder (Non-blocking Research Tape Writer)
    recorder = UpstoxAsyncParquetRecorder(
        output_dir=chunks_dir,
        chunk_size=2000,
        flush_interval_sec=10.0,
        max_queue_size=50000,
        watermark_ratio=0.8,
        fail_closed_on_saturation=False,
        initial_chunk_index=last_allocated_chunk_index,
    )
    resources.recorder = recorder
    recorder_accounting = RecorderAccountingSink(recorder)
    resources.recorder_accounting = recorder_accounting

    # 2. In-Memory Sentinel Adapter (O(1) latest state coalescing & cross-strike skew gate)
    sentinel_adapter = InMemorySentinelAdapter(
        skew_threshold_ms=250.0,
        staleness_timeout_ms=1000.0,
    )

    # 3. Embedded Sentinel Live Advisory Engine (< 1ms live paper evaluation)
    from core.broker.upstox_broker_adapter import UpstoxBrokerAdapter
    upstox_broker = UpstoxBrokerAdapter(access_token=access_token, is_live_enabled=True)

    sentinel_advisor = SentinelLiveStreamAdvisor(
        adapter=sentinel_adapter,
        spread_veto_threshold=0.04,
        enable_stdout=True,
        advisory_capital=30000.0,
        enable_automated_dispatch=True,
        enable_nifty_live=True,
        broker_adapter=upstox_broker,
    )
    resources.advisor = sentinel_advisor
    trace_health_interval = parse_mode5_trace_health_interval(
        os.environ.get("MODE5_TRACE_HEALTH_INTERVAL_SEC")
    )
    trace_health_reporter = Mode5TraceHealthReporter(
        sentinel_advisor, interval_sec=trace_health_interval
    )
    resources.reporter = trace_health_reporter
    trace_health_reporter.maybe_report(force=True)
    callback_gate = resources.callback_gate

    # 3b. Automatic Prior-Day Reference Level Seeding (Dynamic fail-closed reference bounds)
    try:
        primary_dir = next((p for p in PRIMARY_BASE_DIRS if p.exists()), None)
        search_dir = primary_dir if primary_dir is not None else FALLBACK_BASE_DIR
        if search_dir.exists():
            # Find the most recent session directory that actually contains stitched indices_1m parquet file
            valid_dirs = []
            for d in sorted([x for x in search_dir.iterdir() if x.is_dir() and x.name.startswith("2026-") and x.name < today_str]):
                c_date = d.name.replace("-", "")
                if (d / f"indices_1m_{c_date}.parquet").exists():
                    valid_dirs.append(d)

            if valid_dirs:
                last_session_dir = valid_dirs[-1]
                compact_date = last_session_dir.name.replace("-", "")
                idx_file = last_session_dir / f"indices_1m_{compact_date}.parquet"

                # Check if previous session was a special short Muhurat trading session (e.g. 2026-11-08)
                # For baseline daily ATR volatility hurdles, compute rolling median ATR across regular sessions
                regular_dirs = [d for d in valid_dirs if d.name != "2026-11-08"]
                reg_atr_map = {}
                if regular_dirs:
                    import pandas as pd
                    import numpy as np
                    for target, src_sym in {"NIFTY": "NIFTY 50", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}.items():
                        ranges = []
                        for r_dir in regular_dirs[-5:]:
                            r_compact = r_dir.name.replace("-", "")
                            r_idx_file = r_dir / f"indices_1m_{r_compact}.parquet"
                            if r_idx_file.exists():
                                df_r = pd.read_parquet(r_idx_file)
                                sub_r = df_r[df_r["symbol"] == src_sym]
                                if not sub_r.empty:
                                    ranges.append(float(sub_r["high"].max() - sub_r["low"].min()))
                        if ranges:
                            reg_atr_map[target] = float(np.median(ranges))

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
                            # Use full-day baseline ATR if available so short Muhurat sessions do not distort macro daily ATR hurdles
                            pdr = reg_atr_map.get(target, float(pdh - pdl))
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

    # 3c. Dynamic OptionMate Ground-Truth Level Hot-Reloading with strict session date verification
    try:
        sentinel_advisor.check_and_reload_optionmate_levels(force=True, session_date=today_str)
    except Exception as e:
        logger.warning(f"Failed to auto-load OptionMate daily levels: {e}")

    # 4. Stream Broadcaster (Fan-out to Sentinel in-memory + Async Parquet recorder)
    broadcaster = UpstoxStreamBroadcaster([
        recorder_accounting,
        sentinel_adapter,
        sentinel_advisor,
    ])
    logger.info("🛰️ Initialized UpstoxStreamBroadcaster with Async Recorder and Embedded Sentinel Advisor.")

    last_msg_time = time.time()
    streamer = None
    resources.streamer = streamer

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
                _dispatch_with_lease(
                    resources.dispatch_fence,
                    lambda: broadcaster.dispatch_depth(raw_depth, now_ns=now_mono, now_utc=now_utc),
                )

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
                def update_index_price():
                    if ltp > 0:
                        if key in ("NSE_INDEX|Nifty 50", "NSE_INDEX:Nifty 50"):
                            prices["NIFTY"] = ltp
                        elif key in ("NSE_INDEX|Nifty Bank", "NSE_INDEX:Nifty Bank"):
                            prices["BANKNIFTY"] = ltp
                        elif key in ("BSE_INDEX|SENSEX", "BSE_INDEX:SENSEX"):
                            prices["SENSEX"] = ltp

                _dispatch_with_lease(
                    resources.dispatch_fence,
                    lambda: broadcaster.dispatch_tick(raw_tick, now_ns=now_mono, now_utc=now_utc),
                    update_index_price,
                )

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
            resources.streamer = streamer
            streamer.on("message", callback_gate.wrap(on_message))
            streamer.on("open", callback_gate.wrap(on_open))
            streamer.on("close", callback_gate.wrap(on_close))
            streamer.on("error", callback_gate.wrap(on_error))
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

    pm_window_start = dt_time(9, 8, 45)
    pm_window_end = dt_time(9, 9, 30)
    jit_window_start = dt_time(9, 15, 5)
    jit_window_end = dt_time(9, 15, 30)
    drift_window_start = dt_time(9, 30, 0)

    # Track last subscribed ATM strikes per index for dynamic intraday drift watcher
    last_subscribed_atms: dict[str, float] = {
        "NIFTY": round(prices.get("NIFTY", 24500.0) / 50.0) * 50.0,
        "SENSEX": round(prices.get("SENSEX", 80000.0) / 100.0) * 100.0,
        "BANKNIFTY": round(prices.get("BANKNIFTY", 52200.0) / 100.0) * 100.0,
    }
    last_drift_check_time = time.time()

    def run_market_loop():
        while running:
            now = datetime.now()
            now_ts = time.time()
            trace_health_reporter.maybe_report()

            # Dynamic OptionMate Level Hot-Reload (Throttled internally to 1 Hz with strict session date verification)
            sentinel_advisor.check_and_reload_optionmate_levels(session_date=today_str)

            # Reconcile discrete 5-minute bars driven by wall-clock time
            sentinel_advisor.reconcile_5m_bars(wall_clock_time=now)

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



    logger.info("Starting bounded shutdown, trace health reporting, and post-market stitching...")
    safe_run_id = "".join(
        character for character in str(getattr(sentinel_advisor, "trace_run_id", ""))
        if character.isalnum() or character in "-_"
    )[:64] or "UNKNOWN"
    resources.report_path = data_dir / f"capture_health_summary_{today_compact}_{safe_run_id}.json"

    def cleanup_capture(loop_error_type):
        resources.cleanup_started = True
        try:
            return finalize_capture_session(
                streamer=streamer,
                callback_gate=callback_gate,
                dispatch_fence=resources.dispatch_fence,
                recorder=recorder,
                recorder_accounting=resources.recorder_accounting,
                advisor=sentinel_advisor,
                report_path=resources.report_path,
                date_str=today_str,
                date_compact=today_compact,
                loop_error_type=loop_error_type,
                health_reporting_failures=trace_health_reporter.reporting_failures,
                health_reporting_last_error_type=trace_health_reporter.last_reporting_error_type,
                excluded_prior_chunk_count=resources.excluded_prior_chunk_count,
            )
        finally:
            resources.finalized = True

    try:
        _, exit_code = run_capture_loop_safely(run_market_loop, cleanup_capture)
    except BaseException as exc:
        _safe_pipeline_log("error", "Capture shutdown failed with %s", type(exc).__name__)
        raise
    sys.exit(exit_code)


def main():
    resources = CaptureResourceRegistry()
    try:
        _run_capture_pipeline(resources)
    except BaseException as exc:
        if resources.started and not resources.finalized:
            resources.setup_error_type = type(exc).__name__
            try:
                resources.cleanup_after_setup_failure()
            except BaseException as cleanup_exc:
                _safe_pipeline_log(
                    "error", "Partial cleanup raised %s after setup failure %s",
                    type(cleanup_exc).__name__, type(exc).__name__,
                )
        raise
    finally:
        if resources.started and not resources.finalized and not resources.cleanup_started:
            resources.cleanup_after_setup_failure()

if __name__ == "__main__":
    main()
