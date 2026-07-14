from __future__ import annotations

from datetime import datetime
from typing import Any

from config import config as cfg
from core.contracts.invariants import assert_invariants
from core.freshness_sla import get_freshness_status
from core.market_snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    normalize_symbol_snapshot,
    validate_market_snapshot,
)
from core.snapshot_schema import compute_snapshot_id
from core.tick_store import get_latest_tick_db, get_latest_tick_rows_db
from core.time_utils import normalize_epoch_seconds, now_ist, now_utc_epoch


def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_tokens(tokens: list[int] | tuple[int, ...] | None) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for token in list(tokens or []):
        tok = _to_int(token)
        if tok is None or tok <= 0 or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _coerce_expiry_date(expiry_date: str | None) -> str | None:
    text = str(expiry_date or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _is_expiry_day(symbol: str, expiry_date: str | None) -> bool:
    del symbol  # v1 does not need symbol-specific calendar overrides here.
    exp = _coerce_expiry_date(expiry_date)
    if not exp:
        return False
    try:
        return exp == now_ist().date().isoformat()
    except Exception:
        return False


def _min_option_token_count() -> int:
    raw = getattr(cfg, "MIN_OPTION_TOKEN_COUNT", None)
    if raw is None:
        raw = getattr(cfg, "MIN_OPTION_TOKENS", 50)
    try:
        return max(1, int(raw))
    except Exception:
        return 50


def _tick_payload(token: int, row: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(row or {})
    ts_epoch = normalize_epoch_seconds(row.get("ts_epoch"))
    return {
        "instrument_token": int(token),
        "last_price": row.get("ltp"),
        "timestamp_epoch": ts_epoch,
        "volume": row.get("volume"),
        "oi": row.get("oi"),
    }


def _freshness_blocker(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "FRESHNESS_FAILED",
        "message": "freshness SLA failed for snapshot tokens",
        "evidence": {
            "state": payload.get("state"),
            "reasons": list(payload.get("reasons") or []),
            "stale_tokens": list(payload.get("stale_tokens") or []),
            "max_tick_age_sec": payload.get("max_tick_age_sec"),
            "sla_threshold_sec": payload.get("sla_threshold_sec"),
            "ltp_source": ((payload.get("ltp") or {}).get("source")),
        },
    }


def _build_tick_health_snapshot(
    symbol: str,
    index_token: int,
    option_tokens: list[int],
    *,
    strike_window: dict,
    expiry_date: str | None,
) -> dict:
    symbol_norm = _norm_symbol(symbol)
    now_epoch = float(now_utc_epoch())
    idx_token = _to_int(index_token) or 0
    opt_tokens = _normalize_tokens(option_tokens)
    blockers: list[dict[str, Any]] = []

    index_row = get_latest_tick_db(idx_token) if idx_token > 0 else None
    option_rows = get_latest_tick_rows_db(opt_tokens) if opt_tokens else {}

    option_ticks: dict[str, dict[str, Any]] = {}
    missing_option_tokens: list[int] = []
    for token in opt_tokens:
        row = option_rows.get(token)
        option_ticks[str(token)] = _tick_payload(token, row)
        if row is None:
            missing_option_tokens.append(token)

    if idx_token <= 0:
        blockers.append(
            {
                "code": "INDEX_TOKEN_MISSING",
                "message": "index token is missing or invalid",
                "evidence": {"index_token": index_token},
            }
        )
    if not opt_tokens:
        blockers.append(
            {
                "code": "OPTION_TOKEN_MISSING",
                "message": "option token list is empty",
                "evidence": {"option_tokens_count": 0},
            }
        )
    if missing_option_tokens:
        blockers.append(
            {
                "code": "OPTION_TICK_MISSING",
                "message": "missing latest tick rows for some option tokens",
                "evidence": {
                    "missing_tokens_count": len(missing_option_tokens),
                    "missing_tokens_sample": missing_option_tokens[:20],
                },
            }
        )

    min_tokens = _min_option_token_count()
    if len(opt_tokens) < min_tokens:
        blockers.append(
            {
                "code": "TOKEN_COVERAGE_BELOW_THRESHOLD",
                "message": "option token coverage below minimum threshold",
                "evidence": {
                    "resolved_option_tokens_count": len(opt_tokens),
                    "min_option_token_count": min_tokens,
                },
            }
        )

    tracked_tokens = [idx_token] + opt_tokens if idx_token > 0 else list(opt_tokens)
    freshness_payload = get_freshness_status(
        symbol=symbol_norm or None,
        tokens=tracked_tokens,
        force=True,
    )
    freshness_ok = bool(freshness_payload.get("ok"))
    if not freshness_ok:
        blockers.append(_freshness_blocker(freshness_payload))

    max_tick_age_sec = freshness_payload.get("max_tick_age_sec")
    if max_tick_age_sec is None:
        max_tick_age_sec = 0.0 if freshness_ok else float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))

    snapshot: dict[str, Any] = {
        "schema_version": "1.0",
        "snapshot_id": "",
        "timestamp_epoch": now_epoch,
        "symbol": symbol_norm,
        "token_coverage": {
            "index_token": idx_token,
            "option_tokens_count": len(opt_tokens),
            "option_tokens": list(opt_tokens),
            "strike_window": dict(strike_window or {}),
        },
        "freshness": {
            "sla_threshold_sec": float(freshness_payload.get("sla_threshold_sec") or 0.0),
            "max_tick_age_sec": float(max_tick_age_sec),
            "stale_tokens_count": len(list(freshness_payload.get("stale_tokens") or [])),
        },
        "ticks": {
            "index": _tick_payload(idx_token, index_row) if idx_token > 0 else {},
            "options": option_ticks,
        },
        "expiry": {
            "is_expiry_day": _is_expiry_day(symbol_norm, expiry_date),
            "expiry_date": _coerce_expiry_date(expiry_date),
        },
        "regime": {
            "state": "UNKNOWN",
            "confidence": None,
        },
        "health": {
            "ok": bool(not blockers),
            "blockers": blockers,
        },
        "data_sources": {
            "ticks": "sqlite",
            "token_resolution": "resolver",
        },
    }
    snapshot["snapshot_id"] = compute_snapshot_id(snapshot)
    assert_invariants(snapshot, stage="snapshot_builder")
    return snapshot


def build_symbol_market_snapshot(
    *,
    spot=None,
    ltp=None,
    change_pct=None,
    ohlc=None,
    regime=None,
    cross_asset=None,
    option_chain_summary=None,
    feed_health=None,
    quote_truth=None,
) -> dict[str, Any]:
    return normalize_symbol_snapshot(
        {
            "spot": spot,
            "ltp": ltp,
            "change_pct": change_pct,
            "ohlc": dict(ohlc or {}),
            "regime": dict(regime or {}),
            "cross_asset": dict(cross_asset or {}),
            "option_chain_summary": dict(option_chain_summary or {}),
            "feed_health": dict(feed_health or {}),
            "quote_truth": dict(quote_truth or {}),
        }
    )


def _build_dashboard_market_snapshot(
    *,
    generated_at: str,
    market_open: bool,
    symbols_payload: dict,
    warnings: list[str] | None = None,
    compute_ms: float | None = None,
    loop_id: str | None = None,
) -> dict[str, Any]:
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": str(generated_at or "").strip(),
        "source": "engine",
        "market_open": bool(market_open),
        "symbols": {
            str(symbol or "").upper(): build_symbol_market_snapshot(**dict(payload or {}))
            for symbol, payload in dict(symbols_payload or {}).items()
            if str(symbol or "").strip()
        },
        "warnings": [str(item) for item in list(warnings or []) if str(item or "").strip()],
        "producer_meta": {
            "compute_ms": None if compute_ms is None else float(compute_ms),
            "loop_id": None if loop_id is None else str(loop_id),
        },
    }
    ok, errors = validate_market_snapshot(snapshot)
    if not ok:
        raise ValueError(f"invalid_market_snapshot:{'|'.join(errors)}")
    return snapshot


def build_market_snapshot(*args, **kwargs) -> dict:
    if "generated_at" in kwargs or "symbols_payload" in kwargs:
        return _build_dashboard_market_snapshot(**kwargs)
    return _build_tick_health_snapshot(*args, **kwargs)

def build_market_snapshot_from_raw_tick(raw_event: dict) -> dict[str, Any]:
    """
    Pure adapter to map a recorded raw broker feed event directly into the live normalization pipeline.
    """
    raw_tick = dict(raw_event.get("raw_tick") or {})
    return build_symbol_market_snapshot(
        spot=raw_tick.get("last_price"),
        ltp=raw_tick.get("last_price"),
        change_pct=raw_tick.get("change"),
        ohlc=dict(raw_tick.get("ohlc") or {}),
        regime=None,
        cross_asset=None,
        option_chain_summary=None,
        feed_health=None,
        quote_truth=None,
    )
