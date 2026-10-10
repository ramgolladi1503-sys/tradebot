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
import math
import urllib.request
import urllib.parse
import threading
import signal
import logging
import fcntl
from datetime import date, datetime, timezone, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

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

def fetch_instruments(snapshot_dir: Path | None = None) -> pd.DataFrame:
    logger.info("Downloading instrument definitions from Upstox...")
    from core.nse_fo_contract_master import UPSTOX_INSTRUMENTS_URL, sha256_bytes
    instruments = []
    source_metadata = {
        "source_url": UPSTOX_INSTRUMENTS_URL,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "tls_verification": "requests_default_certificate_validation",
        "live_identity_eligible": False,
    }
    try:
        import requests
        response = requests.get(
            UPSTOX_INSTRUMENTS_URL,
            headers={"Accept-Encoding": "gzip", "User-Agent": "TradeBot/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        raw_payload = response.content
        if not raw_payload.startswith(b"\x1f\x8b"):
            raise ValueError("Upstox instrument response was not gzip data")
        instruments = json.loads(gzip.decompress(raw_payload).decode("utf-8"))
        if not isinstance(instruments, list) or not instruments:
            raise ValueError("Upstox instrument response contains no records")
        source_metadata.update({
            "sha256": sha256_bytes(raw_payload),
            "file_size_bytes": len(raw_payload),
            "artifact_filename": f"upstox_complete_{datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d')}.json.gz",
            "source_kind": "DIRECT_DOWNLOAD",
        })
        if snapshot_dir is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshot_dir / source_metadata["artifact_filename"]
            temporary = snapshot_path.with_name(snapshot_path.name + ".part")
            try:
                with temporary.open("wb") as stream:
                    stream.write(raw_payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, snapshot_path)
                source_metadata["live_identity_eligible"] = True
            finally:
                temporary.unlink(missing_ok=True)
        logger.info("Downloaded and hashed %s Upstox instruments.", len(instruments))
    except Exception as exc:
        logger.warning("Direct Upstox master unavailable; cached copy is diagnostic only: %s", exc)

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
                    raw_payload = p.read_bytes()
                    if p.suffix == ".gz":
                        instruments = json.loads(gzip.decompress(raw_payload).decode("utf-8"))
                    else:
                        instruments = json.loads(raw_payload.decode("utf-8"))
                    if isinstance(instruments, dict):
                        instruments = list(instruments.values())
                    if not isinstance(instruments, list):
                        raise ValueError("Cached instrument master is not a list")
                    source_metadata = {
                        "source_url": "LOCAL_CACHE",
                        "artifact_filename": p.name,
                        "sha256": sha256_bytes(raw_payload),
                        "file_size_bytes": len(raw_payload),
                        "downloaded_at_utc": None,
                        "tls_verification": "NOT_APPLICABLE_LOCAL_CACHE",
                        "source_kind": "LOCAL_CACHE_NOT_AUTHORIZED_FOR_OPTION_IDENTITY",
                        "live_identity_eligible": False,
                    }
                    break
                except Exception as e:
                    logger.error(f"Failed to read local file {p}: {e}")
    frame = pd.DataFrame(instruments) if instruments else pd.DataFrame()
    frame.attrs["contract_source"] = source_metadata
    return frame

def get_underlying_prices(access_token: str = None) -> dict[str, float]:
    import requests
    token = access_token or get_access_token()
    keys = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank", "BSE_INDEX|SENSEX", "NSE_INDEX|India VIX"]
    encoded_keys = ",".join([urllib.parse.quote(k) for k in keys])
    headers = {"accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}"}
    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={encoded_keys}"
    fallback_prices = {"NIFTY": 24500.0, "BANKNIFTY": 52200.0, "SENSEX": 80000.0, "INDIA_VIX": 14.0}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", {})
            quotes = {
                "NIFTY": data.get("NSE_INDEX:Nifty 50", {}).get("last_price"),
                "BANKNIFTY": data.get("NSE_INDEX:Nifty Bank", {}).get("last_price"),
                "SENSEX": data.get("BSE_INDEX:SENSEX", {}).get("last_price"),
                "INDIA_VIX": data.get("NSE_INDEX:India VIX", {}).get("last_price"),
            }
            valid = all(
                value is not None and math.isfinite(float(value)) and float(value) > 0
                for value in quotes.values()
            )
            if valid:
                return {**{key: float(value) for key, value in quotes.items()}, "__live_authoritative__": True}
    except Exception as e:
        logger.warning(f"Error fetching underlying prices: {e}")
    return {**fallback_prices, "__live_authoritative__": False}

def get_options_subscriptions(
    df_inst: pd.DataFrame,
    underlying_prices: dict[str, float],
    *,
    nse_master=None,
    session_date: date | None = None,
    verified_contracts_out: dict[str, dict] | None = None,
) -> dict[str, str]:
    """Build index/future subscriptions and only NSE-bound option subscriptions.

    NSE is the contract authority for NIFTY and BANKNIFTY options. SENSEX index
    quotes remain available, but NSE evidence cannot authorize BSE options.
    """
    from core.nse_fo_contract_master import contract_key
    subs = {}
    if verified_contracts_out is None:
        verified_contracts_out = {}
    ambiguous_provider_keys: set[str] = set()
    configs = {
        "NIFTY": {"name": "NIFTY", "interval": 50},
        "BANKNIFTY": {"name": "BANKNIFTY", "interval": 100},
    }
    session_date = session_date or datetime.now(ZoneInfo("Asia/Kolkata")).date()

    option_master_schema_ok = {
        "name", "instrument_type", "expiry", "strike_price", "instrument_key", "trading_symbol"
    }.issubset(df_inst.columns)
    if not df_inst.empty and option_master_schema_ok:
        from core.nse_fo_contract_master import _upstox_expiry
        source = df_inst.attrs.get("contract_source", {})
        provider_identity_eligible = (
            source.get("live_identity_eligible") is True
            and underlying_prices.get("__live_authoritative__") is True
        )
        for symbol, cfg in configs.items():
            ltp = underlying_prices.get(symbol, 0.0)
            nearest_expiry = nse_master.nearest_expiry(symbol) if nse_master is not None else None
            if provider_identity_eligible and nearest_expiry is not None and ltp:
                interval = cfg["interval"]
                atm = round(float(ltp) / interval) * interval
                initial_strikes = {atm + (i * interval) for i in range(-10, 11)}
                provider_rows = df_inst[
                    (df_inst["name"].astype(str).str.upper() == cfg["name"])
                    & (df_inst["instrument_type"].astype(str).str.upper().isin(["CE", "PE"]))
                ]
                keyed: dict[str, list[dict]] = {}
                for row in provider_rows.to_dict("records"):
                    expiry = _upstox_expiry(row)
                    try:
                        strike = float(row.get("strike_price"))
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not math.isfinite(strike) or strike <= 0:
                        continue
                    opt_type = str(row.get("instrument_type", "")).strip().upper()
                    if expiry != nearest_expiry or opt_type not in {"CE", "PE"}:
                        continue
                    try:
                        key = contract_key(symbol, expiry, row.get("strike_price"), opt_type)
                    except (TypeError, ValueError):
                        continue
                    keyed.setdefault(key, []).append(row)

                for key, provider_matches in keyed.items():
                    if len(provider_matches) != 1:
                        continue
                    row = provider_matches[0]
                    try:
                        strike_decimal = row.get("strike_price")
                        nse_contract = nse_master.exact_active_match(
                            symbol, nearest_expiry, strike_decimal, row["instrument_type"]
                        )
                    except (KeyError, TypeError, ValueError):
                        nse_contract = None
                    if nse_contract is None:
                        continue
                    instrument_key = str(row.get("instrument_key", "")).strip()
                    trading_symbol = str(row.get("trading_symbol", "")).strip()
                    if not instrument_key.startswith("NSE_FO|") or not trading_symbol:
                        continue
                    evidence = {
                        "contract_key": key,
                        "underlying": symbol,
                        "expiry": nearest_expiry.isoformat(),
                        "strike": format(nse_contract.strike.normalize(), "f"),
                        "option_type": nse_contract.option_type,
                        "nse_instrument_id": nse_contract.instrument_id,
                        "nse_permitted_to_trade": nse_contract.permitted_to_trade,
                        "nse_deleted": nse_contract.deleted,
                        "nse_normal_market_trading_status": nse_contract.normal_market_trading_status,
                        "nse_normal_market_eligible": nse_contract.normal_market_eligible,
                        "upstox_instrument_key": instrument_key,
                        "upstox_trading_symbol": trading_symbol,
                    }
                    if instrument_key in ambiguous_provider_keys:
                        continue
                    if instrument_key in verified_contracts_out:
                        verified_contracts_out.pop(instrument_key, None)
                        subs.pop(instrument_key, None)
                        ambiguous_provider_keys.add(instrument_key)
                        continue
                    verified_contracts_out[instrument_key] = evidence
                    if strike in initial_strikes:
                        subs[instrument_key] = trading_symbol

            # Subscribe the nearest non-expired index future for context only.
            if option_master_schema_ok:
                df_fut = df_inst[
                    (df_inst["name"].astype(str).str.upper() == cfg["name"])
                    & (df_inst["instrument_type"].astype(str).str.upper() == "FUTIDX")
                ].copy()
                futures = []
                for row in df_fut.to_dict("records"):
                    expiry = _upstox_expiry(row)
                    if expiry is not None and expiry >= session_date:
                        futures.append((expiry, row))
                if futures:
                    _expiry, nearest_fut = min(futures, key=lambda item: item[0])
                    subs[str(nearest_fut["instrument_key"])] = str(nearest_fut["trading_symbol"])
                    logger.info("Subscribed near-month Futures: %s (%s)", nearest_fut["trading_symbol"], nearest_fut["instrument_key"])

    subs["NSE_INDEX|Nifty 50"] = "NIFTY 50"
    subs["NSE_INDEX|Nifty Bank"] = "NIFTY BANK"
    subs["BSE_INDEX|SENSEX"] = "SENSEX"
    subs["NSE_INDEX|India VIX"] = "INDIA VIX"
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
    
    # Gather chunks from primary and fallback directories if present
    possible_chunk_dirs = [
        PRIMARY_BASE_DIR / date_str / "chunks",
        FALLBACK_BASE_DIR / date_str / "chunks",
        data_dir / "chunks"
    ]
    
    chunk_files = []
    for cd in possible_chunk_dirs:
        if cd.exists():
            chunk_files.extend(glob.glob(str(cd / "*.parquet")))
    chunk_files = sorted(list(set(chunk_files)))

    out_file = data_dir / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary_file = data_dir / f"stitching_summary_{date_compact}.json"

    # If master stitched file exists and there are new chunks, merge them seamlessly
    if out_file.exists() and out_file.stat().st_size > 0:
        if not chunk_files:
            logger.info(f"[✓] Master stitched file already exists: {out_file.name} ({out_file.stat().st_size / (1024*1024):.2f} MB) and no new chunks to merge.")
            return
        logger.info(f"Existing master stitched file found ({out_file.name}). Merging with {len(chunk_files)} new chunks...")
        chunk_files = [str(out_file)] + [cf for cf in chunk_files if cf != str(out_file)]

    if not chunk_files:
        logger.warning(f"No chunk files found to stitch.")
        return

    dfs = []
    valid_chunks = 0
    skipped_chunks = 0

    for cf in chunk_files:
        try:
            df = pd.read_parquet(cf)
            if df.empty:
                continue
            df["ts"] = df["ts"].astype(float)
            df["token"] = df["token"].astype(str)
            df["symbol"] = df["symbol"].astype(str)
            df["ltp"] = df["ltp"].astype(float)
            df["bid"] = df["bid"].astype(float)
            df["ask"] = df["ask"].astype(float)
            df["vol"] = df["vol"].astype(float)
            df["oi"] = df["oi"].astype(float)
            df["depth"] = df["depth"].astype(str)
            if "contract_authority_manifest_sha256" not in df.columns:
                df["contract_authority_manifest_sha256"] = ""
            df["contract_authority_manifest_sha256"] = df["contract_authority_manifest_sha256"].fillna("").astype(str)
            dfs.append(df)
            valid_chunks += 1
        except Exception as e:
            skipped_chunks += 1
            logger.warning(f"Error reading chunk {cf}: {e}")

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True).sort_values("ts").reset_index(drop=True)
        initial_count = len(df_all)
        df_all = df_all.drop_duplicates(subset=["ts", "token"]).reset_index(drop=True)
        final_count = len(df_all)

        schema = pa.schema([
            ("ts", pa.float64()),
            ("token", pa.string()),
            ("symbol", pa.string()),
            ("ltp", pa.float64()),
            ("bid", pa.float64()),
            ("ask", pa.float64()),
            ("vol", pa.float64()),
            ("oi", pa.float64()),
            ("depth", pa.string()),
            ("contract_authority_manifest_sha256", pa.string())
        ])

        table = pa.Table.from_pandas(df_all, schema=schema)
        pq.write_table(table, out_file, compression="snappy")
        logger.info(f"[✓] Stitched master saved: {out_file.name} ({final_count:,} ticks, {out_file.stat().st_size / (1024*1024):.2f} MB)")

        summary = {
            "date": date_str,
            "total_chunks": len(chunk_files),
            "valid_chunks": valid_chunks,
            "skipped_chunks": skipped_chunks,
            "total_ticks": final_count,
            "duplicates_removed": initial_count - final_count,
            "unique_tokens": df_all["symbol"].nunique(),
            "file_path": str(out_file),
            "stitched_at_utc": datetime.now(timezone.utc).isoformat()
        }
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        # Safe post-stitching cleanup: remove raw chunks if master file is verified
        if out_file.exists() and out_file.stat().st_size > 0 and final_count > 0 and valid_chunks > 0:
            logger.info(f"Master file verified ({final_count:,} ticks). Pruning raw chunks...")
            for cf in chunk_files:
                try:
                    Path(cf).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not remove chunk file {cf}: {e}")
            for cd in possible_chunk_dirs:
                if cd.exists():
                    try:
                        cd.rmdir()
                        logger.info(f"[✓] Successfully pruned chunks directory: {cd}")
                    except Exception as e:
                        logger.debug(f"Could not remove chunks directory {cd}: {e}")

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

    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    today_compact = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
    data_dir = get_today_data_dir()
    session_date = date.fromisoformat(today_str)
    from core.nse_fo_contract_master import fetch_current_nse_fo_contract_master, write_contract_authority_manifest

    df_inst = fetch_instruments(snapshot_dir=data_dir)
    nse_master = None
    nse_metadata = None
    try:
        nse_master, _nse_path, nse_metadata = fetch_current_nse_fo_contract_master(session_date, data_dir)
        logger.info("NSE contract authority loaded: %s (%s)", nse_metadata["artifact_filename"], nse_metadata["file_sha256"])
    except Exception as exc:
        logger.error("NSE option authority unavailable; option subscriptions are disabled: %s", exc)
    prices = get_underlying_prices(access_token)
    verified_contracts = {}
    subscriptions = get_options_subscriptions(
        df_inst,
        prices,
        nse_master=nse_master,
        session_date=session_date,
        verified_contracts_out=verified_contracts,
    )
    manifest_path, manifest_sha256 = write_contract_authority_manifest(
        data_dir,
        session_date=session_date,
        nse_metadata=nse_metadata,
        upstox_metadata=df_inst.attrs.get("contract_source", {}),
        selected_contracts=verified_contracts.values(),
    )
    logger.info(
        "Contract authority manifest=%s sha256=%s bound_option_tokens=%s",
        manifest_path.name,
        manifest_sha256,
        len(verified_contracts),
    )
    logger.info("Contract authority manifest: %s", manifest_path)
    logger.info("Subscribing to %s tokens; option authority bindings=%s.", len(subscriptions), len(verified_contracts))

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
        ("depth", pa.string()),
        ("contract_authority_manifest_sha256", pa.string())
    ])

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
        current_data_dir = get_today_data_dir()
        current_chunks_dir = current_data_dir / "chunks"
        current_chunks_dir.mkdir(parents=True, exist_ok=True)
        
        chunk_file = current_chunks_dir / f"chunk_{today_compact}_{int(now_dt.timestamp() * 1000)}.parquet"
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
        if "contract_authority_manifest_sha256" not in df.columns:
            df["contract_authority_manifest_sha256"] = ""
        df["contract_authority_manifest_sha256"] = df["contract_authority_manifest_sha256"].fillna("").astype(str)

        try:
            table = pa.Table.from_pandas(df, schema=schema)
            pq.write_table(table, chunk_file, compression="snappy")
            logger.info(f"Flushed {len(df)} ticks to {chunk_file.name} in {current_chunks_dir}")
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
                "depth": depth_str,
                "contract_authority_manifest_sha256": manifest_sha256 if key in verified_contracts else "",
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
                latest_spot = prices.get("NIFTY", 0.0)

            if latest_spot > 0:
                try:
                    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions
                    added = refresh_late_day_option_subscriptions(
                        streamer,
                        subscriptions,
                        df_inst,
                        latest_spot,
                        verified_contracts=verified_contracts,
                    )
                    if added > 0:
                        logger.info(f"[Late-Day Refresh Triggered] Added {added} strikes around spot {latest_spot:.1f}")
                        late_day_refresh_done = True
                    else:
                        logger.warning("[Late-Day Refresh] No subscriptions confirmed; will retry during refresh window")
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
