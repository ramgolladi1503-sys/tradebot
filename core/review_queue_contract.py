"""Review queue quote-preservation contract.

This module isolates the review-queue REST fallback/rate-limit behavior that was
previously bundled inside ``core.full_pytest_contracts``.

Contract:
- preserve better ``PRICE_MISMATCH``/``rest_fallback`` quote truth during
  advisory revalidation;
- avoid repeated REST fallback fetches for the same tradingsymbol during the
  cooldown window;
- never turn REST fallback quote truth into executable quote truth.

Final target: move this behavior directly into ``core.review_queue`` and remove
this module once the real module owns the contract natively.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

_INSTALLED = False
_REST_FALLBACK_CACHE: dict[str, tuple[float, float]] = {}


def _same_trade(a: dict[str, Any], b: dict[str, Any], rq: Any) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    for key in ("trade_key", "trade_id"):
        av = str(a.get(key) or "").strip()
        bv = str(b.get(key) or "").strip()
        if av and bv and av == bv:
            return True
    try:
        compute_trade_key = getattr(rq, "compute_trade_key")
        ak = compute_trade_key(
            a.get("symbol"),
            a.get("expiry_date") or a.get("expiry"),
            a.get("strike"),
            a.get("option_type") or a.get("type"),
            a.get("side"),
            a.get("strategy_id") or a.get("strategy") or a.get("generator"),
        )
        bk = compute_trade_key(
            b.get("symbol"),
            b.get("expiry_date") or b.get("expiry"),
            b.get("strike"),
            b.get("option_type") or b.get("type"),
            b.get("side"),
            b.get("strategy_id") or b.get("strategy") or b.get("generator"),
        )
        return bool(ak and bk and ak == bk)
    except Exception:
        return False


def _is_better_rest_quote(row: dict[str, Any], rq: Any) -> bool:
    if not isinstance(row, dict):
        return False
    safe_float = getattr(rq, "_safe_float", lambda value: None)
    return bool(
        str(row.get("quote_validation_status") or "").strip().upper() == "PRICE_MISMATCH"
        and str(row.get("option_ltp_source") or "").strip().lower() == "rest_fallback"
        and str(row.get("entry_status") or "").strip().lower() == "displayable"
        and safe_float(row.get("entry")) is not None
    )


def _is_worse_no_live_quote(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    return bool(
        str(row.get("quote_validation_status") or "").strip().upper() == "NO_LIVE_OPTION_FEED"
        or str(row.get("entry_status") or "").strip().upper() == "NO_LIVE_OPTION_FEED"
    )


def _preserve_quote_fields(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "entry",
        "entry_status",
        "entry_source",
        "display_entry",
        "display_entry_status",
        "display_entry_source",
        "final_entry",
        "final_entry_source",
        "final_entry_locked",
        "current_ltp",
        "opt_ltp",
        "option_ltp",
        "option_ltp_source",
        "option_ltp_timestamp",
        "quote_source",
        "quote_validation_status",
        "quote_age_sec",
        "price_age_sec",
        "option_age_sec",
        "execution_entry",
        "execution_entry_status",
        "execution_entry_source",
        "validation_reference_price",
        "validation_reference_source",
    )
    out = dict(target)
    for field in fields:
        if field in source:
            out[field] = source.get(field)
    out["quote_truth_preserved_from_previous_row"] = True
    return out


def _extract_tradingsymbol_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    trade = args[0] if args else kwargs.get("trade") or kwargs.get("entry") or {}
    if not isinstance(trade, dict):
        return ""
    return str(trade.get("tradingsymbol") or trade.get("trading_symbol") or trade.get("instrument") or "").strip()


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
        return None if out != out else out
    except Exception:
        return None


def _queue_rest_quote_for_symbol(rq: Any, tradingsymbol: str) -> tuple[float, float] | None:
    if not tradingsymbol:
        return None
    path = getattr(rq, "QUEUE_PATH", None)
    if path is None:
        return None
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    for row in reversed(list(rows or [])):
        if not isinstance(row, dict):
            continue
        row_symbol = str(row.get("tradingsymbol") or row.get("trading_symbol") or "").strip()
        if row_symbol and row_symbol != tradingsymbol:
            continue
        if str(row.get("option_ltp_source") or "").strip().lower() != "rest_fallback":
            continue
        for field in ("option_ltp", "opt_ltp", "current_ltp", "entry"):
            price = _float_or_none(row.get(field))
            if price is not None:
                return price, time.time()
    return None


def _remember_rest_fallback(rq: Any, tradingsymbol: str) -> None:
    if not tradingsymbol:
        return
    cache = getattr(rq, "_ADVISORY_REST_LTP_CACHE", {}) or {}
    for key in (tradingsymbol, tradingsymbol.upper()):
        value = cache.get(key) if isinstance(cache, dict) else None
        if isinstance(value, dict):
            price = _float_or_none(value.get("ltp") or value.get("price") or value.get("value"))
            ts = _float_or_none(value.get("ts") or value.get("timestamp") or value.get("ts_epoch")) or time.time()
            if price is not None:
                _REST_FALLBACK_CACHE[tradingsymbol] = (price, ts)
                return
        if isinstance(value, (list, tuple)) and value:
            price = _float_or_none(value[0])
            ts = _float_or_none(value[1] if len(value) > 1 else None) or time.time()
            if price is not None:
                _REST_FALLBACK_CACHE[tradingsymbol] = (price, ts)
                return
        price = _float_or_none(value)
        if price is not None:
            _REST_FALLBACK_CACHE[tradingsymbol] = (price, time.time())
            return
    queued = _queue_rest_quote_for_symbol(rq, tradingsymbol)
    if queued is not None:
        _REST_FALLBACK_CACHE[tradingsymbol] = queued


def _install_review_queue_contract() -> None:
    try:
        from core import review_queue as rq
    except Exception:
        return

    original_merge = getattr(rq, "_merge_trade_entry", None)
    if callable(original_merge) and not getattr(original_merge, "_review_queue_quote_contract_wrapped", False):

        def _merge_preserving_better_quote(data: list[dict], entry: dict) -> list[dict]:
            better_existing = None
            for row in list(data or []):
                if _same_trade(row, entry, rq) and _is_better_rest_quote(row, rq):
                    better_existing = deepcopy(row)
                    break
            merged = original_merge(data, entry)
            if not better_existing:
                return merged
            for idx, row in enumerate(list(merged or [])):
                if _same_trade(row, better_existing, rq) and _is_worse_no_live_quote(row):
                    merged[idx] = _preserve_quote_fields(row, better_existing)
            return merged

        _merge_preserving_better_quote._review_queue_quote_contract_wrapped = True  # type: ignore[attr-defined]
        _merge_preserving_better_quote._full_pytest_contract_wrapped = True  # type: ignore[attr-defined]
        rq._merge_trade_entry = _merge_preserving_better_quote

    original_add = getattr(rq, "add_to_queue", None)
    if not callable(original_add) or getattr(original_add, "_review_queue_quote_contract_wrapped", False):
        return

    def _add_to_queue_rate_limited_rest_fallback(*args: Any, **kwargs: Any) -> Any:
        tradingsymbol = _extract_tradingsymbol_from_call(args, kwargs)
        cached = _REST_FALLBACK_CACHE.get(tradingsymbol) if tradingsymbol else None
        current_fetch = getattr(rq, "_fetch_option_ltp_rest", None)
        use_cached = bool(cached and callable(current_fetch) and time.time() - float(cached[1]) < 60.0)
        if not use_cached:
            result = original_add(*args, **kwargs)
            _remember_rest_fallback(rq, tradingsymbol)
            return result

        def _cached_fetch_option_ltp_rest(fetch_symbol: str):
            if str(fetch_symbol or "").strip() == tradingsymbol:
                return cached
            return current_fetch(fetch_symbol)

        rq._fetch_option_ltp_rest = _cached_fetch_option_ltp_rest
        try:
            result = original_add(*args, **kwargs)
        finally:
            rq._fetch_option_ltp_rest = current_fetch
        _remember_rest_fallback(rq, tradingsymbol)
        return result

    _add_to_queue_rate_limited_rest_fallback._review_queue_quote_contract_wrapped = True  # type: ignore[attr-defined]
    _add_to_queue_rate_limited_rest_fallback._full_pytest_contract_wrapped = True  # type: ignore[attr-defined]
    rq.add_to_queue = _add_to_queue_rate_limited_rest_fallback


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_review_queue_contract()
    _INSTALLED = True
