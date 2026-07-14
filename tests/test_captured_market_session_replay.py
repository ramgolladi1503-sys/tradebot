from __future__ import annotations

import hashlib
import json
import math
import socket
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from core.movement_contract import StrategyContext
from core.orchestrator import _snapshot_symbol_payload
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.session_bar_history import build_session_bar_history_state


CORPUS_ROOT = Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay")
IST = ZoneInfo("Asia/Kolkata")
EXPECTED_SESSION_START = "09:15:00"
EXPECTED_LAST_BAR_START = "15:29:00"
EXPECTED_FULL_SESSION_BARS = 375
KNOWN_HASHES = {
    "20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet": "89a0d9cc98ba6c6decf1d6a1f62fa8b82f80820b51205ae32f222287b7aa550d",
    "20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet": "8dfdc7b8a2c06ce46379d8f7f1cb59d10cd075bd34ceff0643c2b053ccdeb718",
}


@dataclass(frozen=True)
class ReplayCheckpoint:
    label: str
    cutoff: datetime
    expected_available: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(CORPUS_ROOT))


def _discover_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in CORPUS_ROOT.rglob("*")
                if path.is_file() and path.suffix.lower() in {".parquet", ".csv", ".json"}
            ),
            key=lambda item: str(item),
        )
    )


def _path_session_date(relative_path: str) -> str | None:
    first = relative_path.split("/", 1)[0]
    if len(first) == 8 and first.isdigit():
        return f"{first[0:4]}-{first[4:6]}-{first[6:8]}"
    return None


def _is_option_like(text: str) -> bool:
    normalized = f" {str(text or '').upper()} "
    return " CE " in normalized or " PE " in normalized


def _infer_symbol(df: pd.DataFrame, path: Path) -> str | None:
    for column in ("symbol", "instrument", "name"):
        if column in df.columns:
            series = df[column].dropna().astype(str)
            if not series.empty:
                return series.iloc[0]
    return path.stem


def _normalize_timestamps(series: pd.Series) -> tuple[pd.Series, str | None]:
    timestamps = pd.to_datetime(series, errors="coerce")
    if timestamps.dt.tz is None:
        return timestamps.dt.tz_localize(IST), "Asia/Kolkata"
    tz = timestamps.dt.tz
    try:
        tz_name = tz.key  # type: ignore[attr-defined]
    except Exception:
        tz_name = str(tz)
    return timestamps.dt.tz_convert(IST), str(tz_name)


def _timeframe_from_timestamps(timestamps: pd.Series) -> str | None:
    diffs = timestamps.sort_values().diff().dropna()
    if diffs.empty:
        return None
    mode = diffs.mode()
    if mode.empty:
        return None
    delta = mode.iloc[0]
    if delta == pd.Timedelta(minutes=1):
        return "1m"
    return str(delta)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _inspect_market_file(path: Path) -> dict[str, Any]:
    relative_path = _relative(path)
    suffix = path.suffix.lower()
    sha = _sha256(path)
    if relative_path in KNOWN_HASHES:
        assert sha == KNOWN_HASHES[relative_path]

    if suffix == ".json":
        return {
            "absolute_path": str(path),
            "relative_path": relative_path,
            "file_format": "json",
            "file_size": path.stat().st_size,
            "sha256": sha,
            "symbol": None,
            "instrument_key": None,
            "instrument_category": "artifact",
            "session_date_inferred_from_content": None,
            "session_date_inferred_from_path": _path_session_date(relative_path),
            "path_content_date_match_status": "NOT_APPLICABLE",
            "timeframe": None,
            "row_count": None,
            "column_names": [],
            "timestamp_column": None,
            "timestamp_timezone": None,
            "first_timestamp": None,
            "last_timestamp": None,
            "expected_session_start": None,
            "expected_session_end": None,
            "duplicate_timestamp_count": 0,
            "duplicate_full_row_count": 0,
            "out_of_order_count": 0,
            "missing_timestamp_count": 0,
            "missing_ohlc_count": 0,
            "non_finite_ohlc_count": 0,
            "invalid_ohlc_relationship_count": 0,
            "zero_volume_count": 0,
            "missing_volume_count": 0,
            "partial_session_status": None,
            "suitability_classification": "NON_MARKET_ARTIFACT",
            "rejection_reason": "json_manifest_or_report",
        }

    reader = pd.read_parquet if suffix == ".parquet" else pd.read_csv
    df = reader(path)
    columns = [str(column) for column in df.columns]
    timestamp_column = next(
        (column for column in ("timestamp", "ts", "date", "time", "datetime") if column in df.columns),
        None,
    )
    if timestamp_column is None:
        return {
            "absolute_path": str(path),
            "relative_path": relative_path,
            "file_format": suffix.lstrip("."),
            "file_size": path.stat().st_size,
            "sha256": sha,
            "symbol": _infer_symbol(df, path),
            "instrument_key": path.stem,
            "instrument_category": "unknown",
            "session_date_inferred_from_content": None,
            "session_date_inferred_from_path": _path_session_date(relative_path),
            "path_content_date_match_status": "UNKNOWN_CONTENT_DATE",
            "timeframe": None,
            "row_count": int(len(df)),
            "column_names": columns,
            "timestamp_column": None,
            "timestamp_timezone": None,
            "first_timestamp": None,
            "last_timestamp": None,
            "expected_session_start": None,
            "expected_session_end": None,
            "duplicate_timestamp_count": 0,
            "duplicate_full_row_count": int(df.duplicated().sum()),
            "out_of_order_count": 0,
            "missing_timestamp_count": 0,
            "missing_ohlc_count": 0,
            "non_finite_ohlc_count": 0,
            "invalid_ohlc_relationship_count": 0,
            "zero_volume_count": 0,
            "missing_volume_count": 0,
            "partial_session_status": None,
            "suitability_classification": "INVALID_SCHEMA",
            "rejection_reason": "timestamp_column_missing",
        }

    timestamps, tz_name = _normalize_timestamps(df[timestamp_column])
    missing_timestamp_count = int(timestamps.isna().sum())
    valid_timestamps = timestamps.dropna()
    if valid_timestamps.empty:
        return {
            "absolute_path": str(path),
            "relative_path": relative_path,
            "file_format": suffix.lstrip("."),
            "file_size": path.stat().st_size,
            "sha256": sha,
            "symbol": _infer_symbol(df, path),
            "instrument_key": path.stem,
            "instrument_category": "unknown",
            "session_date_inferred_from_content": None,
            "session_date_inferred_from_path": _path_session_date(relative_path),
            "path_content_date_match_status": "UNKNOWN_CONTENT_DATE",
            "timeframe": None,
            "row_count": int(len(df)),
            "column_names": columns,
            "timestamp_column": timestamp_column,
            "timestamp_timezone": tz_name,
            "first_timestamp": None,
            "last_timestamp": None,
            "expected_session_start": None,
            "expected_session_end": None,
            "duplicate_timestamp_count": 0,
            "duplicate_full_row_count": int(df.duplicated().sum()),
            "out_of_order_count": 0,
            "missing_timestamp_count": missing_timestamp_count,
            "missing_ohlc_count": 0,
            "non_finite_ohlc_count": 0,
            "invalid_ohlc_relationship_count": 0,
            "zero_volume_count": 0,
            "missing_volume_count": 0,
            "partial_session_status": None,
            "suitability_classification": "INVALID_TIMESTAMP",
            "rejection_reason": "timestamp_parse_failed",
        }

    duplicate_timestamp_count = int(valid_timestamps.duplicated().sum())
    out_of_order_count = int((valid_timestamps.diff().dropna() < pd.Timedelta(0)).sum())
    timeframe = _timeframe_from_timestamps(valid_timestamps)
    content_dates = sorted({stamp.date().isoformat() for stamp in valid_timestamps})
    content_session_date = content_dates[0] if len(content_dates) == 1 else None
    path_session_date = _path_session_date(relative_path)
    if content_session_date is None:
        date_match_status = "AMBIGUOUS_CONTENT_DATE"
    elif path_session_date is None:
        date_match_status = "MISSING_PATH_DATE"
    elif path_session_date == content_session_date:
        date_match_status = "MATCH"
    else:
        date_match_status = "MISMATCH"

    symbol = _infer_symbol(df, path)
    instrument_key = str(symbol or path.stem)
    option_like = _is_option_like(instrument_key)
    has_ohlc = all(column in df.columns for column in ("open", "high", "low", "close"))
    has_tick_fields = any(column in df.columns for column in ("ltp", "bid", "ask", "depth"))

    missing_ohlc_count = 0
    non_finite_ohlc_count = 0
    invalid_ohlc_relationship_count = 0
    zero_volume_count = 0
    missing_volume_count = 0
    partial_session_status = None
    expected_session_start = None
    expected_session_end = None
    classification = "AMBIGUOUS"
    rejection_reason = None
    instrument_category = "unknown"

    if has_ohlc:
        instrument_category = "option" if option_like else "underlying"
        o = _numeric(df["open"])
        h = _numeric(df["high"])
        low_series = _numeric(df["low"])
        c = _numeric(df["close"])
        missing_ohlc_count = int(pd.concat([o, h, low_series, c], axis=1).isna().any(axis=1).sum())
        ohlc_frame = pd.concat([o, h, low_series, c], axis=1)
        non_finite_ohlc_count = int((~ohlc_frame.apply(lambda column: column.map(lambda value: pd.isna(value) or math.isfinite(float(value))))).any(axis=1).sum())
        invalid_ohlc_relationship_count = int(
            (
                (h < o)
                | (h < c)
                | (h < low_series)
                | (low_series > o)
                | (low_series > c)
                | (low_series > h)
                | (o <= 0)
                | (h <= 0)
                | (low_series <= 0)
                | (c <= 0)
            ).fillna(True).sum()
        )
        if "volume" in df.columns:
            volume = _numeric(df["volume"])
            zero_volume_count = int((volume.fillna(0.0) == 0.0).sum())
            missing_volume_count = int(volume.isna().sum())
        if content_session_date is not None:
            expected_session_start = f"{content_session_date}T{EXPECTED_SESSION_START}+05:30"
            expected_session_end = f"{content_session_date}T{EXPECTED_LAST_BAR_START}+05:30"
        expected_full = bool(
            content_session_date is not None
            and timeframe == "1m"
            and len(valid_timestamps) == EXPECTED_FULL_SESSION_BARS
            and duplicate_timestamp_count == 0
            and out_of_order_count == 0
            and valid_timestamps.iloc[0].strftime("%H:%M:%S") == EXPECTED_SESSION_START
            and valid_timestamps.iloc[-1].strftime("%H:%M:%S") == EXPECTED_LAST_BAR_START
            and valid_timestamps.diff().dropna().eq(pd.Timedelta(minutes=1)).all()
        )
        partial_session_status = bool(not expected_full)
        if missing_ohlc_count or non_finite_ohlc_count or invalid_ohlc_relationship_count:
            classification = "INVALID_OHLC"
            rejection_reason = "ohlc_validation_failed"
        elif out_of_order_count or duplicate_timestamp_count or missing_timestamp_count:
            classification = "INVALID_TIMESTAMP"
            rejection_reason = "timestamp_sequence_invalid"
        elif option_like:
            classification = "OPTION_CANDLE_DATA"
            rejection_reason = "option_candle_excluded_from_underlying_history"
        elif content_session_date is None:
            classification = "AMBIGUOUS"
            rejection_reason = "multi_date_candle_file"
        else:
            classification = "SUITABLE_FULL_UNDERLYING_SESSION" if expected_full else "SUITABLE_PARTIAL_UNDERLYING_SESSION"
    elif has_tick_fields:
        instrument_category = "option" if option_like else "underlying"
        classification = "OPTION_QUOTE_OR_TICK_DATA" if option_like else "UNDERLYING_TICK_DATA"
        rejection_reason = "tick_or_quote_data_not_completed_candles"
    else:
        classification = "INVALID_SCHEMA"
        rejection_reason = "market_columns_missing"

    return {
        "absolute_path": str(path),
        "relative_path": relative_path,
        "file_format": suffix.lstrip("."),
        "file_size": path.stat().st_size,
        "sha256": sha,
        "symbol": symbol,
        "instrument_key": instrument_key,
        "instrument_category": instrument_category,
        "session_date_inferred_from_content": content_session_date,
        "session_date_inferred_from_path": path_session_date,
        "path_content_date_match_status": date_match_status,
        "timeframe": timeframe,
        "row_count": int(len(df)),
        "column_names": columns,
        "timestamp_column": timestamp_column,
        "timestamp_timezone": tz_name,
        "first_timestamp": None if valid_timestamps.empty else valid_timestamps.iloc[0].isoformat(),
        "last_timestamp": None if valid_timestamps.empty else valid_timestamps.iloc[-1].isoformat(),
        "expected_session_start": expected_session_start,
        "expected_session_end": expected_session_end,
        "duplicate_timestamp_count": duplicate_timestamp_count,
        "duplicate_full_row_count": int(df.duplicated().sum()),
        "out_of_order_count": out_of_order_count,
        "missing_timestamp_count": missing_timestamp_count,
        "missing_ohlc_count": missing_ohlc_count,
        "non_finite_ohlc_count": non_finite_ohlc_count,
        "invalid_ohlc_relationship_count": invalid_ohlc_relationship_count,
        "zero_volume_count": zero_volume_count,
        "missing_volume_count": missing_volume_count,
        "partial_session_status": partial_session_status,
        "suitability_classification": classification,
        "rejection_reason": rejection_reason,
    }


@lru_cache(maxsize=1)
def _corpus_manifest_payload() -> dict[str, Any]:
    rows = [_inspect_market_file(path) for path in _discover_files()]
    manifest_json = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    symbols = sorted({str(row["symbol"]) for row in rows if row.get("symbol")})
    categories = sorted({str(row["instrument_category"]) for row in rows if row.get("instrument_category")})
    content_timestamps = [
        row["first_timestamp"]
        for row in rows
        if row.get("first_timestamp")
    ] + [
        row["last_timestamp"]
        for row in rows
        if row.get("last_timestamp")
    ]
    suitable_rows = [
        row
        for row in rows
        if row["suitability_classification"] in {"SUITABLE_FULL_UNDERLYING_SESSION", "SUITABLE_PARTIAL_UNDERLYING_SESSION"}
    ]
    per_symbol_session_counts: dict[str, int] = defaultdict(int)
    for row in suitable_rows:
        per_symbol_session_counts[str(row["symbol"])] += 1
    counts = Counter(row["suitability_classification"] for row in rows)
    return {
        "rows": rows,
        "manifest_hash": manifest_hash,
        "summary": {
            "total_discovered_files": len(rows),
            "total_parquet_files": sum(1 for row in rows if row["file_format"] == "parquet"),
            "total_csv_files": sum(1 for row in rows if row["file_format"] == "csv"),
            "total_json_files": sum(1 for row in rows if row["file_format"] == "json"),
            "total_suitable_full_underlying_sessions": counts["SUITABLE_FULL_UNDERLYING_SESSION"],
            "total_suitable_partial_underlying_sessions": counts["SUITABLE_PARTIAL_UNDERLYING_SESSION"],
            "total_option_candle_files": counts["OPTION_CANDLE_DATA"],
            "total_tick_quote_files": counts["OPTION_QUOTE_OR_TICK_DATA"] + counts["UNDERLYING_TICK_DATA"],
            "total_invalid_schema_files": counts["INVALID_SCHEMA"],
            "total_invalid_timestamp_files": counts["INVALID_TIMESTAMP"],
            "total_invalid_ohlc_files": counts["INVALID_OHLC"],
            "total_ambiguous_files": counts["AMBIGUOUS"],
            "symbols_discovered": symbols,
            "instrument_categories_discovered": categories,
            "earliest_content_timestamp": min(content_timestamps) if content_timestamps else None,
            "latest_content_timestamp": max(content_timestamps) if content_timestamps else None,
            "distinct_session_dates": sorted({row["session_date_inferred_from_content"] for row in suitable_rows if row["session_date_inferred_from_content"]}),
            "per_symbol_session_counts": dict(sorted(per_symbol_session_counts.items())),
            "zero_volume_session_counts": sum(
                1
                for row in suitable_rows
                if int(row.get("zero_volume_count") or 0) == int(row.get("row_count") or 0)
            ),
        },
    }


@lru_cache(maxsize=None)
def _load_candle_rows(path: Path) -> tuple[dict[str, Any], ...]:
    df = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    timestamps, _tz = _normalize_timestamps(df["timestamp"])
    rows: list[dict[str, Any]] = []
    for idx in range(len(df)):
        rows.append(
            {
                "ts": timestamps.iloc[idx].to_pydatetime(),
                "open": float(df.iloc[idx]["open"]),
                "high": float(df.iloc[idx]["high"]),
                "low": float(df.iloc[idx]["low"]),
                "close": float(df.iloc[idx]["close"]),
                "volume": None if "volume" not in df.columns else df.iloc[idx]["volume"],
            }
        )
    return tuple(rows)

@lru_cache(maxsize=None)
def _full_session_range_pct(path: Path) -> float:
    rows = _load_candle_rows(path)
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    close = float(rows[-1]["close"])
    return (max(highs) - min(lows)) / close


@lru_cache(maxsize=1)
def _selected_replay_corpus() -> dict[str, Any]:
    payload = _corpus_manifest_payload()
    suitable = [
        row for row in payload["rows"]
        if row["suitability_classification"] in {"SUITABLE_FULL_UNDERLYING_SESSION", "SUITABLE_PARTIAL_UNDERLYING_SESSION"}
    ]
    full_rows = [row for row in suitable if row["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION"]
    partial_rows = [row for row in suitable if row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"]

    selected: dict[str, dict[str, Any]] = {}

    def _pick(row: dict[str, Any] | None) -> None:
        if row is None:
            return
        selected.setdefault(str(row["relative_path"]), row)

    sorted_suitable = sorted(suitable, key=lambda row: row["relative_path"])
    for row in sorted_suitable:
        _pick(row)
        if len({item["session_date_inferred_from_content"] for item in selected.values() if item["session_date_inferred_from_content"]}) >= 5:
            break

    if full_rows:
        _pick(sorted(full_rows, key=lambda row: row["relative_path"])[0])
        _pick(sorted(full_rows, key=lambda row: row["relative_path"])[-1])
    if partial_rows:
        _pick(sorted(partial_rows, key=lambda row: row["relative_path"])[0])
    for symbol in sorted({row["symbol"] for row in suitable if row.get("symbol")}):
        candidate = next((row for row in sorted_suitable if row.get("symbol") == symbol), None)
        _pick(candidate)

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted_suitable:
        by_symbol[str(row["symbol"])].append(row)
    for rows in by_symbol.values():
        rows.sort(key=lambda item: (item["session_date_inferred_from_content"] or "", item["relative_path"]))
        for first, second in zip(rows, rows[1:]):
            if first["session_date_inferred_from_content"] and second["session_date_inferred_from_content"]:
                first_date = datetime.fromisoformat(first["session_date_inferred_from_content"]).date()
                second_date = datetime.fromisoformat(second["session_date_inferred_from_content"]).date()
                if (second_date - first_date).days == 1:
                    _pick(first)
                    _pick(second)
                    break

    if full_rows:
        range_sorted = sorted(full_rows, key=lambda row: (_full_session_range_pct(CORPUS_ROOT / row["relative_path"]), row["relative_path"]))
        _pick(range_sorted[0])
        _pick(range_sorted[-1])

    selected_rows = sorted(selected.values(), key=lambda row: row["relative_path"])
    return {
        "selection_rule": (
            "deterministic_union_of_first_five_dates + earliest/full/latest/full + earliest partial + per-symbol earliest "
            "+ first consecutive same-symbol pair + min/max full-session range-percent diversity"
        ),
        "rows": selected_rows,
        "excluded_suitable_paths": [
            row["relative_path"] for row in sorted_suitable if row["relative_path"] not in selected
        ],
    }


def _checkpoints_for_row(row: dict[str, Any]) -> list[ReplayCheckpoint]:
    path = CORPUS_ROOT / row["relative_path"]
    rows = _load_candle_rows(path)
    session_open = rows[0]["ts"]
    final_cutoff = rows[-1]["ts"] + timedelta(minutes=1)
    mid_idx = (len(rows) - 1) // 2
    checkpoints = [
        ReplayCheckpoint("before_first_completed_bar", session_open, True),
        ReplayCheckpoint("after_first_completed_bar", session_open + timedelta(minutes=1), True),
        ReplayCheckpoint("after_second_completed_bar", session_open + timedelta(minutes=2), True),
        ReplayCheckpoint("09:30_IST", session_open.replace(hour=9, minute=30), any(item["ts"].strftime("%H:%M") == "09:29" for item in rows)),
        ReplayCheckpoint("10:00_IST", session_open.replace(hour=10, minute=0), any(item["ts"].strftime("%H:%M") == "09:59" for item in rows)),
        ReplayCheckpoint("mid_session", rows[mid_idx]["ts"] + timedelta(minutes=1), True),
        ReplayCheckpoint("final_completed_bar", final_cutoff, True),
    ]
    return checkpoints


def _build_state_from_row(row: dict[str, Any], cutoff: datetime):
    path = CORPUS_ROOT / row["relative_path"]
    rows = _load_candle_rows(path)
    return build_session_bar_history_state(
        symbol=str(row["symbol"]),
        bars=rows,
        cutoff_timestamp=cutoff,
        segment="NSE_FNO",
        source=f"captured:{row['relative_path']}",
        partial_session=bool(row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"),
    )


def _context_from_state(row: dict[str, Any], cutoff: datetime) -> StrategyContext:
    state = _build_state_from_row(row, cutoff)
    warnings: list[str] = []
    payload = _snapshot_symbol_payload(
        {
            "symbol": str(row["symbol"]),
            "spot": state.completed_bar_history[-1].close if state.completed_bar_history else None,
            "ltp": state.completed_bar_history[-1].close if state.completed_bar_history else None,
            "open_price": state.open_price,
            "day_high": state.day_high,
            "day_low": state.day_low,
            "previous_completed_close": state.previous_completed_close,
            "completed_bar_history": state.history_payload(),
            "completed_bar_history_provenance": state.provenance_payload(
                source_component="tests.test_captured_market_session_replay"
            ),
            "vwap": None,
            "atr": None,
            "vol_z": None,
            "vwap_slope": None,
            "orb_state": {"status": "PENDING"},
            "market_open": True,
            "segment": "NSE_FNO",
            "timestamp_ist": cutoff.isoformat(),
            "ltp_ts_epoch": cutoff.timestamp(),
            "option_chain_health": {},
            "quote_source": "captured_candle_replay",
            "feed_health": {"time_sanity": {"ok": True, "reasons": []}},
            "instrument": "OPT",
        },
        warnings,
    )
    return _strategy_context_from_market_symbol(str(row["symbol"]), payload)


def test_recursive_corpus_inventory_is_deterministic_and_known_hashes_match() -> None:
    payload_a = _corpus_manifest_payload()
    payload_b = _corpus_manifest_payload()
    rows = payload_a["rows"]

    assert payload_a["manifest_hash"] == payload_b["manifest_hash"]
    assert rows == sorted(rows, key=lambda row: row["relative_path"])
    row_map = {row["relative_path"]: row for row in rows}
    assert row_map["20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet"]["sha256"] == KNOWN_HASHES["20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet"]
    assert row_map["20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet"]["sha256"] == KNOWN_HASHES["20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet"]


def test_manifest_classifies_options_json_artifacts_and_underlying_sessions_separately() -> None:
    rows = _corpus_manifest_payload()["rows"]
    row_map = {row["relative_path"]: row for row in rows}

    assert row_map["20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet"]["suitability_classification"] in {
        "SUITABLE_FULL_UNDERLYING_SESSION",
        "SUITABLE_PARTIAL_UNDERLYING_SESSION",
    }
    assert row_map["20260709/underlying/NIFTY 23900 CE 14 JUL 26.parquet"]["suitability_classification"] == "OPTION_QUOTE_OR_TICK_DATA"
    assert row_map["20240101/manifests/upstox_fetch_manifest_20240101.json"]["suitability_classification"] == "NON_MARKET_ARTIFACT"


def test_selected_replay_corpus_meets_deterministic_coverage_rule() -> None:
    selection = _selected_replay_corpus()
    rows = selection["rows"]
    dates = {row["session_date_inferred_from_content"] for row in rows if row["session_date_inferred_from_content"]}
    symbols = {row["symbol"] for row in rows if row["symbol"]}

    assert len(rows) >= 5
    assert len(dates) >= 5
    assert len(symbols) >= 2
    assert any(row["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION" for row in rows)
    assert any(row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION" for row in rows)


def test_incremental_and_batch_replay_match_for_selected_sessions() -> None:
    for row in _selected_replay_corpus()["rows"]:
        rows = _load_candle_rows(CORPUS_ROOT / row["relative_path"])
        checkpoints = _checkpoints_for_row(row)
        for checkpoint in checkpoints:
            if not checkpoint.expected_available:
                continue
            batch_state = _build_state_from_row(row, checkpoint.cutoff)
            visible_rows = [item for item in rows if item["ts"] + timedelta(minutes=1) <= checkpoint.cutoff]
            incremental_state = build_session_bar_history_state(
                symbol=str(row["symbol"]),
                bars=visible_rows,
                cutoff_timestamp=checkpoint.cutoff,
                segment="NSE_FNO",
                source=f"captured:{row['relative_path']}",
                partial_session=bool(row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"),
            )
            assert incremental_state.history_hash == batch_state.history_hash
            assert incremental_state.open_price == batch_state.open_price
            assert incremental_state.day_high == batch_state.day_high
            assert incremental_state.day_low == batch_state.day_low
            assert incremental_state.previous_completed_close == batch_state.previous_completed_close


def test_future_mutation_and_truncation_do_not_change_earlier_state() -> None:
    row = _selected_replay_corpus()["rows"][0]
    path = CORPUS_ROOT / row["relative_path"]
    rows = _load_candle_rows(path)
    checkpoint = _checkpoints_for_row(row)[3]
    if not checkpoint.expected_available:
        checkpoint = _checkpoints_for_row(row)[2]

    original = _build_state_from_row(row, checkpoint.cutoff)
    truncated = build_session_bar_history_state(
        symbol=str(row["symbol"]),
        bars=[item for item in rows if item["ts"] + timedelta(minutes=1) <= checkpoint.cutoff],
        cutoff_timestamp=checkpoint.cutoff,
        segment="NSE_FNO",
        source=f"captured:{row['relative_path']}",
        partial_session=bool(row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"),
    )
    mutated_rows = list(rows)
    mutated_rows[-1] = dict(mutated_rows[-1], close=float(mutated_rows[-1]["close"]) + 999.0)
    mutated = build_session_bar_history_state(
        symbol=str(row["symbol"]),
        bars=mutated_rows,
        cutoff_timestamp=checkpoint.cutoff,
        segment="NSE_FNO",
        source=f"captured:{row['relative_path']}",
        partial_session=bool(row["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"),
    )

    assert original.history_hash == truncated.history_hash
    assert original.history_hash == mutated.history_hash
    assert original.day_high == truncated.day_high == mutated.day_high
    assert original.day_low == truncated.day_low == mutated.day_low


def test_context_adapter_exposes_truthful_session_state_and_keeps_undefined_fields_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    row = next(
        row for row in _selected_replay_corpus()["rows"]
        if row["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION"
    )
    checkpoint = _checkpoints_for_row(row)[2]

    def _no_source_parse(*_args, **_kwargs):
        raise AssertionError("runtime context construction must not invoke AST source parsing")

    monkeypatch.setattr("strategies.strategy_registry.build_strategy_profile_integrity_rows", _no_source_parse, raising=True)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network not allowed")))
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(AssertionError("threads not allowed")))

    ctx = _context_from_state(row, checkpoint.cutoff)

    assert ctx.open_price is not None
    assert ctx.day_high is not None
    assert ctx.day_low is not None
    assert ctx.previous_completed_close is not None
    assert ctx.atr_short is None
    assert ctx.atr_long is None
    assert ctx.nearest_support is None
    assert ctx.nearest_resistance is None
    assert ctx.range_width_pct is None
    assert isinstance(ctx.metadata.get("completed_bar_history"), list)
    assert ctx.metadata["completed_bar_history_provenance"]["history_hash"]


def test_consecutive_session_reset_and_cross_symbol_isolation() -> None:
    selection = _selected_replay_corpus()["rows"]
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selection:
        rows_by_symbol[str(row["symbol"])].append(row)
    chosen_symbol_rows = None
    for rows in rows_by_symbol.values():
        rows.sort(key=lambda item: (item["session_date_inferred_from_content"] or "", item["relative_path"]))
        for first, second in zip(rows, rows[1:]):
            if first["session_date_inferred_from_content"] and second["session_date_inferred_from_content"]:
                first_date = datetime.fromisoformat(first["session_date_inferred_from_content"]).date()
                second_date = datetime.fromisoformat(second["session_date_inferred_from_content"]).date()
                if (second_date - first_date).days == 1:
                    chosen_symbol_rows = (first, second)
                    break
        if chosen_symbol_rows:
            break
    assert chosen_symbol_rows is not None

    first, second = chosen_symbol_rows
    first_rows = _load_candle_rows(CORPUS_ROOT / first["relative_path"])
    second_rows = _load_candle_rows(CORPUS_ROOT / second["relative_path"])
    first_final = _build_state_from_row(first, first_rows[-1]["ts"] + timedelta(minutes=1))
    second_empty = build_session_bar_history_state(
        symbol=str(second["symbol"]),
        bars=second_rows,
        cutoff_timestamp=second_rows[0]["ts"],
        segment="NSE_FNO",
        source=f"captured:{second['relative_path']}",
        partial_session=bool(second["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"),
    )
    second_first = _build_state_from_row(second, second_rows[0]["ts"] + timedelta(minutes=1))

    assert first_final.completed_bar_count >= 1
    assert second_empty.completed_bar_count == 0
    assert second_empty.open_price is None
    assert second_empty.day_high is None
    assert second_empty.day_low is None
    assert second_empty.previous_completed_close is None
    assert second_first.completed_bar_count == 1

    other_symbol = next(row for row in selection if row["symbol"] != first["symbol"])
    other_state = _build_state_from_row(other_symbol, _load_candle_rows(CORPUS_ROOT / other_symbol["relative_path"])[0]["ts"] + timedelta(minutes=1))
    assert other_state.symbol != first_final.symbol
    assert other_state.history_hash != first_final.history_hash
