from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.market_snapshot_schema import validate_market_snapshot
from core.paths import runtime_dir


DEFAULT_MARKET_SNAPSHOT_PATH = runtime_dir() / "snapshots" / "market_snapshot_latest.json"


def _coerce_path(path: str | Path) -> Path:
    return Path(path).expanduser()


def _parse_generated_at(payload: dict[str, Any]) -> float | None:
    text = str(payload.get("generated_at") or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def write_market_snapshot_atomic(
    snapshot: dict,
    path: str | Path = DEFAULT_MARKET_SNAPSHOT_PATH,
) -> Path:
    target = _coerce_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ok, errors = validate_market_snapshot(snapshot)
    if not ok:
        raise ValueError(f"invalid_market_snapshot:{'|'.join(errors)}")
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}.{time.time_ns()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        return target
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def read_market_snapshot(path: str | Path = DEFAULT_MARKET_SNAPSHOT_PATH) -> dict:
    target = _coerce_path(path)
    if not target.exists():
        raise FileNotFoundError(f"market_snapshot_missing:{target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"market_snapshot_parse_error:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("market_snapshot_not_object")
    return payload


def get_market_snapshot_status(
    path: str | Path = DEFAULT_MARKET_SNAPSHOT_PATH,
    now_ts: float | None = None,
    stale_after_sec: float = 15.0,
) -> dict[str, Any]:
    target = _coerce_path(path)
    if now_ts is None:
        now_ts = time.time()
    now_epoch = float(now_ts)
    if not target.exists():
        return {
            "exists": False,
            "valid": False,
            "age_sec": None,
            "state": "missing",
            "errors": ["snapshot_missing"],
        }
    try:
        payload = read_market_snapshot(target)
    except Exception as exc:
        return {
            "exists": True,
            "valid": False,
            "age_sec": None,
            "state": "invalid",
            "errors": [str(exc)],
        }
    valid, errors = validate_market_snapshot(payload)
    generated_ts = _parse_generated_at(payload)
    age_sec = None if generated_ts is None else max(0.0, now_epoch - float(generated_ts))
    if not valid:
        return {
            "exists": True,
            "valid": False,
            "age_sec": age_sec,
            "state": "invalid",
            "errors": list(errors),
        }
    state = "stale" if (age_sec is not None and float(age_sec) > float(stale_after_sec)) else "fresh"
    return {
        "exists": True,
        "valid": True,
        "age_sec": age_sec,
        "state": state,
        "errors": [],
    }
