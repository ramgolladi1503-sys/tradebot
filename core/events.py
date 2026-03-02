from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from core.paths import logs_dir
from core.time_utils import utc_now


def events_path() -> Path:
    path = logs_dir() / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _iso_utc(ts: datetime | float | int | None = None) -> str:
    if isinstance(ts, datetime):
        dt = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if ts is None:
        dt = utc_now()
    else:
        raw = float(ts)
        if raw > 1_000_000_000_000:
            raw = raw / 1000.0
        dt = datetime.fromtimestamp(raw, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def append_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    ts: datetime | float | int | None = None,
    path: Path | None = None,
) -> None:
    target = path or events_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": _iso_utc(ts),
        "type": str(event_type),
        "payload": dict(payload or {}),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")


def read_events(
    *,
    path: Path | None = None,
    event_type: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    target = path or events_path()
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if event_type and str(row.get("type") or "") != str(event_type):
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if run_id and str(payload.get("run_id") or "") != str(run_id):
                continue
            out.append(row)
    return out


def write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path
