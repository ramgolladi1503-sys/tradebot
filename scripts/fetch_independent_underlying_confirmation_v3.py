#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import random
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


DATA_ROOT = Path("/Users/madhuram/tradebot-data/independent_underlying_confirmation_v3")
RESEARCH_ROOT = Path("research/independent_underlying_confirmation_v3/data_acquisition")
SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")
PRIMARY_WINDOW = ("2023-01-02", "2024-06-28")
EXTENSION_WINDOW = ("2022-01-03", "2022-12-30")
V3_ENDPOINT_FAMILY = "https://api.upstox.com/v3/historical-candle"
SAFETY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "execution_eligibility": False,
    "allowed_for_live_execution": False,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def month_chunks(start: str, end: str) -> list[tuple[str, str]]:
    cur = date.fromisoformat(start).replace(day=1)
    end_date = date.fromisoformat(end)
    chunks = []
    while cur <= end_date:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        chunk_start = max(date.fromisoformat(start), cur)
        chunk_end = min(end_date, date(cur.year, cur.month, last_day))
        chunks.append((chunk_start.isoformat(), chunk_end.isoformat()))
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
    return chunks


def sanitize_error(text: str) -> str:
    return text.replace(os.environ.get("UPSTOX_ACCESS_TOKEN", ""), "[REDACTED]") if os.environ.get("UPSTOX_ACCESS_TOKEN") else text


def load_resolution() -> dict[str, str]:
    path = RESEARCH_ROOT / "underlying_instrument_resolution.json"
    data = json.loads(path.read_text())
    mapping = {}
    for symbol, row in data["resolved"].items():
        if row["resolution_status"] != "UNIQUE_EXACT_INDEX_MATCH":
            raise RuntimeError(f"instrument resolution failed closed for {symbol}")
        mapping[symbol] = row["instrument_key"]
    return mapping


@dataclass(frozen=True)
class FetchResult:
    status: str
    status_code: int | None
    payload_hash: str | None
    error_class: str | None


class HistoricalFetcher:
    def __init__(self, token: str, timeout: int = 30) -> None:
        self.token = token
        self.timeout = timeout
        self.rng = random.Random(20260721)

    def fetch_chunk(self, instrument_key: str, start: str, end: str) -> FetchResult:
        url_key = urllib.parse.quote(instrument_key, safe="")
        url = f"{V3_ENDPOINT_FAMILY}/{url_key}/minutes/1/{end}/{start}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        retryable = {408, 409, 425, 429, 500, 502, 503, 504}
        for attempt in range(4):
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
                if response.status_code == 200:
                    return FetchResult("FETCHED_PENDING_VALIDATION", response.status_code, sha256_bytes(response.content), None)
                if response.status_code not in retryable:
                    return FetchResult("FETCH_FAILED_PERMANENT", response.status_code, None, sanitize_error(response.text[:200]))
                delay = float(response.headers.get("Retry-After") or (2**attempt + self.rng.random()))
                time.sleep(min(delay, 30.0))
            except requests.RequestException as exc:
                if attempt == 3:
                    return FetchResult("FETCH_FAILED_RETRYABLE", None, None, sanitize_error(type(exc).__name__))
                time.sleep(min(2**attempt + self.rng.random(), 30.0))
        return FetchResult("FETCH_FAILED_RETRYABLE", None, None, "retry budget exhausted")


def parse_candles(payload: dict[str, Any], symbol: str, provenance: dict[str, Any]) -> pd.DataFrame:
    records = []
    for candle in payload.get("data", {}).get("candles", []):
        ts = pd.Timestamp(candle[0])
        if ts.tzinfo is None:
            raise ValueError("naive timestamp rejected")
        ts = ts.tz_convert("Asia/Kolkata")
        records.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "oi": float(candle[6]) if len(candle) > 6 else 0.0,
                "source": "upstox",
                "interval": "1minute",
                "data_origin": "upstox_historical_v3",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "provider": "upstox",
                "source_endpoint_family": "historical-candle-v3",
                "fetch_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source_chunk_start": provenance["source_chunk_start"],
                "source_chunk_end": provenance["source_chunk_end"],
                "instrument_key_hash": hashlib.sha256(provenance["instrument_key"].encode()).hexdigest(),
                "data_type": "TRUSTED_UNDERLYING_1M_CANDLES",
            }
        )
    return pd.DataFrame.from_records(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=PRIMARY_WINDOW[0])
    parser.add_argument("--end", default=PRIMARY_WINDOW[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    chunks = month_chunks(args.start, args.end)
    plan = {"window": [args.start, args.end], "chunks": chunks, "symbols": SYMBOLS, "api_version": "V3", "safety_flags": SAFETY_FLAGS}
    write_json(RESEARCH_ROOT / "fetch_plan.json", plan)
    write_text(RESEARCH_ROOT / "fetch_plan.md", f"# Fetch Plan\n\nWindow: `{args.start}` through `{args.end}`\n\nMonthly chunks: `{len(chunks)}`\n")
    if args.dry_run:
        return 0
    if not token:
        write_json(RESEARCH_ROOT / "api_call_audit.json", {"historical_market_data_api_called": False, "credential_available": False, "verdict": "BLOCKED_HISTORICAL_DATA_CREDENTIAL_UNAVAILABLE", "safety_flags": SAFETY_FLAGS})
        return 2
    resolution = load_resolution()
    fetcher = HistoricalFetcher(token)
    states = []
    for symbol in SYMBOLS:
        for start, end in chunks:
            states.append({"symbol": symbol, "chunk_start": start, "chunk_end": end, "state": "PLANNED"})
            result = fetcher.fetch_chunk(resolution[symbol], start, end)
            states.append({"symbol": symbol, "chunk_start": start, "chunk_end": end, **result.__dict__})
    write_json(RESEARCH_ROOT / "chunk_state_manifest.json", {"states": states, "token_logged": False, "safety_flags": SAFETY_FLAGS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
