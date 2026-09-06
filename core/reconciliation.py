from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from config import config as cfg
from core.order_reconciliation_daemon import OrderReconciliationDaemon
from core.orders.state_machine import OrderStateMachine
from core.paths import logs_dir
from core.trade_store import fetch_open_positions_dict
from core.trade_state_machine import (
    TradeLifecycleState,
    record_trade_lifecycle_observation,
    rehydrate_trade_lifecycle,
)


logger = logging.getLogger(__name__)

EXCHANGE_TZ = ZoneInfo(str(getattr(cfg, "EXCHANGE_TZ", "Asia/Kolkata") or "Asia/Kolkata"))
_DEFAULT_ANALYTICS_BASE = Path(
    str(getattr(cfg, "ANALYTICS_RUNTIME_DIR", "runtime/analytics") or "runtime/analytics")
)


def _env_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _skip_broker_auth_resolution() -> bool:
    mode = str(
        getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM"
    ).strip().upper()
    dry_run_enabled = bool(getattr(cfg, "DRY_RUN", False) or _env_flag_enabled("DRY_RUN"))
    return mode in {"SIM", "DRY_RUN"} or dry_run_enabled


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        out = float(value)
        if out != out:  # NaN
            return default
        return out
    except Exception:
        return default


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_ts_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = _norm_text(value)
    if not text:
        return datetime.now(tz=timezone.utc)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except Exception:
        try:
            raw = float(text)
            if raw > 10_000_000_000:
                raw = raw / 1000.0
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except Exception:
            return datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_analytics_base(base_dir: Path | str | None = None) -> Path:
    candidate = Path(base_dir) if base_dir is not None else _DEFAULT_ANALYTICS_BASE
    resolved = candidate.resolve()
    # Guardrail: reconciliation storage must live under a runtime/analytics directory.
    parts = list(resolved.parts)
    if len(parts) < 2 or parts[-2:] != ["runtime", "analytics"]:
        raise ValueError(f"invalid_reconciliation_base_dir:{resolved}:must_end_with_runtime/analytics")
    return resolved


def _atomic_append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{time.time_ns()}")
    with tmp.open("w", encoding="utf-8") as handle:
        if existing:
            handle.write(existing)
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path


def _append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    from core.log_writer import get_jsonl_writer
    if not get_jsonl_writer(path).write(payload):
        raise OSError("bounded_reconciliation_write_rejected")
    return path


def _event_day_path(base_dir: Path, ts_utc: datetime) -> Path:
    day_key = ts_utc.astimezone(EXCHANGE_TZ).date().isoformat()
    return base_dir / day_key / "events.jsonl"


def _resolve_runtime_reconciliation_log_path(path: Path | str | None = None) -> Path:
    if path is None:
        return Path(
            str(
                getattr(
                    cfg,
                    "RUNTIME_RECONCILIATION_LOG_PATH",
                    str(logs_dir() / "runtime_reconciliation.jsonl"),
                )
                or str(logs_dir() / "runtime_reconciliation.jsonl")
            )
        )
    return Path(path)


def _log_runtime_reconciliation(
    event: str,
    *,
    reason_code: str,
    payload: dict[str, Any] | None = None,
    log_path: Path | str | None = None,
    level: str = "INFO",
) -> Path:
    record = {
        "ts_epoch": time.time(),
        "ts_utc": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": str(event),
        "reason_code": str(reason_code or "").strip() or "unspecified",
        "level": str(level or "INFO").upper(),
    }
    if payload:
        record.update(dict(payload))
    return _append_jsonl(_resolve_runtime_reconciliation_log_path(log_path), record)


def _resolve_broker_api(broker_api: Any | None = None) -> Any:
    if broker_api is not None:
        return broker_api
    if _skip_broker_auth_resolution():
        raise RuntimeError("broker_api_unavailable")
    from core.kite_client import kite_client

    try:
        kite_client.ensure()
    except Exception:
        pass
    api = getattr(kite_client, "kite", None)
    if api is None:
        raise RuntimeError("broker_api_unavailable")
    return api


def _fetch_broker_positions_snapshot(broker_api: Any) -> list[dict[str, Any]]:
    if not hasattr(broker_api, "positions") or not callable(broker_api.positions):
        return []
    raw = broker_api.positions()
    if raw is None:
        return []
    if isinstance(raw, list):
        return [dict(x) for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        out: list[dict[str, Any]] = []
        for key in ("net", "day", "data", "positions"):
            block = raw.get(key)
            if isinstance(block, list):
                out.extend(dict(x) for x in block if isinstance(x, dict))
        return out
    return []


def _candidate_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in (
        "instrument_id",
        "tradingsymbol",
        "trading_symbol",
        "symbol",
        "underlying",
    ):
        value = _norm_text(row.get(key)).upper()
        if value:
            keys.add(value)
    underlying = _norm_text(row.get("underlying") or row.get("symbol")).upper()
    expiry = _norm_text(row.get("expiry"))
    strike = _norm_text(row.get("strike"))
    right = _norm_text(row.get("right") or row.get("option_type")).upper()
    if underlying and expiry and strike and right:
        keys.add(f"{underlying}|{expiry}|{strike}|{right}")
    return keys


def _position_quantity_abs(row: dict[str, Any]) -> float:
    qty = _safe_float(
        row.get("quantity")
        if row.get("quantity") is not None
        else row.get("net_quantity"),
        0.0,
    )
    return abs(float(qty or 0.0))


def _local_trade_quantity_abs(row: dict[str, Any]) -> float:
    qty = _safe_float(row.get("qty_units"), None)
    if qty is None:
        qty = _safe_float(row.get("qty"), 0.0)
    return abs(float(qty or 0.0))


def _find_matching_broker_position(
    trade_row: dict[str, Any],
    broker_positions: list[dict[str, Any]],
    *,
    used_indexes: set[int],
) -> tuple[int | None, dict[str, Any] | None]:
    local_keys = _candidate_keys(trade_row)
    if not local_keys:
        return None, None
    for idx, broker_row in enumerate(broker_positions):
        if idx in used_indexes:
            continue
        if _position_quantity_abs(broker_row) <= 0.0:
            continue
        if local_keys.intersection(_candidate_keys(broker_row)):
            return idx, broker_row
    return None, None


def reconcile_orders(
    *,
    broker_api: Any | None = None,
    order_state_machine: OrderStateMachine | None = None,
    log_path: Path | str | None = None,
    network_retries: int | None = None,
    retry_delay_sec: float | None = None,
) -> dict[str, Any]:
    sm = order_state_machine or OrderStateMachine()
    startup_limit = max(1, int(getattr(cfg, "ORDER_STORE_STARTUP_LOAD_LIMIT", 2000)))
    open_orders_before = sm.list_orders(include_terminal=False, limit=startup_limit)
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        broker_api=broker_api,
        log_path=_resolve_runtime_reconciliation_log_path(log_path),
        network_retries=network_retries,
        retry_delay_sec=retry_delay_sec,
    )
    result = daemon.run_cycle_once()
    open_orders_after = sm.list_orders(include_terminal=False, limit=startup_limit)
    summary = {
        "status": "ok" if int(result.errors or 0) == 0 else "error",
        "scanned_orders": int(result.scanned_orders),
        "corrections": int(result.corrections),
        "errors": int(result.errors),
        "broker_open_orders": int(result.broker_open_orders),
        "broker_positions": int(result.broker_positions),
        "started_at": float(result.started_at),
        "ended_at": float(result.ended_at),
        "open_orders_before": len(open_orders_before),
        "open_orders_after": len(open_orders_after),
        "reason_codes": ["orders_reconciled"],
        "log_path": str(_resolve_runtime_reconciliation_log_path(log_path)),
    }
    _log_runtime_reconciliation(
        "reconcile_orders_complete",
        reason_code="orders_reconciled",
        payload=summary,
        log_path=log_path,
        level="INFO" if summary["errors"] == 0 else "WARN",
    )
    return summary


def reconcile_positions(
    *,
    broker_api: Any | None = None,
    open_positions: list[dict[str, Any]] | None = None,
    position_limit: int | None = None,
    log_path: Path | str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    limit = max(
        1,
        int(
            position_limit
            if position_limit is not None
            else getattr(cfg, "RUNTIME_RESTORE_POSITION_LIMIT", 2000)
        ),
    )
    local_positions = [dict(row) for row in (open_positions or fetch_open_positions_dict(limit=limit) or [])]
    ts = _norm_text(timestamp) or datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    summary: dict[str, Any] = {
        "status": "ok",
        "local_open_positions": len(local_positions),
        "broker_positions": 0,
        "positions_restored": 0,
        "positions_closed_from_broker_truth": 0,
        "restored_positions": [],
        "unmatched_broker_positions": [],
        "reason_codes": [],
        "log_path": str(_resolve_runtime_reconciliation_log_path(log_path)),
    }
    if not local_positions:
        summary["reason_codes"] = ["no_local_open_positions"]
        return summary

    broker_rows = _fetch_broker_positions_snapshot(_resolve_broker_api(broker_api))
    summary["broker_positions"] = len(broker_rows)
    used_indexes: set[int] = set()
    reason_codes: set[str] = set()
    restored_rows: list[dict[str, Any]] = []

    for raw_trade in local_positions:
        hydrated = rehydrate_trade_lifecycle(raw_trade, reason="restart_rehydrated", timestamp=ts)
        match_idx, broker_row = _find_matching_broker_position(
            hydrated,
            broker_rows,
            used_indexes=used_indexes,
        )
        broker_qty = _position_quantity_abs(broker_row or {})
        local_qty = _local_trade_quantity_abs(hydrated)

        if match_idx is not None:
            used_indexes.add(match_idx)

        if broker_row is None or broker_qty <= 0.0:
            reason_code = "broker_position_flattened"
            restored = record_trade_lifecycle_observation(
                hydrated,
                TradeLifecycleState.CLOSED,
                reason=reason_code,
                timestamp=ts,
            )
            summary["positions_closed_from_broker_truth"] = int(summary["positions_closed_from_broker_truth"]) + 1
        elif local_qty > 0.0 and broker_qty + 1e-9 < local_qty:
            reason_code = "broker_partial_position_restored"
            restored = record_trade_lifecycle_observation(
                hydrated,
                TradeLifecycleState.PARTIALLY_FILLED,
                reason=reason_code,
                timestamp=ts,
            )
            summary["positions_restored"] = int(summary["positions_restored"]) + 1
        else:
            reason_code = "broker_open_position_restored"
            restored = record_trade_lifecycle_observation(
                hydrated,
                TradeLifecycleState.ACTIVE,
                reason=reason_code,
                timestamp=ts,
            )
            summary["positions_restored"] = int(summary["positions_restored"]) + 1

        restored = dict(restored)
        restored["reconciliation_reason_code"] = reason_code
        restored["broker_position_qty"] = broker_qty
        restored["local_position_qty"] = local_qty
        restored_rows.append(restored)
        reason_codes.add(reason_code)
        _log_runtime_reconciliation(
            "reconcile_position",
            reason_code=reason_code,
            payload={
                "trade_id": restored.get("trade_id"),
                "symbol": restored.get("symbol"),
                "trade_lifecycle_state": restored.get("trade_lifecycle_state"),
                "broker_position_qty": broker_qty,
                "local_position_qty": local_qty,
            },
            log_path=log_path,
            level="INFO" if reason_code != "broker_position_flattened" else "WARN",
        )

    unmatched_broker_positions: list[dict[str, Any]] = []
    for idx, broker_row in enumerate(broker_rows):
        if idx in used_indexes:
            continue
        broker_qty = _position_quantity_abs(broker_row)
        if broker_qty <= 0.0:
            continue
        orphan = dict(broker_row)
        orphan["reconciliation_reason_code"] = "broker_position_without_local_trade"
        unmatched_broker_positions.append(orphan)
        reason_codes.add("broker_position_without_local_trade")
        _log_runtime_reconciliation(
            "reconcile_orphan_broker_position",
            reason_code="broker_position_without_local_trade",
            payload={
                "symbol": broker_row.get("symbol") or broker_row.get("tradingsymbol"),
                "broker_position_qty": broker_qty,
            },
            log_path=log_path,
            level="WARN",
        )

    summary["restored_positions"] = restored_rows
    summary["unmatched_broker_positions"] = unmatched_broker_positions
    summary["reason_codes"] = sorted(reason_codes)
    return summary


def restore_runtime_state(
    *,
    broker_api: Any | None = None,
    order_state_machine: OrderStateMachine | None = None,
    open_positions: list[dict[str, Any]] | None = None,
    reconcile_order_state: bool = True,
    restore_position_state: bool = True,
    log_path: Path | str | None = None,
) -> dict[str, Any]:
    sm = order_state_machine or OrderStateMachine()
    position_limit = max(1, int(getattr(cfg, "RUNTIME_RESTORE_POSITION_LIMIT", 2000)))
    local_open_positions = [dict(row) for row in (open_positions or fetch_open_positions_dict(limit=position_limit) or [])]
    open_orders = sm.list_orders(
        include_terminal=False,
        limit=max(1, int(getattr(cfg, "ORDER_STORE_STARTUP_LOAD_LIMIT", 2000))),
    )
    summary: dict[str, Any] = {
        "status": "ok",
        "open_orders": len(open_orders),
        "open_positions": len(local_open_positions),
        "order_reconciliation": None,
        "position_reconciliation": None,
        "reason_codes": [],
        "log_path": str(_resolve_runtime_reconciliation_log_path(log_path)),
    }
    if not open_orders and not local_open_positions:
        summary["reason_codes"] = ["no_local_runtime_state"]
        return summary

    _log_runtime_reconciliation(
        "restore_runtime_state_start",
        reason_code="runtime_restore_started",
        payload={
            "open_orders": len(open_orders),
            "open_positions": len(local_open_positions),
            "reconcile_order_state": bool(reconcile_order_state),
            "restore_position_state": bool(restore_position_state),
        },
        log_path=log_path,
        level="INFO",
    )

    reason_codes: set[str] = set()
    errors: list[str] = []

    if reconcile_order_state and open_orders:
        try:
            order_summary = reconcile_orders(
                broker_api=broker_api,
                order_state_machine=sm,
                log_path=log_path,
            )
            summary["order_reconciliation"] = order_summary
            reason_codes.update(order_summary.get("reason_codes") or [])
        except Exception as exc:
            message = f"order_reconciliation_failed:{type(exc).__name__}:{exc}"
            errors.append(message)
            _log_runtime_reconciliation(
                "restore_runtime_state_order_error",
                reason_code="order_reconciliation_failed",
                payload={"error": message},
                log_path=log_path,
                level="ERROR",
            )

    if restore_position_state and local_open_positions:
        try:
            position_summary = reconcile_positions(
                broker_api=broker_api,
                open_positions=local_open_positions,
                position_limit=position_limit,
                log_path=log_path,
            )
            summary["position_reconciliation"] = position_summary
            reason_codes.update(position_summary.get("reason_codes") or [])
        except Exception as exc:
            message = f"position_reconciliation_failed:{type(exc).__name__}:{exc}"
            errors.append(message)
            _log_runtime_reconciliation(
                "restore_runtime_state_position_error",
                reason_code="position_reconciliation_failed",
                payload={"error": message},
                log_path=log_path,
                level="ERROR",
            )

    if errors:
        summary["status"] = "partial_error"
        summary["errors"] = errors
        reason_codes.add("runtime_restore_partial_error")

    summary["reason_codes"] = sorted(reason_codes)
    _log_runtime_reconciliation(
        "restore_runtime_state_complete",
        reason_code="runtime_restore_complete",
        payload={
            "status": summary["status"],
            "reason_codes": summary["reason_codes"],
            "open_orders": summary["open_orders"],
            "open_positions": summary["open_positions"],
        },
        log_path=log_path,
        level="INFO" if not errors else "WARN",
    )
    return summary


def emit_execution_fill_event(
    *,
    order_id: Any,
    symbol: Any,
    side: Any,
    qty: Any,
    price: Any,
    ts_utc: Any = None,
    run_id: Any = None,
    desk_id: Any = None,
    mode: Any = None,
    trade_id: Any = None,
    broker_order_id: Any = None,
    base_dir: Path | str | None = None,
) -> Path:
    ts = _parse_ts_utc(ts_utc)
    event = {
        "event_type": "EXECUTION_FILL",
        "order_id": _norm_text(order_id),
        "broker_order_id": _norm_text(broker_order_id) or None,
        "trade_id": _norm_text(trade_id) or None,
        "symbol": _norm_text(symbol).upper(),
        "side": _norm_text(side).upper(),
        "qty": _safe_float(qty, 0.0),
        "price": _safe_float(price, 0.0),
        "ts_utc": ts.isoformat().replace("+00:00", "Z"),
        "run_id": _norm_text(run_id) or _norm_text(getattr(cfg, "RUN_ID", None)) or _norm_text(getattr(cfg, "EXEC_RUN_ID", None)) or "UNKNOWN_RUN",
        "desk_id": _norm_text(desk_id) or _norm_text(getattr(cfg, "DESK_ID", None)) or "DEFAULT",
        "mode": (_norm_text(mode) or _norm_text(getattr(cfg, "EXECUTION_MODE", None)) or "PAPER").upper(),
    }
    if not event["order_id"]:
        raise ValueError("missing_order_id")
    if not event["symbol"]:
        raise ValueError("missing_symbol")
    if event["side"] not in {"BUY", "SELL"}:
        raise ValueError(f"invalid_side:{event['side']}")
    base = _resolve_analytics_base(base_dir)
    return _atomic_append_jsonl(_event_day_path(base, ts), event)


def _iter_event_files(base_dir: Path) -> Iterable[Path]:
    if not base_dir.exists():
        return []
    paths: list[Path] = []
    for day_dir in sorted(base_dir.iterdir()):
        if day_dir.is_dir():
            f = day_dir / "events.jsonl"
            if f.exists():
                paths.append(f)
    return paths


def _normalize_execution_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    if _norm_text(payload.get("event_type")).upper() != "EXECUTION_FILL":
        return None
    ts = _parse_ts_utc(payload.get("ts_utc"))
    qty = _safe_float(payload.get("qty"), None)
    price = _safe_float(payload.get("price"), None)
    if qty is None or price is None:
        return None
    return {
        "event_type": "EXECUTION_FILL",
        "order_id": _norm_text(payload.get("order_id")),
        "broker_order_id": _norm_text(payload.get("broker_order_id")) or None,
        "trade_id": _norm_text(payload.get("trade_id")) or None,
        "symbol": _norm_text(payload.get("symbol")).upper(),
        "side": _norm_text(payload.get("side")).upper(),
        "qty": float(qty),
        "price": float(price),
        "ts_utc": ts.isoformat().replace("+00:00", "Z"),
        "run_id": _norm_text(payload.get("run_id")) or "UNKNOWN_RUN",
        "desk_id": _norm_text(payload.get("desk_id")) or "DEFAULT",
        "mode": (_norm_text(payload.get("mode")) or "PAPER").upper(),
    }


def read_execution_fill_events(
    *,
    base_dir: Path | str | None = None,
    trade_date: str | date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    base = _resolve_analytics_base(base_dir)
    day_filter: date | None
    if trade_date is None:
        day_filter = None
    elif isinstance(trade_date, date):
        day_filter = trade_date
    else:
        day_filter = datetime.fromisoformat(str(trade_date)).date()
    out: list[dict[str, Any]] = []
    for path in _iter_event_files(base):
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception as exc:
                    logger.warning(
                        "reconciliation_bad_json_line",
                        extra={"path": str(path), "line": lineno, "error": str(exc)},
                    )
                    continue
                if not isinstance(payload, dict):
                    logger.warning(
                        "reconciliation_non_object_line",
                        extra={"path": str(path), "line": lineno},
                    )
                    continue
                event = _normalize_execution_event(payload)
                if event is None:
                    continue
                if day_filter is not None:
                    local_day = _parse_ts_utc(event["ts_utc"]).astimezone(EXCHANGE_TZ).date()
                    if local_day != day_filter:
                        continue
                out.append(event)
    out.sort(key=lambda row: row["ts_utc"])
    if limit is not None and limit > 0:
        return out[-int(limit):]
    return out


def _broker_positions_from_events(events: list[dict[str, Any]]) -> dict[str, float]:
    net: dict[str, float] = defaultdict(float)
    for row in events:
        symbol = _norm_text(row.get("symbol")).upper()
        if not symbol:
            continue
        qty = float(_safe_float(row.get("qty"), 0.0) or 0.0)
        side = _norm_text(row.get("side")).upper()
        sign = 1.0 if side == "BUY" else -1.0
        net[symbol] += sign * qty
    return {k: round(v, 6) for k, v in net.items() if abs(v) > 1e-9}


def _local_positions_from_ledger() -> dict[str, float]:
    rows = list(fetch_open_positions_dict(limit=5000) or [])
    net: dict[str, float] = defaultdict(float)
    for row in rows:
        symbol = _norm_text(row.get("symbol")).upper()
        if not symbol:
            continue
        qty = float(_safe_float(row.get("qty") or row.get("qty_units"), 0.0) or 0.0)
        side = _norm_text(row.get("side")).upper()
        sign = 1.0 if side == "BUY" else -1.0
        net[symbol] += sign * qty
    return {k: round(v, 6) for k, v in net.items() if abs(v) > 1e-9}


def reconcile_execution_fills(
    *,
    base_dir: Path | str | None = None,
    trade_date: str | date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = _resolve_analytics_base(base_dir)
    events = read_execution_fill_events(base_dir=base, trade_date=trade_date)
    rows = list(events)
    summary: dict[str, Any] = {
        "event_type": "EXECUTION_FILL",
        "storage_path": str(base),
        "execution_fill_count": len(rows),
        "date_filter": str(trade_date) if trade_date is not None else None,
        "run_ids": sorted({_norm_text(row.get("run_id")) for row in rows if _norm_text(row.get("run_id"))}),
        "desk_ids": sorted({_norm_text(row.get("desk_id")) for row in rows if _norm_text(row.get("desk_id"))}),
        "modes": sorted({_norm_text(row.get("mode")) for row in rows if _norm_text(row.get("mode"))}),
        "match_rate": 0.0,
        "avg_confidence": 0.0,
    }
    if not rows:
        summary["error"] = (
            f"No EXECUTION_FILL events found under {base}."
            " Reconciliation uses execution fill events only."
        )
        return rows, summary

    broker_positions = _broker_positions_from_events(rows)
    local_positions = _local_positions_from_ledger()
    mismatch = broker_positions != local_positions
    summary.update(
        {
            "broker_open_positions": broker_positions,
            "local_open_positions": local_positions,
            "position_mismatch": bool(mismatch),
            "match_rate": 1.0 if not mismatch else 0.0,
            "avg_confidence": 1.0 if not mismatch else 0.0,
        }
    )
    if mismatch:
        summary["warning"] = (
            "Broker-vs-ledger position mismatch: "
            f"broker={broker_positions} local={local_positions}"
        )
    return rows, summary
