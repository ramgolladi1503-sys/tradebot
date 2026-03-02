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
from core.trade_store import fetch_open_positions_dict


logger = logging.getLogger(__name__)

EXCHANGE_TZ = ZoneInfo(str(getattr(cfg, "EXCHANGE_TZ", "Asia/Kolkata") or "Asia/Kolkata"))
_DEFAULT_ANALYTICS_BASE = Path(
    str(getattr(cfg, "ANALYTICS_RUNTIME_DIR", "runtime/analytics") or "runtime/analytics")
)


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


def _event_day_path(base_dir: Path, ts_utc: datetime) -> Path:
    day_key = ts_utc.astimezone(EXCHANGE_TZ).date().isoformat()
    return base_dir / day_key / "events.jsonl"


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

