from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


SNAPSHOT_SCHEMA_VERSION = 1


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_ohlc() -> dict[str, float | None]:
    return {
        "open": None,
        "high": None,
        "low": None,
        "close": None,
    }


def _default_regime() -> dict[str, Any]:
    return {
        "trend": None,
        "volatility_state": None,
        "confidence": None,
    }


def _default_cross_asset() -> dict[str, Any]:
    return {
        "available": False,
        "signals": {},
    }


def _default_option_chain_summary() -> dict[str, Any]:
    return {
        "atm_strike": None,
        "pcr": None,
        "max_pain": None,
        "chain_quality": None,
    }


def _default_feed_health() -> dict[str, Any]:
    return {
        "underlying_quote_age_sec": None,
        "option_quote_age_sec": None,
        "status": None,
    }


def _default_quote_truth() -> dict[str, Any]:
    return {
        "symbol": None,
        "ltp": None,
        "bid": None,
        "ask": None,
        "spread": None,
        "last_tick_ts": None,
        "tick_age_seconds": None,
        "quote_truth": None,
        "is_fresh": False,
        "is_executable_quote": False,
        "source": None,
    }


def build_symbol_snapshot_defaults() -> dict[str, Any]:
    return {
        "spot": None,
        "ltp": None,
        "change_pct": None,
        "ohlc": _default_ohlc(),
        "regime": _default_regime(),
        "cross_asset": _default_cross_asset(),
        "option_chain_summary": _default_option_chain_summary(),
        "feed_health": _default_feed_health(),
        "quote_truth": _default_quote_truth(),
        "metadata": {},
    }


def build_empty_market_snapshot_state(reason: str) -> dict[str, Any]:
    reason_text = str(reason or "").strip() or "snapshot_unavailable"
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": _utc_iso_now(),
        "source": "engine",
        "market_open": False,
        "symbols": {},
        "warnings": [reason_text],
        "producer_meta": {
            "compute_ms": None,
            "loop_id": None,
        },
    }


def _is_json_serializable(payload: dict[str, Any]) -> bool:
    try:
        json.dumps(payload, ensure_ascii=True, allow_nan=False)
        return True
    except Exception:
        return False


def _is_non_negative_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) >= 0.0
    except Exception:
        return False


def _coerce_iso8601(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        datetime.fromisoformat(text)
        return True
    except Exception:
        return False


def validate_market_snapshot(snapshot: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return False, ["snapshot_not_object"]

    if int(snapshot.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        errors.append("schema_version_invalid")
    if not _coerce_iso8601(snapshot.get("generated_at")):
        errors.append("generated_at_missing_or_invalid")
    if str(snapshot.get("source") or "").strip() == "":
        errors.append("source_missing")
    if not isinstance(snapshot.get("market_open"), bool):
        errors.append("market_open_missing_or_invalid")
    symbols = snapshot.get("symbols")
    if not isinstance(symbols, dict):
        errors.append("symbols_missing_or_invalid")
        symbols = {}
    warnings = snapshot.get("warnings")
    if not isinstance(warnings, list):
        errors.append("warnings_missing_or_invalid")
    producer_meta = snapshot.get("producer_meta")
    if not isinstance(producer_meta, dict):
        errors.append("producer_meta_missing_or_invalid")

    required_sections = {
        "ohlc": _default_ohlc,
        "regime": _default_regime,
        "cross_asset": _default_cross_asset,
        "option_chain_summary": _default_option_chain_summary,
        "feed_health": _default_feed_health,
        "quote_truth": _default_quote_truth,
    }
    for symbol, payload in list(symbols.items()):
        if str(symbol or "").strip() == "":
            errors.append("symbol_key_missing")
            continue
        if not isinstance(payload, dict):
            errors.append(f"symbol_payload_invalid:{symbol}")
            continue
        for section_name, builder in required_sections.items():
            section = payload.get(section_name)
            if not isinstance(section, dict):
                errors.append(f"{symbol}:{section_name}_missing_or_invalid")
                continue
            for key in list(builder().keys()):
                if key not in section:
                    errors.append(f"{symbol}:{section_name}.{key}_missing")

        feed_health = payload.get("feed_health") if isinstance(payload.get("feed_health"), dict) else {}
        for age_key in ("underlying_quote_age_sec", "option_quote_age_sec"):
            age_val = feed_health.get(age_key)
            if age_val is not None and not _is_non_negative_number(age_val):
                errors.append(f"{symbol}:{age_key}_invalid")

    if not _is_json_serializable(snapshot):
        errors.append("snapshot_not_json_serializable")
    return len(errors) == 0, errors


def normalize_symbol_snapshot(payload: dict[str, Any] | None) -> dict[str, Any]:
    out = build_symbol_snapshot_defaults()
    if not isinstance(payload, dict):
        return out
    for key in ("spot", "ltp", "change_pct"):
        if key in payload:
            out[key] = payload.get(key)
    for section_name in ("ohlc", "regime", "cross_asset", "option_chain_summary", "feed_health", "quote_truth"):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        target = out.get(section_name)
        if not isinstance(target, dict):
            continue
        target.update(deepcopy(section))
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        out["metadata"] = deepcopy(metadata)
    return out
