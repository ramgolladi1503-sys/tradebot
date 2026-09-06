from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

logger = logging.getLogger(__name__)


def execution_audit_path() -> Path:
    path = logs_dir() / "execution_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def execution_audit_latest_path() -> Path:
    path = logs_dir() / "execution_audit_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _iso_utc(epoch: float | None = None) -> str:
    ts = float(epoch if epoch is not None else time.time())
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _blocker_state_from_trade(trade: Any) -> dict[str, Any]:
    blockers: list[str] = []
    for attr in ("hard_blockers", "soft_penalties", "warnings", "blockers", "tradable_reasons_blocking"):
        raw = getattr(trade, attr, None)
        if not isinstance(raw, list):
            continue
        for item in raw:
            text = str(item or "").strip()
            if text and text not in blockers:
                blockers.append(text)
    return {
        "hard_blockers": list(getattr(trade, "hard_blockers", None) or []),
        "soft_penalties": list(getattr(trade, "soft_penalties", None) or []),
        "warnings": list(getattr(trade, "warnings", None) or []),
        "blockers": blockers,
        "execution_status": getattr(trade, "execution_status", None),
        "readiness": getattr(trade, "readiness", None),
    }


def build_execution_audit_event(
    *,
    trade: Any,
    order_action: str,
    guard_result: dict[str, Any] | None = None,
    broker_response: dict[str, Any] | None = None,
    reason: str | None = None,
    ts_epoch: float | None = None,
) -> dict[str, Any]:
    now_epoch = float(ts_epoch if ts_epoch is not None else time.time())
    return {
        "timestamp": _iso_utc(now_epoch),
        "ts_epoch": now_epoch,
        "trade_id": getattr(trade, "trade_id", None),
        "symbol": getattr(trade, "symbol", None),
        "strategy_id": getattr(trade, "strategy_id", None) or getattr(trade, "strategy_name", None) or getattr(trade, "strategy", None),
        "display_entry": _safe_float(getattr(trade, "display_entry", None) if hasattr(trade, "display_entry") else getattr(trade, "entry", None)),
        "execution_entry": _safe_float(getattr(trade, "execution_entry", None) if hasattr(trade, "execution_entry") else getattr(trade, "entry_price", None)),
        "blocker_state": _blocker_state_from_trade(trade),
        "guard_result": _safe_json_copy(guard_result or {}),
        "order_action": str(order_action or "").strip() or "unknown",
        "broker_response": _safe_json_copy(broker_response or {}),
        "reason": str(reason or "").strip() or None,
    }


def append_execution_audit_event(
    *,
    trade: Any,
    order_action: str,
    guard_result: dict[str, Any] | None = None,
    broker_response: dict[str, Any] | None = None,
    reason: str | None = None,
    path: Path | None = None,
    latest_path: Path | None = None,
    ts_epoch: float | None = None,
) -> dict[str, Any]:
    event = build_execution_audit_event(
        trade=trade,
        order_action=order_action,
        guard_result=guard_result,
        broker_response=broker_response,
        reason=reason,
        ts_epoch=ts_epoch,
    )
    target = path or execution_audit_path()
    latest_target = latest_path or execution_audit_latest_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not get_jsonl_writer(target).write(event):
            raise OSError("bounded_execution_audit_write_rejected")
        write_json_atomic(latest_target, event)
    except Exception as exc:
        logger.warning(
            "execution_audit_write_failed trade_id=%s symbol=%s order_action=%s error=%s:%s",
            event.get("trade_id"),
            event.get("symbol"),
            event.get("order_action"),
            type(exc).__name__,
            exc,
        )
    return event


def read_execution_audit_events(
    *,
    path: Path | None = None,
    trade_id: str | None = None,
    symbol: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    target = path or execution_audit_path()
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    trade_key = str(trade_id or "").strip()
    symbol_key = str(symbol or "").strip().upper()
    with target.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = str(raw_line or "").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if trade_key and str(payload.get("trade_id") or "").strip() != trade_key:
                continue
            if symbol_key and str(payload.get("symbol") or "").strip().upper() != symbol_key:
                continue
            out.append(payload)
    if limit > 0:
        out = out[-int(limit) :]
    return out
