"""Trade state engine.

Migration note:
Updates trade lifecycle (PLANNING -> ACTIVE -> EXITED) based on live option LTP ticks.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import config as cfg
from core.option_entry import get_option_ltp_sla_sec
from core.tick_store import get_last_tick
from core.time_utils import compute_age_sec, now_utc_epoch
from core.trade_activation import should_activate, activate_trade
from core.trade_identity import compute_trade_key, derive_strategy_id
from core.option_token_resolver import TokenCoverageError, resolve_option_token
from core.sim_pnl import resolve_lot_size
from core.entry_semantics import EntryContractViolation, enforce_entry_contract

logger = logging.getLogger(__name__)


@dataclass
class TradeStateUpdate:
    updated: bool = False
    activated: int = 0
    exited: int = 0
    invalid: int = 0


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_ts_epoch(row: dict) -> float:
    for key in ("last_seen", "timestamp", "created_at", "queue_ts"):
        val = row.get(key)
        if not val:
            continue
        try:
            if isinstance(val, (int, float)):
                return float(val)
            return datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
    return now_utc_epoch()


def _ensure_trade_key(row: dict) -> str | None:
    key = row.get("trade_key")
    if key:
        return key
    strategy_id = derive_strategy_id(row.get("strategy_id"), row.get("strategy") or row.get("generator"))
    key = compute_trade_key(
        row.get("symbol"),
        row.get("expiry_date") or row.get("expiry"),
        row.get("strike"),
        row.get("option_type") or row.get("type"),
        row.get("side"),
        strategy_id,
    )
    row["trade_key"] = key
    return key


def _resolve_token(row: dict) -> int | None:
    token = row.get("instrument_token")
    if token not in (None, ""):
        try:
            return int(float(token))
        except Exception:
            return None
    instrument_id = row.get("instrument_id")
    if instrument_id not in (None, ""):
        try:
            return int(float(instrument_id))
        except Exception:
            pass
    symbol = row.get("symbol") or row.get("underlying")
    expiry = row.get("expiry_date") or row.get("expiry")
    strike = row.get("strike")
    option_type = row.get("option_type") or row.get("type") or row.get("right")
    if not symbol or not expiry or strike is None or not option_type:
        return None
    try:
        resolved = resolve_option_token(symbol, expiry, strike, option_type)
    except TokenCoverageError as exc:
        logger.warning("token coverage below threshold during trade state processing: %s evidence=%s", exc.code, exc.evidence)
        return None
    if not resolved:
        return None
    token = resolved.get("instrument_token")
    if token is None:
        return None
    try:
        row["instrument_token"] = int(float(token))
    except Exception:
        row["instrument_token"] = token
    if resolved.get("tradingsymbol") and not row.get("tradingsymbol"):
        row["tradingsymbol"] = resolved.get("tradingsymbol")
    return row.get("instrument_token")


def _compute_pnl(row: dict, ltp: float) -> tuple[float | None, float | None]:
    activation_price = _safe_float(row.get("activation_price"))
    if activation_price is None:
        activation_price = _safe_float(row.get("fill_price"))
    if activation_price is None:
        return None, None
    side = str(row.get("side") or "").upper()
    if side not in ("BUY", "SELL"):
        return None, None
    pnl_points = (ltp - activation_price) if side == "BUY" else (activation_price - ltp)
    lot_size, _source, _fallback = resolve_lot_size(row)
    pnl_cash = pnl_points * float(lot_size) if lot_size else None
    return round(float(pnl_points), 2), round(float(pnl_cash), 2) if pnl_cash is not None else None


def _should_exit(row: dict, ltp: float) -> tuple[bool, str | None]:
    side = str(row.get("side") or "").upper()
    stop = _safe_float(row.get("stop"))
    target = _safe_float(row.get("target"))
    if side == "BUY":
        if stop is not None and ltp <= stop:
            return True, "STOP_HIT"
        if target is not None and ltp >= target:
            return True, "TARGET_HIT"
    elif side == "SELL":
        if stop is not None and ltp >= stop:
            return True, "STOP_HIT"
        if target is not None and ltp <= target:
            return True, "TARGET_HIT"
    return False, None


def dedupe_rows(rows: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _ensure_trade_key(row)
        if not key:
            continue
        if key not in deduped:
            deduped[key] = row
            continue
        existing = deduped[key]
        if _row_ts_epoch(row) >= _row_ts_epoch(existing):
            # Preserve first_seen from the earliest row.
            if existing.get("first_seen") and not row.get("first_seen"):
                row["first_seen"] = existing.get("first_seen")
            deduped[key] = row
    return list(deduped.values())


def process_trade_state(trades: list[dict], now_ts: float | None = None) -> tuple[list[dict], TradeStateUpdate]:
    now_epoch = float(now_ts if now_ts is not None else now_utc_epoch())
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "PAPER") or "PAPER").upper()
    live_sla = float(getattr(cfg, "LTP_SLA_SECONDS", getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)))
    allow_stale = bool(getattr(cfg, "ALLOW_STALE_QUOTES", exec_mode in {"PAPER", "SIM", "BACKTEST", "PLANNING", "ADVISORY", "OFFHOURS"}))
    sla_sec = float(
        get_option_ltp_sla_sec(
            exec_mode,
            live_sla,
            allow_stale_quotes=allow_stale,
        )
    )
    update = TradeStateUpdate()
    updated_rows: list[dict] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        row = dict(trade)
        _ensure_trade_key(row)
        token = _resolve_token(row)
        tick = None
        if token is not None:
            try:
                tick = get_last_tick(token, decision_path=True)
            except TypeError:
                # Backward/test compatibility for patched callables without decision_path kwarg.
                tick = get_last_tick(token)
        ltp = tick.get("ltp") if isinstance(tick, dict) else None
        ts_epoch = tick.get("ts_epoch") if isinstance(tick, dict) else None
        price_age = compute_age_sec(ts_epoch, now_epoch) if ts_epoch is not None else None
        row["current_ltp"] = ltp
        row["current_ltp_ts"] = ts_epoch
        row["price_age_sec"] = price_age
        if ltp is not None:
            row["live_ltp"] = ltp

        status = str(row.get("status") or "PLANNING").upper()
        if token is None:
            row["invalidation_reason"] = row.get("invalidation_reason") or "NO_TOKEN"
            update.invalid += 1
        entry_val = _safe_float(row.get("entry"))
        if status == "PLANNING":
            if entry_val is None:
                row["activation_reason"] = row.get("activation_reason") or "NO_ENTRY"
            elif ltp is None or price_age is None or price_age > sla_sec:
                row["activation_reason"] = row.get("activation_reason") or "NO_LIVE_PRICE"
            else:
                if should_activate(row.get("side"), row.get("entry_condition"), entry_val, ltp):
                    row = activate_trade(row, ltp, ts=_now_iso())
                    row["activation_reason"] = "ENTRY_TRIGGERED"
                    update.activated += 1
                    update.updated = True
        status = str(row.get("status") or "PLANNING").upper()
        if status == "ACTIVE":
            if ltp is not None:
                pnl_points, pnl_cash = _compute_pnl(row, ltp)
                row["pnl_points"] = pnl_points
                row["pnl_cash"] = pnl_cash
                exit_now, reason = _should_exit(row, ltp)
                if exit_now:
                    row["status"] = "EXITED"
                    row["exit_reason"] = reason
                    row["exit_price"] = ltp
                    row["exit_ts"] = _now_iso()
                    update.exited += 1
                    update.updated = True
        try:
            row = enforce_entry_contract(row, stage="trade_state_engine.process")
        except EntryContractViolation:
            raise
        updated_rows.append(row)
    return updated_rows, update


def run_state_engine_once(desk_id: str | None = None, queue_paths: Iterable[Path] | None = None) -> dict:
    try:
        from core.review_queue import (
            QUEUE_PATH,
            QUICK_QUEUE_PATH,
            ZERO_HERO_QUEUE_PATH,
            SCALP_QUEUE_PATH,
            TARGET_POINTS_QUEUE_PATH,
        )
        default_paths = [
            QUEUE_PATH,
            QUICK_QUEUE_PATH,
            ZERO_HERO_QUEUE_PATH,
            SCALP_QUEUE_PATH,
            TARGET_POINTS_QUEUE_PATH,
        ]
    except Exception:
        default_paths = []
    paths = list(queue_paths) if queue_paths is not None else default_paths
    summary = {"desk_id": desk_id or "DEFAULT", "updated": 0, "queues": {}}
    for path in paths:
        if not path:
            continue
        path = Path(path)
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())
        except Exception:
            logger.warning("trade_state_engine: failed to read %s", path)
            continue
        if not isinstance(raw, list):
            continue
        rows = [row for row in raw if isinstance(row, dict)]
        deduped = dedupe_rows(rows)
        updated_rows, update = process_trade_state(deduped)
        changed = update.updated or len(deduped) != len(rows)
        if changed:
            try:
                path.write_text(json.dumps(updated_rows, indent=2))
                summary["updated"] += 1
            except Exception:
                logger.warning("trade_state_engine: failed to write %s", path)
        summary["queues"][path.name] = {
            "rows": len(updated_rows),
            "activated": update.activated,
            "exited": update.exited,
            "invalid": update.invalid,
            "changed": changed,
        }
    return summary
