from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import config as cfg
from core.paths import desk_logs_dir
from core.time_utils import now_ist, now_utc_epoch
from core.log_writer import get_jsonl_writer


def _desk_id(desk_id: str | None = None) -> str:
    return str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")


def _stream_path(filename: str, *, desk_id: str | None = None) -> Path:
    return desk_logs_dir(_desk_id(desk_id)) / filename


def candidates_stream_path(desk_id: str | None = None) -> Path:
    return _stream_path("candidates.jsonl", desk_id=desk_id)


def decisions_stream_path(desk_id: str | None = None) -> Path:
    return _stream_path("decisions.jsonl", desk_id=desk_id)


def execution_stream_path(desk_id: str | None = None) -> Path:
    return _stream_path("execution.jsonl", desk_id=desk_id)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        module_name = str(getattr(type(value), "__module__", ""))
        if module_name.startswith("numpy"):
            if hasattr(value, "item"):
                return value.item()
            return str(value)
    except Exception:
        pass
    return str(value)


def compute_candidate_id(payload: Mapping[str, Any]) -> str:
    ts_epoch = payload.get("ts_epoch")
    if ts_epoch is None:
        ts_epoch = payload.get("timestamp")
    try:
        ts_bucket = int(float(ts_epoch or 0.0))
    except Exception:
        ts_bucket = 0
    stable = {
        "symbol": str(payload.get("symbol") or "").upper(),
        "cycle_id": str(payload.get("cycle_id") or ""),
        "instrument": str(payload.get("instrument") or "OPT").upper(),
        "strategy": str(payload.get("strategy") or payload.get("strategy_id") or ""),
        "strike": payload.get("strike"),
        "expiry_date": str(payload.get("expiry_date") or payload.get("expiry") or ""),
        "option_type": str(payload.get("option_type") or payload.get("right") or ""),
        "ts_bucket": ts_bucket,
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=_json_default)
    return "cand_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    if not get_jsonl_writer(path).write(dict(payload)):
        raise OSError("bounded_telemetry_write_rejected")


def append_candidate_stream_event(payload: Mapping[str, Any], *, desk_id: str | None = None) -> dict[str, Any]:
    record = dict(payload or {})
    record.setdefault("event_type", "candidate_seen")
    record.setdefault("ts_epoch", float(now_utc_epoch()))
    record.setdefault("ts_ist", now_ist().isoformat())
    record.setdefault("symbol", str(record.get("symbol") or "").upper())
    record["candidate_id"] = str(record.get("candidate_id") or compute_candidate_id(record))
    _append_jsonl(candidates_stream_path(desk_id=desk_id), record)
    return record


def append_decision_stream_event(payload: Mapping[str, Any], *, desk_id: str | None = None) -> dict[str, Any]:
    record = dict(payload or {})
    record.setdefault("event_type", "decision_evaluated")
    record.setdefault("ts_epoch", float(now_utc_epoch()))
    record.setdefault("ts_ist", now_ist().isoformat())
    record.setdefault("symbol", str(record.get("symbol") or "").upper())
    record["candidate_id"] = str(record.get("candidate_id") or compute_candidate_id(record))
    record["allowed"] = bool(record.get("allowed", False))
    if "blockers" not in record:
        record["blockers"] = []
    elif not isinstance(record.get("blockers"), list):
        record["blockers"] = [str(record.get("blockers"))]
    _append_jsonl(decisions_stream_path(desk_id=desk_id), record)
    return record


def append_execution_stream_event(payload: Mapping[str, Any], *, desk_id: str | None = None) -> dict[str, Any]:
    record = dict(payload or {})
    record.setdefault("ts_epoch", float(now_utc_epoch()))
    record.setdefault("ts_ist", now_ist().isoformat())
    _append_jsonl(execution_stream_path(desk_id=desk_id), record)
    return record


def iter_recent_events(
    path: Path,
    *,
    now_epoch: float | None = None,
    max_age_sec: float = 900.0,
    event_types: Iterable[str] | None = None,
    max_lines: int = 2000,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    now_val = float(now_epoch if now_epoch is not None else now_utc_epoch())
    types_filter = {str(x).strip().lower() for x in (event_types or []) if str(x).strip()}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in reversed(lines[-max_lines:]):
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("event_type") or "").strip().lower()
        if types_filter and event_type not in types_filter:
            continue
        try:
            ts_epoch = float(payload.get("ts_epoch") or 0.0)
        except Exception:
            continue
        if ts_epoch <= 0:
            continue
        if (now_val - ts_epoch) > float(max_age_sec):
            continue
        out.append(payload)
    out.reverse()
    return out
