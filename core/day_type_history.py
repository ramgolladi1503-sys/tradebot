from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.time_utils import normalize_epoch_seconds, now_ist, now_utc_epoch, parse_ts_ist


def day_type_history_path(base_dir: Path | str | None = None) -> Path:
    if base_dir is None:
        return Path("logs/day_type_events.jsonl")
    return Path(base_dir) / "day_type_events.jsonl"


def _to_ts_ist(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).astimezone(now_ist().tzinfo).isoformat()


def normalize_day_type_event(row: dict[str, Any], *, fill_now: bool = True) -> tuple[dict[str, Any], bool]:
    payload = dict(row or {})
    changed = False

    ts_epoch = normalize_epoch_seconds(payload.get("ts_epoch"))
    if ts_epoch is None:
        ts_epoch = normalize_epoch_seconds(payload.get("ts_ist"))
    if ts_epoch is None:
        ts_epoch = normalize_epoch_seconds(payload.get("ts"))
    if ts_epoch is None:
        ts_epoch = normalize_epoch_seconds(payload.get("timestamp"))
    if ts_epoch is None and fill_now:
        ts_epoch = float(now_utc_epoch())
    if ts_epoch is not None:
        if payload.get("ts_epoch") != ts_epoch:
            changed = True
        payload["ts_epoch"] = float(ts_epoch)

    ts_ist = payload.get("ts_ist")
    if not isinstance(ts_ist, str) or not ts_ist.strip():
        dt_ist = parse_ts_ist(payload.get("ts")) if payload.get("ts") is not None else None
        if dt_ist is None and payload.get("timestamp") is not None:
            dt_ist = parse_ts_ist(payload.get("timestamp"))
        if dt_ist is None and ts_epoch is not None:
            ts_ist = _to_ts_ist(float(ts_epoch))
        elif dt_ist is not None:
            ts_ist = dt_ist.isoformat()
        elif fill_now:
            ts_ist = now_ist().isoformat()
        if ts_ist is not None:
            changed = True
            payload["ts_ist"] = ts_ist

    # Backward-compatible alias for consumers that still expect "ts".
    if payload.get("ts") != payload.get("ts_ist"):
        payload["ts"] = payload.get("ts_ist")
        changed = True

    return payload, changed


def day_type_events_dataframe(rows: list[dict[str, Any]]):
    """
    Build a backward-compatible DataFrame for dashboard rendering.
    Prefers `ts`, falls back to `timestamp`, then `ts_ist`.
    Always returns a DataFrame with a `ts` column.
    """
    import pandas as pd

    df = pd.DataFrame(rows or [])
    if df.empty:
        if "ts" not in df.columns:
            df["ts"] = pd.Series(dtype="datetime64[ns]")
        return df

    if "ts_epoch" in df.columns:
        df["ts_epoch"] = pd.to_numeric(df["ts_epoch"], errors="coerce")

    ts_series = None
    if "ts" in df.columns:
        ts_series = pd.to_datetime(df["ts"], errors="coerce")
    if "timestamp" in df.columns:
        ts_fallback = pd.to_datetime(df["timestamp"], errors="coerce")
        ts_series = ts_fallback if ts_series is None else ts_series.fillna(ts_fallback)
    if "ts_ist" in df.columns:
        ts_ist = pd.to_datetime(df["ts_ist"], errors="coerce")
        ts_series = ts_ist if ts_series is None else ts_series.fillna(ts_ist)

    if ts_series is None:
        ts_series = pd.Series([pd.NaT] * len(df), index=df.index)
    df["ts"] = ts_series
    return df


def append_day_type_event(
    *,
    symbol: str,
    event: str,
    day_type: str,
    confidence: float,
    minutes_since_open: int,
    extra: dict[str, Any] | None = None,
) -> None:
    path = day_type_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_epoch": float(now_utc_epoch()),
        "ts_ist": now_ist().isoformat(),
        "symbol": symbol,
        "event": event,
        "day_type": day_type,
        "confidence": confidence,
        "minutes_since_open": minutes_since_open,
    }
    if extra:
        payload.update(extra)
    payload, _ = normalize_day_type_event(payload, fill_now=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def load_day_type_events(*, backfill: bool = False, max_rows: int | None = None) -> list[dict[str, Any]]:
    path = day_type_history_path()
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    changed = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            normalized, did_change = normalize_day_type_event(parsed, fill_now=False)
            rows.append(normalized)
            changed = changed or did_change

    if backfill and changed:
        ts = int(time.time())
        backup = path.with_name(f"{path.stem}.bak.{ts}{path.suffix}")
        tmp = path.with_name(f"{path.name}.tmp")
        shutil.copy2(path, backup)
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
            f.flush()
        tmp.replace(path)

    if max_rows is not None and max_rows > 0 and len(rows) > max_rows:
        return rows[-max_rows:]
    return rows
