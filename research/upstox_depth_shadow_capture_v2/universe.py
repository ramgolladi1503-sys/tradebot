from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SPOT_SPECS = {
    "NIFTY": ("NIFTY 50", "INDEX"),
    "BANKNIFTY": ("NIFTY BANK", "INDEX"),
    "SENSEX": ("SENSEX", "INDEX"),
    "INDIA_VIX": ("INDIA VIX", "INDEX"),
}
OPTION_NAMES = ("NIFTY", "BANKNIFTY", "SENSEX")
FUTURE_NAMES = ("NIFTY", "BANKNIFTY", "SENSEX")


def _parse_expiry(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc).date()
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported expiry value: {value}")


def _instrument_key(record: Mapping[str, Any]) -> str:
    value = record.get("instrument_key") or record.get("instrument_token")
    key = str(value or "").strip()
    if not key or "|" not in key:
        raise ValueError(f"instrument record lacks a valid instrument key: {record}")
    return key


def _minimal_record(record: Mapping[str, Any], *, role: str, expiry: date | None) -> dict[str, Any]:
    return {
        "instrument_key": _instrument_key(record),
        "role": role,
        "name": str(record.get("name") or ""),
        "trading_symbol": str(record.get("trading_symbol") or record.get("tradingsymbol") or ""),
        "instrument_type": str(record.get("instrument_type") or ""),
        "exchange": str(record.get("exchange") or record.get("segment") or ""),
        "expiry": expiry.isoformat() if expiry else None,
        "strike_price": record.get("strike_price"),
        "lot_size": record.get("lot_size"),
    }


def build_shadow_universe(
    instruments: Iterable[Mapping[str, Any]],
    *,
    as_of_date: date,
    future_expiry_count: int = 2,
    maximum_instruments: int = 2000,
) -> dict[str, Any]:
    if future_expiry_count <= 0:
        raise ValueError("future_expiry_count must be positive")
    if maximum_instruments <= 0:
        raise ValueError("maximum_instruments must be positive")
    records = [dict(record) for record in instruments]
    if not records:
        raise ValueError("instrument master is empty")

    selected: list[dict[str, Any]] = []
    missing: list[str] = []

    for role, (trading_symbol, instrument_type) in SPOT_SPECS.items():
        matches = [
            record
            for record in records
            if str(record.get("trading_symbol") or record.get("tradingsymbol") or "") == trading_symbol
            and str(record.get("instrument_type") or "").upper() == instrument_type
        ]
        if not matches:
            missing.append(f"SPOT:{role}")
            continue
        matches.sort(key=lambda record: _instrument_key(record))
        selected.append(_minimal_record(matches[0], role=f"SPOT:{role}", expiry=None))

    for name in OPTION_NAMES:
        candidates: list[tuple[date, Mapping[str, Any]]] = []
        for record in records:
            if str(record.get("name") or "").upper() != name:
                continue
            if str(record.get("instrument_type") or "").upper() not in {"CE", "PE"}:
                continue
            expiry = _parse_expiry(record.get("expiry"))
            if expiry is not None and expiry >= as_of_date:
                candidates.append((expiry, record))
        if not candidates:
            missing.append(f"NEAREST_OPTIONS:{name}")
            continue
        nearest = min(expiry for expiry, _ in candidates)
        for expiry, record in candidates:
            if expiry == nearest:
                selected.append(
                    _minimal_record(record, role=f"NEAREST_OPTION:{name}", expiry=expiry)
                )

    for name in FUTURE_NAMES:
        candidates: list[tuple[date, Mapping[str, Any]]] = []
        for record in records:
            if str(record.get("name") or "").upper() != name:
                continue
            if str(record.get("instrument_type") or "").upper() != "FUT":
                continue
            expiry = _parse_expiry(record.get("expiry"))
            if expiry is not None and expiry >= as_of_date:
                candidates.append((expiry, record))
        expiries = sorted({expiry for expiry, _ in candidates})[:future_expiry_count]
        for expiry, record in candidates:
            if expiry in expiries:
                selected.append(
                    _minimal_record(record, role=f"FUTURE:{name}", expiry=expiry)
                )

    if missing:
        raise ValueError(f"instrument master cannot satisfy shadow universe: {sorted(missing)}")

    by_key: dict[str, dict[str, Any]] = {}
    for record in selected:
        key = str(record["instrument_key"])
        existing = by_key.get(key)
        if existing is not None and existing != record:
            raise ValueError(f"conflicting duplicate instrument key: {key}")
        by_key[key] = record
    ordered = [by_key[key] for key in sorted(by_key)]
    if len(ordered) > maximum_instruments:
        raise ValueError(
            f"shadow universe has {len(ordered)} instruments; limit is {maximum_instruments}"
        )

    role_counts: dict[str, int] = {}
    for record in ordered:
        role = str(record["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
    return {
        "campaign_id": "UPSTOX_DEPTH_SHADOW_CAPTURE_V2",
        "classification": "SHADOW_UNIVERSE_FROZEN_FOR_SESSION",
        "as_of_date": as_of_date.isoformat(),
        "instrument_count": len(ordered),
        "instrument_keys": [record["instrument_key"] for record in ordered],
        "role_counts": dict(sorted(role_counts.items())),
        "instruments": ordered,
        "maximum_instruments": maximum_instruments,
        "selection_uses_outcomes": False,
        "execution_allowed": False,
    }


def write_universe_atomic(path: Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, destination)
