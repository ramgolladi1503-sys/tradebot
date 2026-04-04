from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.paths import data_root
from core.time_utils import now_utc_epoch

_LIQUIDITY_BY_TOKEN: dict[int, dict[str, Any]] = {}
_LIQUIDITY_BY_CONTRACT: dict[tuple[str, str, float, str], dict[str, Any]] = {}
_LAST_SNAPSHOT_LOAD_EPOCH = 0.0
_LAST_SNAPSHOT_MTIME = 0.0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _coerce_token(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        token = int(value)
        return token if token > 0 else None
    except Exception:
        return None


def _coerce_expiry(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return text


def _coerce_option_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"CALL", "C"}:
        return "CE"
    if text in {"PUT", "P"}:
        return "PE"
    if text in {"CE", "PE"}:
        return text
    return None


def _coerce_strike(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _contract_key(symbol: Any, expiry: Any, strike: Any, option_type: Any) -> tuple[str, str, float, str] | None:
    sym = str(symbol or "").strip().upper()
    exp = _coerce_expiry(expiry)
    strike_val = _coerce_strike(strike)
    opt_type = _coerce_option_type(option_type)
    if not sym or not exp or strike_val is None or not opt_type:
        return None
    return (sym, exp, float(strike_val), opt_type)


def _snapshot_epoch(row: dict[str, Any], explicit_epoch: float | None = None) -> float:
    if explicit_epoch is not None:
        return float(explicit_epoch)
    for key in ("snapshot_ts_epoch", "quote_ts_epoch", "timestamp_epoch", "ts_epoch", "timestamp"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            try:
                return float(datetime.fromisoformat(str(value)).timestamp())
            except Exception:
                continue
    return float(now_utc_epoch())


def _is_synthetic_liquidity_row(row: dict[str, Any]) -> bool:
    chain_source = str(row.get("chain_source") or row.get("quote_source") or row.get("source") or "").strip().lower()
    if chain_source.startswith("synthetic"):
        return True
    return bool(row.get("planning_only")) and _coerce_token(row.get("instrument_token")) is None


def _merge_payload(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(incoming)
    existing_ts = _safe_float(existing.get("snapshot_ts_epoch")) or 0.0
    incoming_ts = _safe_float(incoming.get("snapshot_ts_epoch")) or 0.0
    if incoming_ts < existing_ts:
        return dict(existing)
    merged = dict(existing)
    merged["snapshot_ts_epoch"] = max(existing_ts, incoming_ts)
    for field_name in ("volume", "current_volume", "oi", "oi_change"):
        incoming_value = _safe_float(incoming.get(field_name))
        if incoming_value is not None:
            merged[field_name] = incoming_value
        elif field_name not in merged:
            merged[field_name] = None
    if incoming.get("source"):
        merged["source"] = incoming.get("source")
    if incoming.get("symbol"):
        merged["symbol"] = str(incoming.get("symbol")).upper()
    if incoming.get("expiry"):
        merged["expiry"] = incoming.get("expiry")
    if incoming.get("option_type"):
        merged["option_type"] = incoming.get("option_type")
    if incoming.get("strike") is not None:
        merged["strike"] = incoming.get("strike")
    if incoming.get("instrument_token") is not None:
        merged["instrument_token"] = incoming.get("instrument_token")
    for field_name in (
        "bid",
        "ask",
        "bid_qty",
        "ask_qty",
        "spread_pct",
        "spread_change_ratio",
        "spread_stability_score",
        "quote_ts_epoch",
        "quote_age_sec",
        "bid_age_sec",
        "ask_age_sec",
    ):
        incoming_value = _safe_float(incoming.get(field_name))
        if incoming_value is not None:
            merged[field_name] = incoming_value
        elif field_name not in merged:
            merged[field_name] = None
    for field_name in ("spread_source", "quote_source", "liquidity_validation_mode"):
        incoming_value = incoming.get(field_name)
        if incoming_value not in (None, "", "None"):
            merged[field_name] = incoming_value
        elif field_name not in merged:
            merged[field_name] = None
    existing_spread = _safe_float(existing.get("spread_pct"))
    incoming_spread = _safe_float(incoming.get("spread_pct"))
    if incoming_spread is not None:
        merged["spread_pct"] = incoming_spread
        if existing_spread is not None and existing_spread > 0:
            spread_change_ratio = abs(float(incoming_spread) - float(existing_spread)) / max(abs(float(existing_spread)), 1e-6)
            merged["spread_change_ratio"] = spread_change_ratio
            full_scale = 1.0
            try:
                from config import config as cfg

                full_scale = max(
                    float(getattr(cfg, "DATA_CONFIDENCE_SPREAD_CHANGE_FULL_SCALE", 1.0) or 1.0),
                    1e-6,
                )
            except Exception:
                full_scale = 1.0
            merged["spread_stability_score"] = max(
                0.0,
                min(1.0, 1.0 - min(float(spread_change_ratio) / full_scale, 1.0)),
            )
        elif merged.get("spread_stability_score") is None:
            merged["spread_stability_score"] = 1.0
    return merged


def _prime_from_snapshot_file() -> None:
    global _LAST_SNAPSHOT_LOAD_EPOCH, _LAST_SNAPSHOT_MTIME
    path = data_root() / "option_chain_latest.json"
    try:
        stat = path.stat()
    except Exception:
        return
    mtime = float(stat.st_mtime)
    if mtime <= _LAST_SNAPSHOT_MTIME and _LAST_SNAPSHOT_LOAD_EPOCH > 0:
        return
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return
    if not isinstance(raw, dict):
        return
    for symbol, rows in raw.items():
        if isinstance(rows, (list, tuple)):
            update_option_liquidity_cache(rows, symbol=symbol)
    _LAST_SNAPSHOT_LOAD_EPOCH = float(now_utc_epoch())
    _LAST_SNAPSHOT_MTIME = mtime


def update_option_liquidity_cache(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    symbol: str | None = None,
    snapshot_ts_epoch: float | None = None,
    source: str = "option_chain_snapshot",
) -> None:
    for raw_row in list(rows or []):
        if not isinstance(raw_row, dict):
            continue
        if _is_synthetic_liquidity_row(raw_row):
            continue
        payload = {
            "symbol": str(raw_row.get("symbol") or symbol or "").strip().upper() or None,
            "expiry": _coerce_expiry(raw_row.get("expiry") or raw_row.get("expiry_date")),
            "strike": _coerce_strike(raw_row.get("strike")),
            "option_type": _coerce_option_type(
                raw_row.get("type") or raw_row.get("option_type") or raw_row.get("right") or raw_row.get("instrument_type")
            ),
            "instrument_token": _coerce_token(raw_row.get("instrument_token")),
            "volume": _safe_float(raw_row.get("volume")),
            "current_volume": _safe_float(raw_row.get("current_volume")),
            "oi": _safe_float(raw_row.get("oi")),
            "oi_change": _safe_float(raw_row.get("oi_change")),
            "bid": _safe_float(raw_row.get("best_bid") if raw_row.get("best_bid") is not None else raw_row.get("bid")),
            "ask": _safe_float(raw_row.get("best_ask") if raw_row.get("best_ask") is not None else raw_row.get("ask")),
            "bid_qty": _safe_float(raw_row.get("bid_qty")),
            "ask_qty": _safe_float(raw_row.get("ask_qty")),
            "spread_pct": _safe_float(raw_row.get("spread_pct")),
            "spread_change_ratio": _safe_float(raw_row.get("spread_change_ratio")),
            "spread_stability_score": _safe_float(raw_row.get("spread_stability_score")),
            "quote_ts_epoch": _safe_float(raw_row.get("quote_ts_epoch")),
            "quote_age_sec": _safe_float(raw_row.get("quote_age_sec")),
            "bid_age_sec": _safe_float(raw_row.get("bid_age_sec")),
            "ask_age_sec": _safe_float(raw_row.get("ask_age_sec")),
            "spread_source": raw_row.get("spread_source") or raw_row.get("price_source") or source,
            "quote_source": raw_row.get("quote_source") or raw_row.get("price_source"),
            "liquidity_validation_mode": raw_row.get("liquidity_validation_mode"),
            "snapshot_ts_epoch": _snapshot_epoch(raw_row, snapshot_ts_epoch),
            "source": source,
        }
        token = payload.get("instrument_token")
        contract_key = _contract_key(
            payload.get("symbol"),
            payload.get("expiry"),
            payload.get("strike"),
            payload.get("option_type"),
        )
        if token is None and contract_key is None:
            continue
        if (
            payload.get("volume") is None
            and payload.get("current_volume") is None
            and payload.get("oi") is None
            and payload.get("oi_change") is None
            and payload.get("bid") is None
            and payload.get("ask") is None
            and payload.get("spread_pct") is None
            and payload.get("quote_ts_epoch") is None
        ):
            continue
        if payload.get("current_volume") is None and payload.get("volume") is not None:
            payload["current_volume"] = payload.get("volume")
        if token is not None:
            _LIQUIDITY_BY_TOKEN[token] = _merge_payload(_LIQUIDITY_BY_TOKEN.get(token), payload)
        if contract_key is not None:
            _LIQUIDITY_BY_CONTRACT[contract_key] = _merge_payload(_LIQUIDITY_BY_CONTRACT.get(contract_key), payload)


def lookup_option_liquidity(
    *,
    instrument_token: Any = None,
    symbol: Any = None,
    expiry: Any = None,
    strike: Any = None,
    option_type: Any = None,
) -> dict[str, Any]:
    token = _coerce_token(instrument_token)
    if token is not None and token in _LIQUIDITY_BY_TOKEN:
        return dict(_LIQUIDITY_BY_TOKEN[token])
    contract_key = _contract_key(symbol, expiry, strike, option_type)
    if contract_key is not None and contract_key in _LIQUIDITY_BY_CONTRACT:
        return dict(_LIQUIDITY_BY_CONTRACT[contract_key])
    _prime_from_snapshot_file()
    if token is not None and token in _LIQUIDITY_BY_TOKEN:
        return dict(_LIQUIDITY_BY_TOKEN[token])
    if contract_key is not None and contract_key in _LIQUIDITY_BY_CONTRACT:
        return dict(_LIQUIDITY_BY_CONTRACT[contract_key])
    return {}


def hydrate_option_liquidity_fields(
    row: dict[str, Any],
    *,
    symbol: Any = None,
    expiry: Any = None,
    strike: Any = None,
    option_type: Any = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    out = dict(row or {})
    payload = lookup_option_liquidity(
        instrument_token=out.get("instrument_token"),
        symbol=out.get("symbol") or symbol,
        expiry=out.get("expiry") or out.get("expiry_date") or expiry,
        strike=out.get("strike") if out.get("strike") is not None else strike,
        option_type=out.get("type") or out.get("option_type") or out.get("right") or option_type,
    )
    cache_hit = bool(payload)
    for field_name, source_fields in (
        ("volume", ("volume", "current_volume")),
        ("current_volume", ("current_volume", "volume")),
        ("oi", ("oi",)),
        ("oi_change", ("oi_change",)),
        ("bid", ("bid",)),
        ("ask", ("ask",)),
        ("bid_qty", ("bid_qty",)),
        ("ask_qty", ("ask_qty",)),
        ("spread_pct", ("spread_pct",)),
        ("spread_change_ratio", ("spread_change_ratio",)),
        ("spread_stability_score", ("spread_stability_score",)),
        ("quote_ts_epoch", ("quote_ts_epoch",)),
        ("quote_age_sec", ("quote_age_sec",)),
        ("bid_age_sec", ("bid_age_sec", "quote_age_sec")),
        ("ask_age_sec", ("ask_age_sec", "quote_age_sec")),
    ):
        if _safe_float(out.get(field_name)) is not None:
            continue
        for source_field in source_fields:
            value = _safe_float(payload.get(source_field))
            if value is not None:
                out[field_name] = value
                break
    for field_name, source_fields in (
        ("spread_source", ("spread_source", "source")),
        ("quote_source", ("quote_source", "source")),
        ("liquidity_validation_mode", ("liquidity_validation_mode",)),
    ):
        if out.get(field_name) not in (None, "", "None"):
            continue
        for source_field in source_fields:
            value = payload.get(source_field)
            if value not in (None, "", "None"):
                out[field_name] = value
                break
    if cache_hit:
        snapshot_ts_epoch = _safe_float(payload.get("snapshot_ts_epoch"))
        if snapshot_ts_epoch is not None:
            liquidity_age_sec = max(0.0, float((now_epoch if now_epoch is not None else now_utc_epoch())) - snapshot_ts_epoch)
            if out.get("liquidity_age_sec") is None:
                out["liquidity_age_sec"] = liquidity_age_sec
            if out.get("chain_snapshot_age_sec") is None:
                out["chain_snapshot_age_sec"] = liquidity_age_sec
            if out.get("cache_age_sec") is None:
                out["cache_age_sec"] = liquidity_age_sec
        if not out.get("liquidity_source"):
            out["liquidity_source"] = str(payload.get("source") or "option_liquidity_cache")
    if out.get("liquidity_cache_hit") is None:
        out["liquidity_cache_hit"] = cache_hit
    out["liquidity_missing_fields"] = [
        field_name
        for field_name in ("volume", "current_volume", "oi", "oi_change")
        if _safe_float(out.get(field_name)) is None
    ]
    return out


def clear_option_liquidity_cache() -> None:
    global _LAST_SNAPSHOT_LOAD_EPOCH, _LAST_SNAPSHOT_MTIME
    _LIQUIDITY_BY_TOKEN.clear()
    _LIQUIDITY_BY_CONTRACT.clear()
    _LAST_SNAPSHOT_LOAD_EPOCH = 0.0
    _LAST_SNAPSHOT_MTIME = 0.0
