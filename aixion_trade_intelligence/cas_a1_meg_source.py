from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo
import json
import math

from .contracts import canonical_json, parse_timestamp


IST = ZoneInfo("Asia/Kolkata")


class CasA1MegSourceError(ValueError):
    pass


def _finite_positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CasA1MegSourceError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise CasA1MegSourceError(f"{field} must be finite and positive")
    return number


def _parse_ts(value: Any, field: str) -> datetime:
    if value in (None, ""):
        raise CasA1MegSourceError(f"{field} is required")
    return parse_timestamp(value, field_name=field)


def _minute_label(value: datetime) -> str:
    return value.astimezone(IST).strftime("%H:%M")


def _date_ist(value: datetime) -> str:
    return value.astimezone(IST).date().isoformat()


def _row_event_id(row: Mapping[str, Any]) -> str:
    semantic = dict(row)
    semantic.pop("source_generated_at_epoch", None)
    return "meg:" + sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def _bar_timestamp(bar: Mapping[str, Any]) -> datetime:
    for key in ("ts", "bar_ts", "bucket_start", "date", "timestamp"):
        if bar.get(key) not in (None, ""):
            return _parse_ts(bar.get(key), f"bar.{key}")
    raise CasA1MegSourceError("completed bar lacks explicit timestamp")


def _bar_symbol(bar: Mapping[str, Any]) -> str:
    return str(bar.get("symbol") or bar.get("instrument") or "").strip().upper()


def _bar_token(bar: Mapping[str, Any]) -> str:
    value = bar.get("instrument_token")
    if value in (None, ""):
        return ""
    return str(value).strip()


def _validate_authority(row: Mapping[str, Any]) -> None:
    expected = {
        "source_kind": "LIVE_CAPTURED_METADATA",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": True,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise CasA1MegSourceError(f"unsafe or non-live MEG metadata: {key}={row.get(key)!r}")
    if row.get("duplicate_interval") is True:
        raise CasA1MegSourceError("duplicate MEG interval rejected")
    for key in (
        "missing_constituents",
        "stale_constituents",
        "duplicate_constituents",
        "misaligned_constituents",
        "late_constituents",
    ):
        value = row.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and list(value):
            raise CasA1MegSourceError(f"MEG interval contains {key}: {list(value)}")


def _identity_map(raw: Mapping[str, Any]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    constituents = raw.get("constituents")
    index = raw.get("index")
    if not isinstance(constituents, list) or not isinstance(index, Mapping):
        raise CasA1MegSourceError("identity contract requires constituents[] and index")
    cmap: dict[str, dict[str, str]] = {}
    by_symbol: dict[str, str] = {}
    for item in constituents:
        if not isinstance(item, Mapping):
            raise CasA1MegSourceError("constituent identity rows must be objects")
        instrument_key = str(item.get("instrument_key") or "").strip()
        symbol = str(item.get("symbol") or "").strip().upper()
        token = str(item.get("instrument_token") or "").strip()
        if not instrument_key or not symbol or not token:
            raise CasA1MegSourceError("constituent identity requires instrument_key, symbol, instrument_token")
        if instrument_key in cmap or symbol in by_symbol:
            raise CasA1MegSourceError("duplicate constituent identity")
        cmap[instrument_key] = {"symbol": symbol, "instrument_token": token}
        by_symbol[symbol] = instrument_key
    index_key = str(index.get("instrument_key") or "").strip()
    index_symbol = str(index.get("symbol") or "").strip().upper()
    index_token = str(index.get("instrument_token") or "").strip()
    if not index_key or not index_symbol or not index_token:
        raise CasA1MegSourceError("index identity requires instrument_key, symbol, instrument_token")
    return cmap, {"instrument_key": index_key, "symbol": index_symbol, "instrument_token": index_token}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CasA1MegSourceError(f"{path}:{lineno}:invalid JSON") from exc
            if not isinstance(value, dict):
                raise CasA1MegSourceError(f"{path}:{lineno}:row must be object")
            rows.append(value)
    return rows


def build_completed_bar_bundle(
    *,
    captured_metadata_rows: Sequence[Mapping[str, Any]],
    identity_contract: Mapping[str, Any],
    session_date: str,
    required_minutes: tuple[str, ...] = ("15:10", "15:14"),
) -> dict[str, Any]:
    """Extract exact completed 1-minute closes from governed MEG captured metadata.

    This bridge does not infer bars from ticks. It only accepts rows already marked as
    LIVE_CAPTURED_METADATA and binds constituent/index symbol + token identity through
    a separate frozen identity contract.
    """
    cmap, index_identity = _identity_map(identity_contract)
    if len(cmap) != 49:
        raise CasA1MegSourceError(f"CAS-A1 identity contract requires exactly 49 constituents, got {len(cmap)}")

    selected: dict[tuple[str, str], dict[str, Any]] = {}
    index_selected: dict[str, dict[str, Any]] = {}
    provider_set: set[str] = set()
    run_ids: set[str] = set()

    for raw in captured_metadata_rows:
        row = dict(raw)
        if str(row.get("session_date") or "") != session_date:
            continue
        _validate_authority(row)
        provider = str(row.get("source") or row.get("provider") or "kite").strip().lower()
        provider_set.add(provider)
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            run_ids.add(run_id)
        row_event_id = _row_event_id(row)

        details = row.get("constituent_bar_details")
        if not isinstance(details, list):
            raise CasA1MegSourceError("constituent_bar_details must be a list")
        for bar in details:
            if not isinstance(bar, Mapping):
                raise CasA1MegSourceError("constituent bar detail must be an object")
            if bar.get("completed") is False or bar.get("is_completed") is False:
                raise CasA1MegSourceError("incomplete constituent bar rejected")
            ts = _bar_timestamp(bar)
            if _date_ist(ts) != session_date:
                raise CasA1MegSourceError("cross-session constituent bar rejected")
            minute = _minute_label(ts)
            if minute not in required_minutes:
                continue
            symbol = _bar_symbol(bar)
            instrument_key = next((key for key, ident in cmap.items() if ident["symbol"] == symbol), "")
            if not instrument_key:
                continue
            expected = cmap[instrument_key]
            token = _bar_token(bar)
            if token != expected["instrument_token"]:
                raise CasA1MegSourceError(
                    f"constituent token mismatch for {instrument_key}: expected {expected['instrument_token']}, got {token}"
                )
            key = (instrument_key, minute)
            if key in selected:
                raise CasA1MegSourceError(f"duplicate exact completed constituent bar: {key}")
            available = _parse_ts(
                row.get("export_timestamp_utc") or row.get("event_timestamp_utc") or row.get("source_generated_at_epoch") or row.get("ts_epoch"),
                "MEG row availability",
            )
            selected[key] = {
                "instrument_key": instrument_key,
                "minute": minute,
                "close": _finite_positive(bar.get("close"), f"{instrument_key}.{minute}.close"),
                "available_time": available.isoformat().replace("+00:00", "Z"),
                "source_event_id": row_event_id,
                "source_provider": provider.upper(),
                "bar_complete": True,
            }

        index_bar = row.get("index_bar")
        if isinstance(index_bar, Mapping):
            if index_bar.get("completed") is False or index_bar.get("is_completed") is False:
                raise CasA1MegSourceError("incomplete index bar rejected")
            ts = _bar_timestamp(index_bar)
            if _date_ist(ts) != session_date:
                raise CasA1MegSourceError("cross-session index bar rejected")
            minute = _minute_label(ts)
            if minute in required_minutes:
                symbol = _bar_symbol(index_bar) or str(row.get("symbol") or "").strip().upper()
                token = _bar_token(index_bar) or str((row.get("live_universe") or {}).get("index_instrument_token") or "").strip()
                if symbol != index_identity["symbol"] or token != index_identity["instrument_token"]:
                    raise CasA1MegSourceError("index identity mismatch in MEG completed bar")
                if minute in index_selected:
                    raise CasA1MegSourceError(f"duplicate exact completed index bar: {minute}")
                available = _parse_ts(
                    row.get("export_timestamp_utc") or row.get("event_timestamp_utc") or row.get("source_generated_at_epoch") or row.get("ts_epoch"),
                    "MEG row availability",
                )
                index_selected[minute] = {
                    "instrument_key": index_identity["instrument_key"],
                    "minute": minute,
                    "close": _finite_positive(index_bar.get("close"), f"index.{minute}.close"),
                    "available_time": available.isoformat().replace("+00:00", "Z"),
                    "source_event_id": row_event_id,
                    "source_provider": provider.upper(),
                    "bar_complete": True,
                }

    if len(provider_set) != 1:
        raise CasA1MegSourceError(f"mixed MEG providers rejected: {sorted(provider_set)}")
    if len(run_ids) > 1:
        raise CasA1MegSourceError(f"mixed MEG run IDs rejected: {sorted(run_ids)}")

    missing = [
        (instrument_key, minute)
        for instrument_key in cmap
        for minute in required_minutes
        if (instrument_key, minute) not in selected
    ]
    if missing:
        raise CasA1MegSourceError(f"missing CAS-A1 MEG constituent bars: {missing}")
    if "15:14" not in index_selected:
        raise CasA1MegSourceError("missing exact NIFTY 15:14 completed MEG bar")

    bars = [selected[(instrument_key, minute)] for instrument_key in cmap for minute in required_minutes]
    bars.append(index_selected["15:14"])
    return {
        "schema_version": 1,
        "evidence_kind": "CAS_A1_MEG_COMPLETED_BAR_BUNDLE",
        "session_date": session_date,
        "run_id": next(iter(run_ids)) if run_ids else "",
        "source_provider": next(iter(provider_set)).upper(),
        "completed_minute_bars": bars,
        "constituent_count": len(cmap),
        "required_minutes": list(required_minutes),
        "tick_to_minute_inference_authorized": False,
        "forward_fill_authorized": False,
        "instrument_substitution_authorized": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
