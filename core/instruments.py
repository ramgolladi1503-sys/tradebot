"""Instrument registry + expiry selection helpers.

Source of truth is the Kite instruments dump; no calendar-rule expiry synthesis.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any


logger = logging.getLogger(__name__)


def coerce_expiry_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        text = str(value).strip()
        if not text:
            return None
        if "T" in text:
            text = text.split("T", 1)[0]
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def option_exchange(symbol: str | None) -> str:
    return "BFO" if str(symbol or "").upper() == "SENSEX" else "NFO"


def option_segment(exchange: str | None) -> str:
    return "BFO-OPT" if str(exchange or "").upper() == "BFO" else "NFO-OPT"


def _normalize_expiries(values: list[Any] | tuple[Any, ...] | set[Any]) -> list[date]:
    out = []
    for value in values:
        exp = coerce_expiry_date(value)
        if exp is not None:
            out.append(exp)
    return sorted(set(out))


def _monthly_expiry_candidates(expiries: list[date]) -> list[date]:
    last_by_month: dict[tuple[int, int], date] = {}
    for exp in sorted(expiries):
        key = (exp.year, exp.month)
        prev = last_by_month.get(key)
        if prev is None or exp > prev:
            last_by_month[key] = exp
    return [last_by_month[key] for key in sorted(last_by_month.keys())]


def select_expiry(
    available_expiries: list[Any] | tuple[Any, ...] | set[Any],
    *,
    selection_mode: str = "NEAREST",
    today: date | None = None,
) -> date | None:
    expiries = _normalize_expiries(available_expiries)
    if not expiries:
        return None
    today = today or date.today()
    mode = str(selection_mode or "NEAREST").upper()
    if mode == "MONTHLY":
        monthly = _monthly_expiry_candidates(expiries)
        future = [exp for exp in monthly if exp >= today]
        return future[0] if future else None
    future = [exp for exp in expiries if exp >= today]
    return future[0] if future else None


def select_next_expiry(
    available_expiries: list[Any] | tuple[Any, ...] | set[Any],
    current_expiry: Any,
    *,
    selection_mode: str = "NEAREST",
) -> date | None:
    expiries = _normalize_expiries(available_expiries)
    current = coerce_expiry_date(current_expiry)
    if not expiries or current is None:
        return None
    mode = str(selection_mode or "NEAREST").upper()
    candidates = expiries
    if mode == "MONTHLY":
        candidates = _monthly_expiry_candidates(expiries)
    later = [exp for exp in candidates if exp > current]
    return later[0] if later else None


def build_option_registry(
    *,
    symbol: str,
    instruments: list[dict] | tuple[dict, ...],
    exchange: str | None = None,
) -> dict:
    sym = str(symbol or "").upper()
    ex = str(exchange or option_exchange(sym)).upper()
    seg = option_segment(ex)
    registry: dict[tuple[str, str, float, str, date], dict] = {}
    filtered_instruments: list[dict] = []
    expiries: set[date] = set()
    for inst in instruments or []:
        if not isinstance(inst, dict):
            continue
        if str(inst.get("segment") or "").upper() != seg:
            continue
        if str(inst.get("name") or "").upper() != sym:
            continue
        inst_type = str(inst.get("instrument_type") or "").upper()
        if inst_type not in {"CE", "PE"}:
            continue
        exp = coerce_expiry_date(inst.get("expiry"))
        if exp is None:
            continue
        try:
            strike = float(inst.get("strike"))
        except Exception:
            continue
        key = (sym, seg, strike, inst_type, exp)
        entry = {
            "instrument_token": inst.get("instrument_token"),
            "tradingsymbol": inst.get("tradingsymbol"),
            "expiry": exp,
        }
        if key not in registry:
            registry[key] = entry
        filtered_instruments.append(inst)
        expiries.add(exp)
    return {
        "symbol": sym,
        "exchange": ex,
        "segment": seg,
        "registry": registry,
        "instruments": filtered_instruments,
        "available_expiries": sorted(expiries),
    }


def resolve_registry_contract(
    *,
    registry_payload: dict,
    symbol: str,
    strike: float,
    instrument_type: str,
    requested_expiry: Any = None,
    selection_mode: str = "NEAREST",
    today: date | None = None,
) -> dict | None:
    sym = str(symbol or "").upper()
    seg = str(registry_payload.get("segment") or option_segment(option_exchange(sym))).upper()
    today = today or date.today()
    try:
        strike_val = float(strike)
    except Exception:
        return None
    opt_type = str(instrument_type or "").upper()
    if opt_type not in {"CE", "PE"}:
        return None
    reg = registry_payload.get("registry") or {}
    expiry_candidates = sorted(
        {
            key[4]
            for key in reg.keys()
            if key[0] == sym and key[1] == seg and key[3] == opt_type and abs(float(key[2]) - strike_val) <= 1e-6
        }
    )
    if not expiry_candidates:
        return None
    requested = coerce_expiry_date(requested_expiry)
    chosen = None
    if requested is not None and requested < today:
        logger.warning(
            "[EXPIRED_CONTRACT_REJECTED] context=%s symbol=%s requested_expiry=%s today=%s",
            "resolve_registry_contract",
            sym,
            requested.isoformat(),
            today.isoformat(),
        )
        return None
    if requested is not None and requested in expiry_candidates:
        chosen = requested
    elif requested is not None:
        log_requested_expiry_missing(
            symbol=sym,
            requested_expiry=requested,
            available_expiries=expiry_candidates,
            context="resolve_registry_contract",
        )
    if chosen is None:
        chosen = select_expiry(
            expiry_candidates,
            selection_mode=selection_mode,
            today=today,
        )
    if chosen is None or chosen < today:
        logger.warning(
            "[EXPIRED_CONTRACT_REJECTED] context=%s symbol=%s requested_expiry=%s available_expiries=%s today=%s",
            "resolve_registry_contract",
            sym,
            requested.isoformat() if requested is not None else None,
            [d.isoformat() for d in expiry_candidates],
            today.isoformat(),
        )
        return None
    key = (sym, seg, strike_val, opt_type, chosen)
    entry = reg.get(key)
    if not isinstance(entry, dict):
        return None
    out = dict(entry)
    out["symbol"] = sym
    out["segment"] = seg
    out["strike"] = strike_val
    out["instrument_type"] = opt_type
    out["expiry"] = chosen
    return out


def log_requested_expiry_missing(
    *,
    symbol: str,
    requested_expiry: Any,
    available_expiries: list[Any] | tuple[Any, ...] | set[Any],
    context: str,
) -> None:
    requested = coerce_expiry_date(requested_expiry)
    available = _normalize_expiries(available_expiries)
    logger.warning(
        "[EXPIRY_RESOLUTION_MISS] context=%s symbol=%s requested_expiry=%s available_expiries=%s",
        context,
        str(symbol or "").upper(),
        requested.isoformat() if requested is not None else str(requested_expiry),
        [d.isoformat() for d in available],
    )