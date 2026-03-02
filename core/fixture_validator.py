# Migration note:
# Adds fixture validation utilities for replay harness; can auto-fill missing tradingsymbols.

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

from config import config as cfg
from core.paths import data_root, logs_dir
from core.instrument_symbols import build_option_tradingsymbol


def _iter_option_rows(payload: dict) -> Iterable[dict]:
    for snapshot in payload.get("snapshots", []) or []:
        if not isinstance(snapshot, dict):
            continue
        chain = snapshot.get("option_chain")
        if not isinstance(chain, list):
            continue
        for row in chain:
            if isinstance(row, dict):
                yield row


def ensure_tradingsymbols(payload: dict, *, fixture_name: str | None = None) -> int:
    updates = 0
    log_path = Path(getattr(cfg, "REPLAY_FIXTURE_LOG_PATH", str(logs_dir() / "replay_fixture_symbols.jsonl")))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for row in _iter_option_rows(payload):
        if row.get("tradingsymbol"):
            continue
        symbol = row.get("symbol") or payload.get("symbol")
        expiry = row.get("expiry") or row.get("expiry_date") or row.get("expiryDate") or row.get("exp")
        strike = row.get("strike") or row.get("strike_price") or row.get("strikePrice")
        right = row.get("type") or row.get("option_type") or row.get("right")
        result = build_option_tradingsymbol(symbol, expiry, strike, right)
        if not result.tradingsymbol:
            continue
        row["tradingsymbol"] = result.tradingsymbol
        updates += 1
        event = {
            "ts_epoch": time.time(),
            "fixture": fixture_name,
            "symbol": symbol,
            "expiry": str(expiry) if expiry is not None else None,
            "strike": strike,
            "right": right,
            "tradingsymbol": result.tradingsymbol,
            "reason": "filled_missing_tradingsymbol",
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")
    return updates


def validate_fixture_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    for row in _iter_option_rows(payload):
        if row.get("tradingsymbol"):
            continue
        symbol = row.get("symbol") or payload.get("symbol")
        expiry = row.get("expiry") or row.get("expiry_date") or row.get("expiryDate") or row.get("exp")
        strike = row.get("strike") or row.get("strike_price") or row.get("strikePrice")
        right = row.get("type") or row.get("option_type") or row.get("right")
        result = build_option_tradingsymbol(symbol, expiry, strike, right)
        if not result.tradingsymbol:
            errors.append(
                f"missing tradingsymbol for symbol={symbol} expiry={expiry} strike={strike} right={right} reason={result.reason}"
            )
    return errors
