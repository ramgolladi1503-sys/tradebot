"""Upstox instrument dump loader + resolver.

Expected file paths (optional):
  - data/upstox_instruments.json.gz
  - data/upstox_instruments.json
  - data/upstox_instruments.csv

This module is intentionally tolerant of missing files and schema drift.
It returns an empty index when no data is present.
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_CACHE: dict[str, Any] = {"path": None, "index": {}}


def default_instruments_path() -> Path | None:
    try:
        from config import config as cfg
        raw = str(getattr(cfg, "UPSTOX_INSTRUMENTS_PATH", "") or "").strip()
        if raw:
            cfg_path = Path(raw)
            if cfg_path.exists():
                return cfg_path
    except Exception:
        pass
    for name in (
        "data/upstox_instruments.json.gz",
        "data/upstox_instruments.json",
        "data/upstox_instruments.csv",
    ):
        path = Path(name)
        if path.exists():
            return path
    return None


def _coerce_date(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _coerce_strike(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _coerce_opt_type(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("CE", "CALL"):
        return "CE"
    if text in ("PE", "PUT"):
        return "PE"
    return None


def _coerce_underlying(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _load_json(path: Path) -> list[dict]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("data", "instruments", "records"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
    return []


def _load_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def load_instruments(path: Path) -> list[dict]:
    if path.suffix.lower() in (".json", ".gz"):
        return _load_json(path)
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    return []


def build_index(rows: Iterable[dict]) -> dict[tuple, str]:
    index: dict[tuple, str] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = row.get("instrument_key") or row.get("instrument_token") or row.get("instrument_id")
        if not key:
            continue
        underlying = _coerce_underlying(row.get("underlying") or row.get("name") or row.get("symbol"))
        expiry = _coerce_date(row.get("expiry") or row.get("expiry_date"))
        strike = _coerce_strike(row.get("strike_price") or row.get("strike"))
        opt_type = _coerce_opt_type(row.get("option_type") or row.get("right") or row.get("instrument_type"))
        if not (underlying and expiry and strike is not None and opt_type):
            continue
        index[(underlying, expiry, float(strike), opt_type)] = str(key)
    return index


def _ensure_index(path: Path | None = None) -> dict[tuple, str]:
    path = path or default_instruments_path()
    if path is None:
        return {}
    if _CACHE["path"] == str(path) and _CACHE.get("index"):
        return _CACHE["index"]
    rows = load_instruments(path)
    index = build_index(rows)
    _CACHE["path"] = str(path)
    _CACHE["index"] = index
    return index


def resolve_upstox_key(row: dict, instruments_path: Path | None = None) -> str | None:
    if not isinstance(row, dict):
        return None
    underlying = _coerce_underlying(row.get("underlying") or row.get("symbol"))
    expiry = _coerce_date(row.get("expiry_date") or row.get("expiry"))
    strike = _coerce_strike(row.get("strike"))
    opt_type = _coerce_opt_type(row.get("option_type") or row.get("type") or row.get("right"))
    if not (underlying and expiry and strike is not None and opt_type):
        return None
    index = _ensure_index(instruments_path)
    return index.get((underlying, expiry, float(strike), opt_type))
