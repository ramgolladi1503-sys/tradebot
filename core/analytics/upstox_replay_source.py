"""Strict, local-only option OHLC source for outcome replay.

Manifest format (JSON):
{
  "schema_version": 1, "dataset_id": "...", "provider": "upstox",
  "session_date": "YYYY-MM-DD", "interval": "1minute",
  "timezone": "Asia/Kolkata", "timestamp_semantics": "interval_start",
  "instrument_master": {"path": "master.csv", "sha256": "...",
    "size_bytes": 123, "format": "csv"},
  "entries": [{"contract": {"underlying": "NIFTY", "expiry": "...",
    "strike": 25000, "option_type": "CE"}, "instrument_token": "...",
    "path": "relative.csv",
    "sha256": "64 hex chars", "size_bytes": 123,
    "format": "csv"}]
}

Source files must contain timestamp, open, high, low, close columns. Paths are
resolved relative to the manifest; no network or market-data fallback exists.
This is a provenance/consistency contract, not independent source authenticity.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import config as cfg


class ReplaySourceError(ValueError):
    """Raised when an explicit replay source cannot prove its contract."""


def _text(value: Any) -> str:
    return str(value or "").strip()


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_MASTER_BYTES = 64 * 1024 * 1024


def _read_snapshot(path: Path, *, max_bytes: int, error_prefix: str) -> bytes:
    try:
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ReplaySourceError(f"{error_prefix}_read_failed:{type(exc).__name__}") from exc
    if len(payload) > max_bytes:
        raise ReplaySourceError(f"{error_prefix}_too_large")
    return payload


def _contract_value(event: Mapping[str, Any], name: str) -> Any:
    value = event.get(name)
    if value is None:
        metrics = event.get("metrics_snapshot")
        if isinstance(metrics, Mapping):
            value = metrics.get(name)
    return value


def _normalized_contract(event: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _text(_contract_value(event, "symbol")).upper()
    expiry = _text(_contract_value(event, "expiry"))
    option_type = _text(_contract_value(event, "option_type")).upper()
    strike_raw = _contract_value(event, "strike")
    try:
        strike = float(strike_raw)
    except (TypeError, ValueError):
        strike = math.nan
    if not symbol or not expiry or option_type not in {"CE", "PE"} or not math.isfinite(strike):
        raise ReplaySourceError("exact_option_identity_required")
    return {"underlying": symbol, "expiry": expiry, "strike": strike, "option_type": option_type}


def _event_token(event: Mapping[str, Any]) -> str | None:
    raw = _contract_value(event, "instrument_token")
    token = _text(raw)
    return token or None


def _parse_session_date(value: Any) -> str:
    try:
        return date.fromisoformat(_text(value)).isoformat()
    except ValueError as exc:
        raise ReplaySourceError("invalid_session_date") from exc


def _epoch_ms(value: Any, timezone_name: str) -> int:
    if isinstance(value, (int, float)):
        raw = float(value)
        if not math.isfinite(raw) or raw <= 0:
            raise ReplaySourceError("invalid_timestamp")
        return int(raw if raw >= 1_000_000_000_000 else raw * 1000)
    text = _text(value)
    if not text:
        raise ReplaySourceError("missing_timestamp")
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        return _epoch_ms(numeric, timezone_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        return int(parsed.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ReplaySourceError("invalid_timestamp") from exc


def _session_bounds_ms(session_date: str, zone: ZoneInfo) -> tuple[int, int]:
    try:
        open_time = datetime.strptime(_text(getattr(cfg, "MARKET_OPEN_IST", "")), "%H:%M").time()
        close_time = datetime.strptime(_text(getattr(cfg, "MARKET_CLOSE_IST", "")), "%H:%M").time()
        day = date.fromisoformat(session_date)
        open_dt = datetime.combine(day, open_time, tzinfo=zone)
        close_dt = datetime.combine(day, close_time, tzinfo=zone)
    except (TypeError, ValueError) as exc:
        raise ReplaySourceError("invalid_configured_market_session") from exc
    open_ms = int(open_dt.astimezone(timezone.utc).timestamp() * 1000)
    close_ms = int(close_dt.astimezone(timezone.utc).timestamp() * 1000)
    if close_ms <= open_ms:
        raise ReplaySourceError("invalid_configured_market_session")
    return open_ms, close_ms


def _read_rows(payload: bytes, file_format: str) -> list[dict[str, Any]]:
    if file_format == "csv":
        with io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if file_format == "parquet":
        try:
            import pandas as pd

            return pd.read_parquet(io.BytesIO(payload)).to_dict(orient="records")
        except Exception as exc:
            raise ReplaySourceError(f"parquet_read_failed:{type(exc).__name__}") from exc
    raise ReplaySourceError("unsupported_source_format")


class OfflineOptionOHLCManifest:
    """Callable replay loader backed only by hashed local OHLC files."""

    def __init__(self, manifest_path: Path | str) -> None:
        self.manifest_path = Path(manifest_path).expanduser().resolve()
        try:
            manifest_bytes = _read_snapshot(
                self.manifest_path, max_bytes=MAX_MANIFEST_BYTES, error_prefix="manifest"
            )
            payload = json.loads(manifest_bytes.decode("utf-8"))
        except Exception as exc:
            raise ReplaySourceError(f"manifest_read_failed:{type(exc).__name__}") from exc
        if not isinstance(payload, Mapping):
            raise ReplaySourceError("invalid_manifest")
        self.manifest = dict(payload)
        if self.manifest.get("schema_version") != 1:
            raise ReplaySourceError("unsupported_manifest_version")
        self.dataset_id = _text(self.manifest.get("dataset_id"))
        self.provider = _text(self.manifest.get("provider")).lower()
        if not self.dataset_id or self.provider != "upstox":
            raise ReplaySourceError("missing_dataset_provenance")
        self.session_date = _parse_session_date(self.manifest.get("session_date"))
        self.interval = _text(self.manifest.get("interval"))
        if self.manifest.get("timestamp_semantics") != "interval_start":
            raise ReplaySourceError("unsupported_timestamp_semantics")
        self.timezone_name = _text(self.manifest.get("timezone"))
        if self.timezone_name != "Asia/Kolkata":
            raise ReplaySourceError("unsupported_exchange_timezone")
        try:
            self.zone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ReplaySourceError("invalid_timezone") from exc
        entries = self.manifest.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ReplaySourceError("manifest_entries_required")
        self.entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ReplaySourceError("invalid_manifest_entry")
            contract = entry.get("contract")
            if not isinstance(contract, Mapping):
                raise ReplaySourceError("manifest_contract_required")
            normalized = {
                "underlying": _text(contract.get("underlying")).upper(),
                "expiry": _text(contract.get("expiry")),
                "strike": contract.get("strike"),
                "option_type": _text(contract.get("option_type")).upper(),
            }
            try:
                normalized["strike"] = float(normalized["strike"])
            except (TypeError, ValueError) as exc:
                raise ReplaySourceError("invalid_manifest_contract") from exc
            if (
                not normalized["underlying"]
                or not normalized["expiry"]
                or not math.isfinite(normalized["strike"])
                or normalized["option_type"] not in {"CE", "PE"}
            ):
                raise ReplaySourceError("invalid_manifest_contract")
            token = _text(entry.get("instrument_token"))
            if not token:
                raise ReplaySourceError("manifest_instrument_token_required")
            self.entries.append({**dict(entry), "_contract": normalized, "_token": token})
        master = self.manifest.get("instrument_master")
        if not isinstance(master, Mapping):
            raise ReplaySourceError("instrument_master_receipt_required")
        master_path = (self.manifest_path.parent / _text(master.get("path"))).resolve()
        if self.manifest_path.parent not in master_path.parents or not master_path.is_file():
            raise ReplaySourceError("instrument_master_missing_or_outside_manifest")
        master_size = master.get("size_bytes")
        master_hash = _text(master.get("sha256")).lower()
        if not isinstance(master_size, int) or master_size < 0 or not master_hash:
            raise ReplaySourceError("instrument_master_receipt_required")
        master_bytes = _read_snapshot(master_path, max_bytes=MAX_MASTER_BYTES, error_prefix="instrument_master")
        self.master_sha256 = hashlib.sha256(master_bytes).hexdigest()
        if len(master_bytes) != master_size:
            raise ReplaySourceError("instrument_master_size_mismatch")
        if self.master_sha256 != master_hash:
            raise ReplaySourceError("instrument_master_sha256_mismatch")
        if _text(master.get("format") or master_path.suffix.lstrip(".")).lower() != "csv":
            raise ReplaySourceError("unsupported_instrument_master_format")
        with io.TextIOWrapper(io.BytesIO(master_bytes), encoding="utf-8-sig", newline="") as handle:
            master_rows = list(csv.DictReader(handle))
        self.master_contracts: dict[str, dict[str, Any]] = {}
        for row in master_rows:
            token = _text(row.get("instrument_token"))
            if not token or token in self.master_contracts:
                raise ReplaySourceError("duplicate_or_missing_instrument_master_token")
            try:
                master_contract = {
                    "underlying": _text(row.get("underlying")).upper(),
                    "expiry": _text(row.get("expiry")),
                    "strike": float(row.get("strike")),
                    "option_type": _text(row.get("option_type")).upper(),
                }
            except (TypeError, ValueError) as exc:
                raise ReplaySourceError("invalid_instrument_master_row") from exc
            self.master_contracts[token] = master_contract
        for entry in self.entries:
            if self.master_contracts.get(entry["_token"]) != entry["_contract"]:
                raise ReplaySourceError("manifest_contract_not_bound_by_instrument_master")
        self.provenance = {
            "dataset_id": self.dataset_id,
            "provider": self.provider,
            "provenance_status": "OPERATOR_SUPPLIED_UNVERIFIED",
            "source_authenticity_verified": False,
            "event_token_binding": "OPTIONAL_EVENT_TOKEN_VERIFIED_WHEN_PRESENT",
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "instrument_master_sha256": self.master_sha256,
            "session_date": self.session_date,
            "interval": self.interval,
        }
        self.manifest_provenance = dict(self.provenance)

    def __call__(self, event: dict[str, Any], start_ms: int, end_ms: int, interval: str):
        contract = _normalized_contract(event)
        token = _event_token(event)
        event_ts_raw = None
        for key in ("ts_epoch_ms", "reject_ts_epoch_ms", "reject_ts_epoch", "timestamp_epoch_ms", "timestamp"):
            if event.get(key) is not None:
                event_ts_raw = event.get(key)
                break
        if event_ts_raw is None or _epoch_ms(event_ts_raw, self.timezone_name) != int(start_ms):
            raise ReplaySourceError("event_timestamp_binding_mismatch")
        side = _text(_contract_value(event, "side")).upper()
        if side not in {"BUY", "SELL"}:
            raise ReplaySourceError("trade_side_required")
        if _parse_session_date(datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).astimezone(self.zone).date()) != self.session_date:
            raise ReplaySourceError("event_session_mismatch")
        if _interval_ms(interval) != _interval_ms(self.interval):
            raise ReplaySourceError("interval_mismatch")
        session_open_ms, session_close_ms = _session_bounds_ms(self.session_date, self.zone)
        if start_ms < session_open_ms or start_ms >= session_close_ms or end_ms > session_close_ms:
            raise ReplaySourceError("event_window_outside_market_session")
        matches = [
            entry
            for entry in self.entries
            if entry["_contract"] == contract and (token is None or entry["_token"] == token)
        ]
        if len(matches) != 1:
            raise ReplaySourceError("exact_contract_entry_not_unique")
        event_ts_ms = int(start_ms)
        if _ts_grid_origin(event_ts_ms, self.zone, interval) != 0:
            # Never round an event backward into a candle that began before it.
            raise ReplaySourceError("event_not_on_source_bar_boundary")
        entry = matches[0]
        source_path = (self.manifest_path.parent / _text(entry.get("path"))).resolve()
        if source_path.parent != self.manifest_path.parent and self.manifest_path.parent not in source_path.parents:
            raise ReplaySourceError("source_path_outside_manifest_directory")
        if not source_path.is_file():
            raise ReplaySourceError("source_file_missing")
        expected_size = entry.get("size_bytes")
        expected_hash = _text(entry.get("sha256")).lower()
        if not isinstance(expected_size, int) or expected_size < 0 or not expected_hash:
            raise ReplaySourceError("source_integrity_receipt_required")
        source_bytes = _read_snapshot(source_path, max_bytes=MAX_SOURCE_BYTES, error_prefix="source")
        if len(source_bytes) != expected_size:
            raise ReplaySourceError("source_size_mismatch")
        digest = hashlib.sha256(source_bytes).hexdigest()
        if digest != expected_hash:
            raise ReplaySourceError("source_sha256_mismatch")
        file_format = _text(entry.get("format") or source_path.suffix.lstrip(".")).lower()
        rows = _read_rows(source_bytes, file_format)
        interval_ms = _interval_ms(interval)
        parsed: list[dict[str, Any]] = []
        for raw in rows:
            if not all(key in raw for key in ("timestamp", "open", "high", "low", "close")):
                raise ReplaySourceError("ohlc_schema_mismatch")
            timestamp = _epoch_ms(raw.get("timestamp"), self.timezone_name)
            local_day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).astimezone(self.zone).date().isoformat()
            if local_day != self.session_date:
                raise ReplaySourceError("row_session_mismatch")
            if timestamp < session_open_ms or timestamp >= session_close_ms:
                raise ReplaySourceError("source_row_outside_market_session")
            if _ts_grid_origin(timestamp, self.zone, interval) != 0:
                raise ReplaySourceError("source_row_not_on_interval_grid")
            values: dict[str, float] = {}
            for key in ("open", "high", "low", "close"):
                try:
                    value = float(raw[key])
                except (TypeError, ValueError) as exc:
                    raise ReplaySourceError("invalid_ohlc_value") from exc
                if not math.isfinite(value) or value <= 0:
                    raise ReplaySourceError("invalid_ohlc_value")
                values[key] = value
            if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]) or values["low"] > values["high"]:
                raise ReplaySourceError("invalid_ohlc_envelope")
            parsed.append({"time_ms": timestamp, **values})
        parsed.sort(key=lambda row: row["time_ms"])
        timestamps = [row["time_ms"] for row in parsed]
        if len(timestamps) != len(set(timestamps)):
            raise ReplaySourceError("duplicate_source_timestamp")
        window = [row for row in parsed if start_ms <= row["time_ms"] < end_ms]
        expected = list(range(start_ms, end_ms, interval_ms))
        actual = [row["time_ms"] for row in window]
        if actual != expected:
            if len(actual) < len(expected):
                raise ReplaySourceError("truncated_or_gapped_source_window")
            raise ReplaySourceError("misaligned_source_window")
        for row in window:
            row["ref_price"] = row["close"]
            row["source"] = f"upstox_manifest:{self.dataset_id}"
        self.provenance.update(
            {
                "file_sha256": digest,
                "file_size_bytes": len(source_bytes),
                "contract": contract,
                "instrument_token": entry["_token"],
                "event_token_bound": token is not None,
                "identity_binding_mode": (
                    "STRUCTURED_CONTRACT_AND_HASHED_OPERATOR_MASTER"
                    if token is None
                    else "EVENT_TOKEN_AND_STRUCTURED_CONTRACT_AND_HASHED_OPERATOR_MASTER"
                ),
            }
        )
        return window, f"upstox_manifest:{self.dataset_id}"


def _interval_ms(interval: str) -> int:
    text = "".join(str(interval or "").lower().split())
    aliases = {"minute": 1, "1minute": 1, "1min": 1, "1m": 1,
               "2minute": 2, "2min": 2, "2m": 2,
               "3minute": 3, "3min": 3, "3m": 3,
               "5minute": 5, "5min": 5, "5m": 5,
               "10minute": 10, "10min": 10, "10m": 10,
               "15minute": 15, "15min": 15, "15m": 15,
               "30minute": 30, "30min": 30, "30m": 30}
    try:
        return aliases[text] * 60_000
    except KeyError as exc:
        raise ReplaySourceError("unsupported_interval") from exc


def _ts_grid_origin(timestamp_ms: int, zone: ZoneInfo, interval: str) -> int:
    """Return remainder against the configured local exchange-open grid."""
    interval_ms = _interval_ms(interval)
    local = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(zone)
    anchor_ms, _ = _session_bounds_ms(local.date().isoformat(), zone)
    return (timestamp_ms - anchor_ms) % interval_ms
