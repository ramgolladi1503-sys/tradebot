"""Option instrument token resolver.

Migration note:
Resolves option instrument tokens without caching per-expiry results.
"""

from __future__ import annotations

from datetime import datetime, date
import json
import time
from typing import Any

from config import config as cfg
from core.instruments import build_option_registry, log_requested_expiry_missing
from core.kite_client import kite_client
from core.log_writer import get_jsonl_writer
from core.paths import data_root, logs_dir
from core.time_utils import utc_now

_LOG_PATH = logs_dir() / "option_token_resolution.jsonl"
_LOGGER = get_jsonl_writer(_LOG_PATH)
_STATS_LOG_TS: dict[tuple[str, str, str], float] = {}


class TokenCoverageError(Exception):
    """Raised when option token coverage for a symbol/expiry is below threshold."""

    def __init__(self, *, code: str, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.evidence = dict(evidence or {})


def _coerce_expiry(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        text = str(value).split("T", 1)[0]
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _load_local_instruments_cache(exchange: str) -> list[dict]:
    cache_path = data_root() / "kite_instruments.json"
    if not cache_path.exists():
        return []
    try:
        raw = json.loads(cache_path.read_text())
    except Exception:
        return []
    if isinstance(raw, dict):
        bucket = raw.get(exchange)
        if isinstance(bucket, list):
            return list(bucket)
        return []
    if isinstance(raw, list):
        return list(raw)
    return []


def _load_instruments(exchange: str) -> tuple[list[dict], str]:
    local = _load_local_instruments_cache(exchange)
    if local:
        return local, "local_cache"
    ttl_sec = int(getattr(cfg, "OPTION_TOKEN_RESOLVER_CACHE_TTL_SEC", 3600))
    try:
        data = kite_client.instruments_cached(exchange, ttl_sec=max(0, ttl_sec))
    except Exception:
        data = []
    if isinstance(data, list) and data:
        return data, "kite_client_cache"
    return [], "missing"


def _iter_registry_matches_for_expiry(
    registry: dict,
    *,
    sym: str,
    segment: str,
    expiry: date,
) -> list[dict]:
    out: list[dict] = []
    for key, value in (registry or {}).items():
        try:
            key_sym, key_segment, key_strike, key_opt_type, key_expiry = key
        except Exception:
            continue
        if key_sym != sym or key_segment != segment or key_expiry != expiry:
            continue
        if not isinstance(value, dict):
            continue
        token = value.get("instrument_token")
        if token in (None, "", "None"):
            continue
        out.append(
            {
                "instrument_token": int(token),
                "tradingsymbol": value.get("tradingsymbol"),
                "strike": float(key_strike),
                "option_type": str(key_opt_type),
            }
        )
    out.sort(key=lambda row: (row.get("strike", 0.0), row.get("option_type", "")))
    return out


def _log_registry_stats(
    *,
    sym: str,
    exchange: str,
    segment: str,
    expiry: date,
    registry: dict,
    data_source: str,
) -> None:
    now_ts = time.time()
    log_key = (sym, segment, expiry.isoformat())
    last_ts = float(_STATS_LOG_TS.get(log_key, 0.0) or 0.0)
    if (now_ts - last_ts) < 30.0:
        return
    _STATS_LOG_TS[log_key] = now_ts
    rows = _iter_registry_matches_for_expiry(
        registry,
        sym=sym,
        segment=segment,
        expiry=expiry,
    )
    sample = rows[:8]
    _LOGGER.write(
        {
            "ts": utc_now().isoformat(),
            "event": "OPTION_TOKEN_REGISTRY_STATS",
            "symbol": sym,
            "exchange": exchange,
            "segment": segment,
            "expiry": expiry.isoformat(),
            "resolved_tokens_count": len(rows),
            "sample_tokens": [int(r.get("instrument_token")) for r in sample if r.get("instrument_token") is not None],
            "sample_tradingsymbols": [str(r.get("tradingsymbol") or "") for r in sample if r.get("tradingsymbol")],
            "registry_size": len(registry or {}),
            "data_source": data_source,
        }
    )
    min_required = int(getattr(cfg, "MIN_OPTION_TOKENS", 20))
    if len(rows) < max(1, min_required):
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_REGISTRY_UNDER_MIN",
                "symbol": sym,
                "exchange": exchange,
                "segment": segment,
                "expiry": expiry.isoformat(),
                "resolved_tokens_count": len(rows),
                "min_required": int(min_required),
                "data_source": data_source,
            }
        )


def _min_option_token_count() -> int:
    raw = getattr(cfg, "MIN_OPTION_TOKEN_COUNT", None)
    if raw is None:
        raw = getattr(cfg, "MIN_OPTION_TOKENS", 50)
    try:
        return max(1, int(raw))
    except Exception:
        return 50


def _max_fallback_expiry_days() -> int:
    raw = getattr(cfg, "OPTION_TOKEN_FALLBACK_MAX_EXPIRY_DAYS", 7)
    try:
        return max(0, int(raw))
    except Exception:
        return 7


def _max_fallback_strike_distance(symbol: str) -> float:
    attr_name = "SENSEX_OPTION_TOKEN_FALLBACK_MAX_STRIKE_DISTANCE" if str(symbol or "").upper() == "SENSEX" else "OPTION_TOKEN_FALLBACK_MAX_STRIKE_DISTANCE"
    raw = getattr(cfg, attr_name, None)
    if raw is None:
        raw = 100 if str(symbol or "").upper() == "SENSEX" else 50
    try:
        return max(0.0, float(raw))
    except Exception:
        return 100.0 if str(symbol or "").upper() == "SENSEX" else 50.0


def _safe_fallback_enabled() -> bool:
    raw = getattr(cfg, "OPTION_TOKEN_SAFE_FALLBACK_ENABLED", True)
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _fallback_candidate_rows(
    registry: dict,
    *,
    sym: str,
    segment: str,
    opt_type: str,
) -> list[tuple[tuple, dict]]:
    rows: list[tuple[tuple, dict]] = []
    for key, value in (registry or {}).items():
        try:
            key_sym, key_segment, _key_strike, key_opt_type, _key_expiry = key
        except Exception:
            continue
        if key_sym != sym or key_segment != segment or key_opt_type != opt_type:
            continue
        if not isinstance(value, dict):
            continue
        token = value.get("instrument_token")
        if token in (None, "", "None"):
            continue
        rows.append((key, value))
    return rows


def _find_safe_fallback_contract(
    *,
    registry: dict,
    sym: str,
    segment: str,
    requested_expiry: date,
    requested_strike: float,
    opt_type: str,
) -> dict | None:
    """Find a nearby listed contract when candidate generation is slightly off.

    This is intentionally conservative. It only falls back within the same
    symbol, segment and option type, and only when expiry/strike distance remain
    inside configured guardrails.
    """
    if not _safe_fallback_enabled():
        return None
    max_days = _max_fallback_expiry_days()
    max_strike_distance = _max_fallback_strike_distance(sym)
    candidates = []
    for key, value in _fallback_candidate_rows(registry, sym=sym, segment=segment, opt_type=opt_type):
        key_sym, key_segment, key_strike, key_opt_type, key_expiry = key
        try:
            strike_distance = abs(float(key_strike) - float(requested_strike))
        except Exception:
            continue
        expiry_distance_days = abs((key_expiry - requested_expiry).days)
        if expiry_distance_days > max_days:
            continue
        if strike_distance > max_strike_distance:
            continue
        candidates.append(
            (
                expiry_distance_days,
                strike_distance,
                key_expiry,
                float(key_strike),
                key,
                value,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    expiry_distance_days, strike_distance, _exp, _strike, key, value = candidates[0]
    token = value.get("instrument_token")
    if token in (None, "", "None"):
        return None
    return {
        "instrument_token": int(token),
        "tradingsymbol": value.get("tradingsymbol"),
        "exchange": "BFO" if segment == "BFO-OPT" else "NFO",
        "segment": segment,
        "resolved_expiry": key[4],
        "resolved_strike": float(key[2]),
        "requested_expiry": requested_expiry,
        "requested_strike": float(requested_strike),
        "expiry_distance_days": int(expiry_distance_days),
        "strike_distance": float(strike_distance),
        "resolution_path": "safe_nearest_contract_fallback",
    }


def _enforce_token_coverage_threshold(
    *,
    sym: str,
    exchange: str,
    segment: str,
    exp: date,
    strike_val: float,
    opt_type: str,
    rows_for_expiry: list[dict],
    data_source: str,
) -> None:
    min_required = _min_option_token_count()
    resolved_count = len(rows_for_expiry or [])
    if resolved_count >= min_required:
        return
    sample_tokens = [
        int(r.get("instrument_token"))
        for r in rows_for_expiry[:10]
        if r.get("instrument_token") is not None
    ]
    evidence = {
        "symbol": sym,
        "exchange": exchange,
        "segment": segment,
        "expiry": exp.isoformat(),
        "strike": float(strike_val),
        "option_type": opt_type,
        "resolved_option_tokens_count": int(resolved_count),
        "min_option_token_count": int(min_required),
        "sample_tokens": sample_tokens,
        "data_source": data_source,
    }
    _LOGGER.write(
        {
            "ts": utc_now().isoformat(),
            "event": "OPTION_TOKEN_COVERAGE_BELOW_THRESHOLD",
            "code": "TOKEN_COVERAGE_BELOW_THRESHOLD",
            **evidence,
        }
    )
    raise TokenCoverageError(
        code="TOKEN_COVERAGE_BELOW_THRESHOLD",
        message=(
            "resolved option token coverage below threshold: "
            f"resolved={resolved_count} min_required={min_required} "
            f"symbol={sym} expiry={exp.isoformat()}"
        ),
        evidence=evidence,
    )


def _allow_exact_match_below_threshold(data_source: str) -> bool:
    source = str(data_source or "").strip().lower()
    return source in {"local_cache", "file_cache"}


def _token_payload_from_exact_match(*, token: int, entry: dict, exchange: str, segment: str) -> dict:
    return {
        "instrument_token": token,
        "tradingsymbol": entry.get("tradingsymbol"),
        "exchange": exchange,
        "segment": segment,
        "resolution_path": "exact_contract_match",
        "fallback_candidate": False,
        "candidate_origin": "exact_contract",
    }


def is_safe_nearest_contract_fallback(resolution: dict | None) -> bool:
    if not isinstance(resolution, dict):
        return False
    return str(resolution.get("resolution_path") or "").strip().lower() == "safe_nearest_contract_fallback"


def resolve_option_token(
    symbol: str,
    expiry_date: str | date,
    strike: float,
    option_type: str,
    exchange: str | None = None,
) -> dict | None:
    sym = _norm_text(symbol)
    opt_type = _norm_text(option_type)
    exp = _coerce_expiry(expiry_date)
    if not sym or not opt_type or exp is None or strike is None:
        return None
    try:
        strike_val = float(strike)
    except Exception:
        return None
    exchange = (exchange or ("BFO" if sym == "SENSEX" else "NFO")).upper()
    segment = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
    data, data_source = _load_instruments(exchange)
    if not data:
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLUTION_EMPTY",
                "symbol": sym,
                "expiry": str(exp),
                "strike": strike,
                "option_type": opt_type,
                "exchange": exchange,
                "data_source": data_source,
            }
        )
        return None
    registry_payload = build_option_registry(
        symbol=sym,
        instruments=data,
        exchange=exchange,
    )
    registry = registry_payload.get("registry") or {}
    _log_registry_stats(
        sym=sym,
        exchange=exchange,
        segment=segment,
        expiry=exp,
        registry=registry,
        data_source=data_source,
    )
    rows_for_expiry = _iter_registry_matches_for_expiry(
        registry,
        sym=sym,
        segment=segment,
        expiry=exp,
    )
    key = (sym, segment, strike_val, opt_type, exp)
    entry = registry.get(key)
    exact_match_exists = isinstance(entry, dict) and entry.get("instrument_token")
    if _allow_exact_match_below_threshold(data_source) and exact_match_exists:
        token = int(entry.get("instrument_token"))
        payload = _token_payload_from_exact_match(token=token, entry=entry, exchange=exchange, segment=segment)
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLVED",
                "symbol": sym,
                "expiry": str(exp),
                "strike": float(strike_val),
                "option_type": opt_type,
                "instrument_token": token,
                "tradingsymbol": entry.get("tradingsymbol"),
                "exchange": exchange,
                "data_source": data_source,
                "resolution_path": "exact_contract_match",
            }
        )
        return payload
    _enforce_token_coverage_threshold(
        sym=sym,
        exchange=exchange,
        segment=segment,
        exp=exp,
        strike_val=strike_val,
        opt_type=opt_type,
        rows_for_expiry=rows_for_expiry,
        data_source=data_source,
    )
    if exact_match_exists:
        token = int(entry.get("instrument_token"))
        payload = _token_payload_from_exact_match(token=token, entry=entry, exchange=exchange, segment=segment)
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLVED",
                "symbol": sym,
                "expiry": str(exp),
                "strike": float(strike_val),
                "option_type": opt_type,
                "instrument_token": token,
                "tradingsymbol": entry.get("tradingsymbol"),
                "exchange": exchange,
                "data_source": data_source,
                "resolution_path": "exact_contract_match",
            }
        )
        return payload

    fallback = _find_safe_fallback_contract(
        registry=registry,
        sym=sym,
        segment=segment,
        requested_expiry=exp,
        requested_strike=strike_val,
        opt_type=opt_type,
    )
    if fallback:
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLVED",
                "symbol": sym,
                "expiry": str(exp),
                "strike": float(strike_val),
                "option_type": opt_type,
                "instrument_token": fallback.get("instrument_token"),
                "tradingsymbol": fallback.get("tradingsymbol"),
                "exchange": exchange,
                "data_source": data_source,
                "resolution_path": "safe_nearest_contract_fallback",
                "requested_expiry": fallback.get("requested_expiry").isoformat() if fallback.get("requested_expiry") else None,
                "resolved_expiry": fallback.get("resolved_expiry").isoformat() if fallback.get("resolved_expiry") else None,
                "requested_strike": fallback.get("requested_strike"),
                "resolved_strike": fallback.get("resolved_strike"),
                "expiry_distance_days": fallback.get("expiry_distance_days"),
                "strike_distance": fallback.get("strike_distance"),
            }
        )
        return {
            "instrument_token": fallback.get("instrument_token"),
            "tradingsymbol": fallback.get("tradingsymbol"),
            "exchange": exchange,
            "segment": segment,
            "resolution_path": "safe_nearest_contract_fallback",
            "fallback_candidate": True,
            "candidate_origin": "fallback",
            "requested_expiry": fallback.get("requested_expiry"),
            "resolved_expiry": fallback.get("resolved_expiry"),
            "requested_strike": fallback.get("requested_strike"),
            "resolved_strike": fallback.get("resolved_strike"),
        }

    available_expiries = sorted(
        {
            k[4]
            for k in registry.keys()
            if k[0] == sym and k[1] == segment and k[3] == opt_type and abs(float(k[2]) - strike_val) <= 1e-6
        }
    )
    if available_expiries:
        log_requested_expiry_missing(
            symbol=sym,
            requested_expiry=exp,
            available_expiries=available_expiries,
            context="option_token_resolver",
        )
    _LOGGER.write(
        {
            "ts": utc_now().isoformat(),
            "event": "OPTION_TOKEN_NOT_FOUND",
            "symbol": sym,
            "expiry": str(exp),
            "strike": float(strike_val),
            "option_type": opt_type,
            "exchange": exchange,
            "available_expiries": [d.isoformat() for d in available_expiries],
            "data_source": data_source,
        }
    )
    return None
