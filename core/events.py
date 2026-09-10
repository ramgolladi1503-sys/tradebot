from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any
import uuid

from core.paths import logs_dir
from core.telemetry_streams import append_execution_stream_event
from core.time_utils import utc_now
from core.log_writer import get_jsonl_writer

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "password",
    "refresh_token",
    "secret",
    "session_token",
    "token",
}


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
    session_id: str | None = None,
) -> None:
    target = path or events_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload_obj = dict(payload or {})
    payload_event_id = str(payload_obj.get("event_id") or "").strip()
    if not payload_event_id:
        payload_event_id = str(uuid.uuid4())
        payload_obj["event_id"] = payload_event_id
    if session_id is not None and str(payload_obj.get("session_id") or "").strip() == "":
        payload_obj["session_id"] = str(session_id)
    stored_payload = _redact_sensitive_values(payload_obj)
    event = {
        "ts": _iso_utc(ts),
        "type": str(event_type),
        "event_id": payload_event_id,
        "payload": stored_payload,
    }
    get_jsonl_writer(target).write(event)
    try:
        append_execution_stream_event(
            {
                "event_type": str(event_type),
                "event_id": payload_event_id,
                "session_id": stored_payload.get("session_id"),
                "payload": stored_payload,
                "source": "events_jsonl",
            }
        )
    except Exception:
        pass


def _redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if key_text in _SENSITIVE_KEYS or any(token in key_text for token in _SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_sensitive_values(item) for item in value]
    return value


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
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
    target_name = path.name.lower()
    stored_payload = _redact_sensitive_values(payload) if target_name == "events.jsonl" else payload
    # codeql[py/clear-text-storage-sensitive-data]
    data = json.dumps(stored_payload, indent=2, sort_keys=True, ensure_ascii=True)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
    os.replace(tmp, path)
    return path


def write_json_atomic_if_changed(path: Path, payload: dict[str, Any]) -> tuple[Path, bool]:
    """Write JSON atomically only when the serialized payload changed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    target_name = path.name.lower()
    stored_payload = _redact_sensitive_values(payload) if target_name == "events.jsonl" else payload
    # codeql[py/clear-text-storage-sensitive-data]
    data = json.dumps(stored_payload, indent=2, sort_keys=True, ensure_ascii=True)
    digest = sha256(data.encode("utf-8")).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if path.exists():
        try:
            if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() == digest:
                return path, False
        except Exception:
            pass
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
    os.replace(tmp, path)
    try:
        sidecar_tmp = sidecar.with_suffix(sidecar.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
        with sidecar_tmp.open("w", encoding="utf-8") as handle:
            handle.write(digest)
        os.replace(sidecar_tmp, sidecar)
    except Exception:
        pass
    return path, True
