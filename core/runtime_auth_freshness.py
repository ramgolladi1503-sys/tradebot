from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.paths import logs_dir


STALE_AUTH_SUPERSEDED_BY_HEALTH = "stale_auth_required_superseded_by_fresh_auth_health"


def latest_auth_health(path: str | Path | None = None, *, max_lines: int = 200) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else logs_dir() / "auth_health.jsonl"
    if not target.exists():
        return {}
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return {}
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    if not rows:
        return {}
    return max(rows, key=lambda row: _float_or_zero(row.get("ts_epoch")))


def resolve_runtime_auth_snapshot(
    auth_state_payload: dict[str, Any] | None,
    *,
    latest_health_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(auth_state_payload or {})
    health = dict(latest_health_payload or {})
    state = str(payload.get("status") or payload.get("auth_state") or "").strip().upper()
    state_ts = _float_or_none(payload.get("ts_epoch"))
    health_ts = _float_or_none(health.get("ts_epoch"))
    health_state = str(health.get("auth_state") or "").strip().upper()
    health_ok = health.get("ok") is True and health_state == "OK"

    if state == "AUTH_REQUIRED" and health_ok and _is_newer(health_ts, state_ts):
        return {
            "auth_ok": True,
            "auth_state": "OK",
            "auth_reason": "",
            "auth_source": str(health.get("source") or "auth_health"),
            "auth_state_ts_epoch": state_ts,
            "auth_health_ts_epoch": health_ts,
            "auth_stale_reason": STALE_AUTH_SUPERSEDED_BY_HEALTH,
            "stale_auth_reason": str(payload.get("reason") or payload.get("error") or "").strip(),
        }

    if not state:
        return {
            "auth_ok": True,
            "auth_state": "UNKNOWN",
            "auth_reason": "",
            "auth_source": "none",
            "auth_state_ts_epoch": state_ts,
            "auth_health_ts_epoch": health_ts,
            "auth_stale_reason": "",
            "stale_auth_reason": "",
        }

    return {
        "auth_ok": state == "OK",
        "auth_state": state,
        "auth_reason": str(payload.get("reason") or payload.get("error") or "").strip(),
        "auth_source": str(payload.get("source") or "auth_state"),
        "auth_state_ts_epoch": state_ts,
        "auth_health_ts_epoch": health_ts,
        "auth_stale_reason": "",
        "stale_auth_reason": "",
    }


def _is_newer(left: float | None, right: float | None) -> bool:
    if left is None:
        return False
    if right is None:
        return True
    return left >= right


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0
