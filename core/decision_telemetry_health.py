from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg
from core.paths import desk_logs_dir
from core.telemetry_streams import decisions_stream_path
from core.time_utils import compute_age_sec, normalize_epoch_seconds, now_ist, now_utc_epoch


def _desk_id(desk_id: str | None = None) -> str:
    return str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")


def decision_write_error_path(desk_id: str | None = None) -> Path:
    return desk_logs_dir(_desk_id(desk_id)) / "decision_write_errors.jsonl"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        module_name = str(getattr(type(value), "__module__", ""))
        if module_name.startswith("numpy") and hasattr(value, "item"):
            return value.item()
    except Exception:
        pass
    return str(value)


def append_decision_write_error(
    *,
    desk_id: str | None = None,
    stream: str,
    exc: Exception | str,
    payload: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload_map = dict(payload or {})
    exc_obj = exc if isinstance(exc, Exception) else Exception(str(exc))
    record = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        "desk_id": _desk_id(desk_id),
        "stream": str(stream or "unknown"),
        "exception_type": type(exc_obj).__name__,
        "exception_message": str(exc_obj),
        "payload_keys": sorted(str(k) for k in payload_map.keys()),
        "payload_min": {
            "event_type": payload_map.get("event_type"),
            "symbol": payload_map.get("symbol"),
            "candidate_id": payload_map.get("candidate_id"),
            "decision_stage": payload_map.get("decision_stage"),
            "cycle_id": payload_map.get("cycle_id"),
            "ts_epoch": payload_map.get("ts_epoch"),
        },
        "context": dict(context or {}),
    }
    path = decision_write_error_path(desk_id=desk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=True,
                default=_json_default,
                separators=(",", ":"),
            )
            + "\n"
        )
    return record


def _load_jsonl_rows(path: Path, *, max_lines: int = 5000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-max_lines:]:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def check_decision_telemetry(desk_id: str | None = None, max_age_sec: float = 60.0) -> dict[str, Any]:
    desk = _desk_id(desk_id)
    path = decisions_stream_path(desk_id=desk)
    now_epoch = now_utc_epoch()
    max_future_skew = float(getattr(cfg, "MAX_CLOCK_SKEW_SEC", 5.0))
    rows = _load_jsonl_rows(path)
    evaluated_rows = [
        row for row in rows if str(row.get("event_type") or "").strip().lower() == "decision_evaluated"
    ]
    valid_rows: list[dict[str, Any]] = []
    recent_valid_rows: list[dict[str, Any]] = []
    for row in evaluated_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        stage = str(row.get("decision_stage") or "").strip()
        ts_epoch = normalize_epoch_seconds(row.get("ts_epoch"))
        if not symbol or not stage or ts_epoch is None:
            continue
        if ts_epoch > (now_epoch + max_future_skew):
            continue
        age_sec = compute_age_sec(ts_epoch, now_epoch)
        if age_sec is None:
            continue
        row_with_age = dict(row)
        row_with_age["_age_sec"] = age_sec
        valid_rows.append(row_with_age)
        if age_sec <= float(max_age_sec):
            recent_valid_rows.append(row_with_age)

    last_valid_ts = None
    if valid_rows:
        try:
            last_valid_ts = max(float(normalize_epoch_seconds(r.get("ts_epoch")) or 0.0) for r in valid_rows)
        except Exception:
            last_valid_ts = None
    last_valid_age = compute_age_sec(last_valid_ts, now_epoch) if last_valid_ts is not None else None

    ok = len(recent_valid_rows) > 0
    if not rows:
        reason = "decisions_stream_missing_or_empty"
    elif not evaluated_rows:
        reason = "decision_evaluated_missing"
    elif not valid_rows:
        reason = "decision_evaluated_invalid_shape"
    elif not ok:
        reason = "decision_evaluated_stale"
    else:
        reason = "ok"
    return {
        "ok": bool(ok),
        "reason": reason,
        "desk_id": desk,
        "path": str(path),
        "max_age_sec": float(max_age_sec),
        "rows_total": len(rows),
        "decision_evaluated_total": len(evaluated_rows),
        "decision_evaluated_valid": len(valid_rows),
        "decision_evaluated_recent": len(recent_valid_rows),
        "last_decision_ts_epoch": last_valid_ts,
        "last_decision_age_sec": last_valid_age,
    }
