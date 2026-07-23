from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

_ALLOWED_SOURCE_ROOT = Path("runtime/upstox_candidate_replay")
_REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
_SESSION_ROWS = 375
_SESSION_START = "09:15"
_SESSION_END = "15:29"
_SOURCE_TIMEZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class UpstoxSourceBundle:
    bars: pd.DataFrame
    manifest: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").upper().strip().replace("_", " ")
    if "NIFTY BANK" in text or "BANKNIFTY" in text:
        return "BANKNIFTY"
    if "NIFTY 50" in text or text == "NIFTY" or text.endswith("|NIFTY"):
        return "NIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return text.replace(" ", "")


def _has_symlink_component(path: Path, *, stop_at: Path) -> bool:
    try:
        relative = path.relative_to(stop_at)
    except ValueError:
        return True
    current = stop_at
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _resolve_contained_source(project_root: Path, logical_path: str) -> Path:
    authority = project_root.expanduser().resolve()
    allowed_root = (authority / _ALLOWED_SOURCE_ROOT).resolve()
    if not allowed_root.exists() or not allowed_root.is_dir():
        raise ValueError(
            "certified Upstox source root is missing or not a directory: "
            f"{allowed_root}"
        )
    if _has_symlink_component(allowed_root, stop_at=authority):
        raise ValueError("source authority root contains a symlink component")

    logical = Path(str(logical_path))
    if not logical_path or logical.is_absolute() or ".." in logical.parts:
        raise ValueError(f"unsafe source logical path: {logical_path!r}")
    if logical.parts[: len(_ALLOWED_SOURCE_ROOT.parts)] != _ALLOWED_SOURCE_ROOT.parts:
        raise ValueError(f"source path is outside the allowed logical root: {logical_path}")

    resolved = (authority / logical).resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"source containment failed: {logical_path}") from exc
    if _has_symlink_component(resolved, stop_at=allowed_root):
        raise ValueError(f"source file contains a symlink component: {logical_path}")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"source file is missing or not regular: {logical_path}")
    return resolved


def _timestamps_ist(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="raise")
    timezone = getattr(parsed.dt, "tz", None)
    if timezone is None:
        return parsed.dt.tz_localize(
            _SOURCE_TIMEZONE,
            ambiguous="raise",
            nonexistent="raise",
        )
    return parsed.dt.tz_convert(_SOURCE_TIMEZONE)


def _verify_session_frame(
    frame: pd.DataFrame,
    *,
    record: dict[str, Any],
    logical_path: str,
    requested_symbol: str,
) -> pd.DataFrame:
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(
            f"source required columns missing path={logical_path} columns={sorted(missing)}"
        )
    if len(frame) != _SESSION_ROWS:
        raise ValueError(
            f"source session is incomplete path={logical_path} rows={len(frame)}"
        )

    output = frame.copy()
    output["timestamp"] = _timestamps_ist(output["timestamp"])
    if output["timestamp"].duplicated().any():
        raise ValueError(f"source duplicate timestamps path={logical_path}")
    if not output["timestamp"].is_monotonic_increasing:
        raise ValueError(f"source timestamps are not monotonic path={logical_path}")
    deltas = output["timestamp"].diff().dropna()
    if not (deltas == pd.Timedelta(minutes=1)).all():
        raise ValueError(f"source cadence is not exactly one minute path={logical_path}")

    local_naive = output["timestamp"].dt.tz_localize(None)
    observed_dates = sorted({value.date().isoformat() for value in local_naive})
    declared_session = str(record.get("session_date") or "")
    if observed_dates != [declared_session]:
        raise ValueError(
            "source session date mismatch "
            f"path={logical_path} declared={declared_session} observed={observed_dates}"
        )
    if local_naive.iloc[0].strftime("%H:%M") != _SESSION_START:
        raise ValueError(f"source session start mismatch path={logical_path}")
    if local_naive.iloc[-1].strftime("%H:%M") != _SESSION_END:
        raise ValueError(f"source session end mismatch path={logical_path}")

    observed_symbols = sorted(
        {_normalize_symbol(value) for value in output["symbol"].dropna().unique()}
    )
    declared_symbol = _normalize_symbol(record.get("symbol"))
    if observed_symbols != [requested_symbol] or declared_symbol != requested_symbol:
        raise ValueError(
            "source symbol mismatch "
            f"path={logical_path} declared={declared_symbol} observed={observed_symbols}"
        )

    for column in ("open", "high", "low", "close", "volume"):
        output[column] = pd.to_numeric(output[column], errors="raise")
    if not output[["open", "high", "low", "close", "volume"]].notna().all().all():
        raise ValueError(f"source contains non-finite OHLCV values path={logical_path}")
    if (output[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"source contains non-positive prices path={logical_path}")
    if (output["volume"] < 0).any():
        raise ValueError(f"source contains negative volume path={logical_path}")
    if (output["high"] < output[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError(f"source high violates OHLC ordering path={logical_path}")
    if (output["low"] > output[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"source low violates OHLC ordering path={logical_path}")
    return output


def load_certified_upstox_underlying(
    *,
    source_project_root: str | Path,
    source_manifest_path: str | Path,
    instrument: str,
) -> UpstoxSourceBundle:
    """Load only manifest-declared, file-backed, complete Upstox sessions.

    The source manifest is treated as a selection contract, not as truth by itself.
    Every selected file is contained, hashed, reopened, schema-checked, and compared
    with the declared session and symbol before any rows are returned.
    """

    requested_symbol = _normalize_symbol(instrument)
    if requested_symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError(f"unsupported certified underlying instrument: {instrument}")

    project_root = Path(source_project_root).expanduser().resolve()
    manifest_path = Path(source_manifest_path).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (project_root / manifest_path).resolve()
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ValueError(f"source manifest is missing: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("source_manifest_version") != "v2":
        raise ValueError("certified source manifest v2 is required")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("source manifest records are required")

    selected = [
        record
        for record in records
        if isinstance(record, dict)
        and _normalize_symbol(record.get("symbol")) == requested_symbol
    ]
    if not selected:
        raise ValueError(f"manifest contains no records for {requested_symbol}")
    expected_order = sorted(
        selected,
        key=lambda record: (
            str(record.get("session_date") or ""),
            str(record.get("logical_path") or ""),
            str(record.get("actual_sha256") or ""),
        ),
    )
    if selected != expected_order:
        raise ValueError("selected source manifest records are not deterministically ordered")

    frames: list[pd.DataFrame] = []
    observed_records: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()
    for record in selected:
        session_date = str(record.get("session_date") or "")
        logical_path = str(record.get("logical_path") or "")
        if session_date in seen_sessions:
            raise ValueError(
                f"manifest contains duplicate selected session for {requested_symbol}: {session_date}"
            )
        seen_sessions.add(session_date)
        resolved = _resolve_contained_source(project_root, logical_path)
        actual_sha256 = _sha256_file(resolved)
        declared_sha256 = str(record.get("actual_sha256") or "")
        if actual_sha256 != declared_sha256:
            raise ValueError(
                f"source SHA-256 mismatch path={logical_path} declared={declared_sha256} actual={actual_sha256}"
            )
        byte_size = resolved.stat().st_size
        if record.get("byte_size") is not None and int(record["byte_size"]) != byte_size:
            raise ValueError(f"source byte-size mismatch path={logical_path}")

        frame = pd.read_parquet(resolved)
        if record.get("row_count") is not None and int(record["row_count"]) != len(frame):
            raise ValueError(f"source row-count metadata mismatch path={logical_path}")
        verified = _verify_session_frame(
            frame,
            record=record,
            logical_path=logical_path,
            requested_symbol=requested_symbol,
        )
        record_id = str(record.get("source_record_id") or "")
        verified["source_logical_path"] = logical_path
        verified["source_sha256"] = actual_sha256
        verified["source_manifest_record_id"] = record_id
        frames.append(verified)
        observed_records.append(
            {
                "session_date": session_date,
                "symbol": requested_symbol,
                "logical_path": logical_path,
                "actual_sha256": actual_sha256,
                "byte_size": byte_size,
                "row_count": len(verified),
                "source_record_id": record_id,
            }
        )

    bars = pd.concat(frames, ignore_index=True)
    bars = bars.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if bars["timestamp"].duplicated().any():
        raise ValueError("certified corpus contains duplicate timestamps after concatenation")
    if len(bars) != len(selected) * _SESSION_ROWS:
        raise AssertionError("certified corpus row conservation failed")

    adapter_manifest = {
        "mode": "ML_STRATEGY_DISCOVERY_UPSTOX_SOURCE_ADAPTER_V1",
        "candidate_id": f"ALL_{requested_symbol}_CERTIFIED_SESSIONS",
        "decision": "CERTIFIED_UPSTOX_UNDERLYING_SOURCE_BOUND",
        "reason": "manifest-selected files were contained, hashed, reopened, and independently schema/session checked",
        "timestamp": str(bars["timestamp"].max()),
        "source": str(manifest_path.name),
        "instrument": requested_symbol,
        "timestamp_semantics": "START",
        "source_timezone": _SOURCE_TIMEZONE,
        "bar_interval_minutes": 1,
        "record_count": len(observed_records),
        "row_count": len(bars),
        "session_count": bars["timestamp"].dt.date.nunique(),
        "coverage_start": str(bars["timestamp"].min()),
        "coverage_end": str(bars["timestamp"].max()),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "observed_record_set_hash": _canonical_hash(observed_records),
        "records": observed_records,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "allowed_for_live_execution": False,
        "append": False,
    }
    return UpstoxSourceBundle(bars=bars, manifest=adapter_manifest)
