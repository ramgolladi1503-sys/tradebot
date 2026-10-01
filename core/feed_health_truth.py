from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

GLOBAL_FEED_UNHEALTHY_REASON = "global_feed_unhealthy"
WEBSOCKET_DISCONNECTED_REASON = "websocket_disconnected"
FEED_STATE_UNSAFE_REASON = "feed_state_unsafe"
RUNTIME_STATE_UNSAFE_REASON = "runtime_state_unsafe"
LTP_TICKS_STALE_REASON = "ltp_ticks_stale"
DEPTH_TICKS_STALE_REASON = "depth_ticks_stale"
OPTION_FEED_BLOCKED_REASON = "option_feed_blocked"
OPTION_TICKS_STALE_REASON = "option_ticks_stale"
OPTION_AGE_MISSING_REASON = "option_age_missing"
SYMBOL_FEED_UNKNOWN_REASON = "symbol_feed_unknown"
FEED_HEALTH_TRUTH_BLOCK_REASON = "feed_health_truth_failed"

_OPTION_OK_CODES = {"", "OK", "NONE", "HEALTHY", "FRESH"}
_SAFE_RUNTIME_STATES = {"", "RUNNING", "LIVE", "HEALTHY", "OK", "DEGRADED_LOCAL", "VERIFYING_RECOVERY"}
_SAFE_FEED_STATES = {"", "LIVE", "RUNNING", "HEALTHY", "OK", "DEGRADED_LOCAL", "VERIFYING_RECOVERY"}
FEED_HEALTH_DOMAINS = (
    "INDEX_SPOT",
    "INDEX_FUTURES",
    "INDEX_OPTIONS",
    "STOCK_SPOT",
    "STOCK_OPTIONS",
)
_DOMAIN_HEALTH_STATES = {"HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"}


@dataclass(frozen=True)
class SymbolFeedTruth:
    symbol: str
    feed_ok: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    option_feed_block_reason: str | None = None
    option_last_tick_age_sec: float | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedHealthTruthDecision:
    feed_ok: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    global_feed_ok: bool | None = None
    websocket_ok: bool | None = None
    symbols: tuple[SymbolFeedTruth, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    domains: dict[str, dict[str, str]] = field(default_factory=dict)
    overall_state: str = "UNKNOWN"

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbols"] = [symbol.to_payload() for symbol in self.symbols]
        return payload


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_non_negative_float(value: Any, default: float) -> float:
    out = _safe_float(value)
    if out is None:
        return float(default)
    return max(0.0, float(out))


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "healthy"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded"}:
        return False
    return None


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _normalize_reason(reason: Any) -> str:
    return str(reason or "").strip().upper()


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().upper()


def _domain_health(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return only explicit producer-supplied domain evidence; never infer it."""
    supplied = payload.get("domain_health_by_domain")
    supplied = supplied if isinstance(supplied, dict) else {}
    result: dict[str, dict[str, str]] = {}
    for domain in FEED_HEALTH_DOMAINS:
        raw = next((value for key, value in supplied.items() if _normalize_state(key) == domain), None)
        state = _normalize_state(raw.get("state")) if isinstance(raw, dict) else "UNKNOWN"
        if state not in _DOMAIN_HEALTH_STATES:
            state = "UNKNOWN"
        result[domain.lower()] = {"state": state}
    return result


def _symbols_from_payload(payload: dict[str, Any], requested_symbols: tuple[str, ...]) -> tuple[str, ...]:
    requested = tuple(_normalize_symbol(symbol) for symbol in requested_symbols if _normalize_symbol(symbol))
    if requested:
        return requested

    symbols: set[str] = set()
    for key in (
        "option_feed_block_reason_by_symbol",
        "option_last_tick_age_by_symbol",
    ):
        values = payload.get(key)
        if isinstance(values, dict):
            symbols.update(_normalize_symbol(symbol) for symbol in values if _normalize_symbol(symbol))
    return tuple(sorted(symbols))


def _symbol_value(payload: dict[str, Any], symbol: str, *keys: str) -> Any:
    for key in keys:
        values = payload.get(key)
        if not isinstance(values, dict):
            continue
        for candidate_key, value in values.items():
            if _normalize_symbol(candidate_key) == symbol:
                return value
    return None


def _has_symbol_entry(payload: dict[str, Any], field: str, symbol: str) -> bool:
    values = payload.get(field)
    return isinstance(values, dict) and any(
        _normalize_symbol(candidate) == symbol for candidate in values
    )


def _global_websocket_ok(payload: dict[str, Any]) -> bool | None:
    effective = _bool_or_none(payload.get("effective_ws_connected"))
    if effective is not None:
        return effective
    return _bool_or_none(payload.get("ws_connected"))


def _runtime_state(payload: dict[str, Any]) -> str:
    state = _normalize_state(payload.get("runtime_state"))
    if state:
        return state
    state_machine = _mapping(payload.get("state_machine"))
    return _normalize_state(state_machine.get("runtime_state"))


def _feed_state(payload: dict[str, Any]) -> str:
    state_machine = _mapping(payload.get("state_machine"))
    return _normalize_state(state_machine.get("state"))


def classify_symbol_feed_truth(
    payload: dict[str, Any],
    symbol: str,
    *,
    max_option_tick_age_sec: float,
) -> SymbolFeedTruth:
    normalized = _normalize_symbol(symbol)
    reasons: list[str] = []
    block_reason_raw = _symbol_value(payload, normalized, "option_feed_block_reason_by_symbol")
    block_reason = _normalize_reason(block_reason_raw)
    option_age = _safe_float(_symbol_value(payload, normalized, "option_last_tick_age_by_symbol"))
    symbol_feed_ok = _bool_or_none(
        _symbol_value(payload, normalized, "symbol_feed_ok_by_symbol", "feed_ok_by_symbol")
    )
    symbol_evidence_present = any(
        normalized in {_normalize_symbol(key) for key in (payload.get(field) or {})}
        for field in (
            "option_feed_block_reason_by_symbol",
            "option_last_tick_age_by_symbol",
            "symbol_feed_ok_by_symbol",
            "feed_ok_by_symbol",
        )
        if isinstance(payload.get(field), dict)
    )

    if block_reason not in _OPTION_OK_CODES:
        _append_unique(reasons, OPTION_FEED_BLOCKED_REASON)
    if option_age is None:
        _append_unique(reasons, OPTION_AGE_MISSING_REASON)
    elif option_age > max_option_tick_age_sec:
        _append_unique(reasons, OPTION_TICKS_STALE_REASON)
    if not symbol_evidence_present:
        _append_unique(reasons, SYMBOL_FEED_UNKNOWN_REASON)
    if symbol_feed_ok is False:
        _append_unique(reasons, SYMBOL_FEED_UNKNOWN_REASON if not reasons else None)

    feed_ok = not reasons and symbol_feed_ok is not False
    return SymbolFeedTruth(
        symbol=normalized,
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else FEED_HEALTH_TRUTH_BLOCK_REASON,
        reasons=tuple(reasons),
        option_feed_block_reason=None if block_reason in _OPTION_OK_CODES else block_reason.lower(),
        option_last_tick_age_sec=option_age,
        context={"symbol_feed_ok": symbol_feed_ok, "max_option_tick_age_sec": max_option_tick_age_sec},
    )


def classify_feed_health_truth(
    payload: dict[str, Any] | None,
    *,
    symbols: tuple[str, ...] | list[str] = (),
    max_option_tick_age_sec: float = 3.0,
    max_ltp_age_sec: float | None = None,
    max_depth_age_sec: float | None = None,
    required_domains: tuple[str, ...] | list[str] = (),
) -> FeedHealthTruthDecision:
    """Reconcile global, runtime, websocket, and per-symbol feed health.

    This is read-only evidence. It does not reconnect, resubscribe, mutate
    runtime state, write files, or call external execution APIs.
    """
    if not isinstance(payload, dict):
        return FeedHealthTruthDecision(
            feed_ok=False,
            reason_code=FEED_HEALTH_TRUTH_BLOCK_REASON,
            reasons=("invalid_payload",),
            context={},
        )

    max_option_age = _safe_non_negative_float(max_option_tick_age_sec, 3.0)
    max_ltp_age = _safe_non_negative_float(max_ltp_age_sec, 2.5) if max_ltp_age_sec is not None else None
    max_depth_age = _safe_non_negative_float(max_depth_age_sec, 6.0) if max_depth_age_sec is not None else None
    global_feed_ok = _bool_or_none(payload.get("feed_ok"))
    websocket_ok = _global_websocket_ok(payload)
    runtime_state = _runtime_state(payload)
    feed_state = _feed_state(payload)
    last_tick_age = _safe_float(payload.get("last_tick_age_sec"))
    last_depth_age = _safe_float(payload.get("last_depth_age_sec"))
    requested_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol))
    symbol_names = _symbols_from_payload(payload, requested_symbols)
    symbol_truths = tuple(
        classify_symbol_feed_truth(payload, symbol, max_option_tick_age_sec=max_option_age)
        for symbol in symbol_names
    )
    monitored_names = _symbols_from_payload(payload, ())
    monitored_truths = tuple(
        classify_symbol_feed_truth(payload, symbol, max_option_tick_age_sec=max_option_age)
        for symbol in monitored_names
    )
    domains = _domain_health(payload)
    required_domain_names = tuple(dict.fromkeys(_normalize_state(item) for item in required_domains if _normalize_state(item)))

    reasons: list[str] = []
    # ``feed_ok`` is an aggregate across monitored symbols in current runtime
    # artifacts. When a consumer supplies explicit dependencies, its false
    # value may be caused by an unrelated illiquid symbol. Hard transport and
    # runtime blockers remain checked below; callers may additionally provide
    # an explicit global_feed_blocked flag for a genuinely system-wide fault.
    scope_symbols = requested_symbols or monitored_names
    aggregate_scope_declared = payload.get("feed_ok_scope") == "symbol_aggregate"
    aggregate_scope_has_evidence = bool(scope_symbols) and all(
        _has_symbol_entry(payload, "option_feed_block_reason_by_symbol", symbol)
        and _has_symbol_entry(payload, "option_last_tick_age_by_symbol", symbol)
        for symbol in scope_symbols
    )
    aggregate_is_symbol_scoped = (
        aggregate_scope_declared
        and payload.get("global_feed_blocked") is False
        and websocket_ok is True
        and aggregate_scope_has_evidence
    )
    if payload.get("global_feed_blocked") is True or (
        global_feed_ok is False and not aggregate_is_symbol_scoped
    ):
        _append_unique(reasons, GLOBAL_FEED_UNHEALTHY_REASON)
    if websocket_ok is False:
        _append_unique(reasons, WEBSOCKET_DISCONNECTED_REASON)
    if feed_state and feed_state not in _SAFE_FEED_STATES:
        _append_unique(reasons, FEED_STATE_UNSAFE_REASON)
    if runtime_state and runtime_state not in _SAFE_RUNTIME_STATES:
        _append_unique(reasons, RUNTIME_STATE_UNSAFE_REASON)
    if last_tick_age is None:
        if "last_tick_age_sec" in payload:
            _append_unique(reasons, "LTP_AGE_MISSING")
    elif max_ltp_age is not None and last_tick_age > max_ltp_age:
        _append_unique(reasons, LTP_TICKS_STALE_REASON)
    if last_depth_age is None:
        if "last_depth_age_sec" in payload:
            _append_unique(reasons, "DEPTH_AGE_MISSING")
    elif max_depth_age is not None and last_depth_age > max_depth_age:
        _append_unique(reasons, DEPTH_TICKS_STALE_REASON)
    if (
        "subscribed_option_tokens_count" in payload
        or "option_subscribe_count" in payload
        or "subscribed_option_tokens" in payload
    ):
        sub_option_count = int(
            payload.get("subscribed_option_tokens_count")
            or payload.get("option_subscribe_count")
            or payload.get("subscribed_option_tokens")
            or 0
        )
        if sub_option_count <= 0:
            _append_unique(reasons, "NO_SUBSCRIBED_OPTIONS")
    for symbol_truth in symbol_truths:
        for reason in symbol_truth.reasons:
            _append_unique(reasons, f"{symbol_truth.symbol}:{reason}")

    for domain in required_domain_names:
        if domain not in FEED_HEALTH_DOMAINS:
            _append_unique(reasons, f"required_domain_unknown:{domain}")
            continue
        state = domains[domain.lower()]["state"]
        if state == "UNKNOWN":
            _append_unique(reasons, f"required_domain_unknown:{domain}")
        elif state != "HEALTHY":
            _append_unique(reasons, f"required_domain_not_healthy:{domain}:{state}")

    feed_ok = (
        not reasons
        and (global_feed_ok is not False or aggregate_is_symbol_scoped)
        and websocket_ok is not False
    )
    domain_states = [item["state"] for item in domains.values()]
    hard_block = any(
        reason in reasons
        for reason in (
            GLOBAL_FEED_UNHEALTHY_REASON,
            WEBSOCKET_DISCONNECTED_REASON,
            FEED_STATE_UNSAFE_REASON,
            RUNTIME_STATE_UNSAFE_REASON,
        )
    ) or "UNHEALTHY" in domain_states
    monitored_unknown = any(
        SYMBOL_FEED_UNKNOWN_REASON in truth.reasons
        or OPTION_AGE_MISSING_REASON in truth.reasons
        for truth in monitored_truths
    )
    monitored_degraded = any(
        not truth.feed_ok
        and any(reason not in {SYMBOL_FEED_UNKNOWN_REASON, OPTION_AGE_MISSING_REASON} for reason in truth.reasons)
        for truth in monitored_truths
    )
    if hard_block:
        overall_state = "BLOCKED"
    elif "DEGRADED" in domain_states or monitored_degraded or any(
        reason.startswith("required_domain_not_healthy:") for reason in reasons
    ):
        overall_state = "OPERATIONAL_DEGRADED"
    elif "UNKNOWN" in domain_states or monitored_unknown or reasons:
        overall_state = "UNKNOWN"
    else:
        overall_state = "HEALTHY"
    return FeedHealthTruthDecision(
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else FEED_HEALTH_TRUTH_BLOCK_REASON,
        reasons=tuple(reasons),
        global_feed_ok=global_feed_ok,
        websocket_ok=websocket_ok,
        symbols=symbol_truths,
        domains=domains,
        overall_state=overall_state,
        context={
            "symbols_requested": list(requested_symbols),
            "required_domains": list(required_domain_names),
            "symbols_evaluated": list(symbol_names),
            "monitored_degraded_symbols": [
                truth.symbol for truth in monitored_truths if not truth.feed_ok
            ],
            "aggregate_feed_ok": global_feed_ok,
            "global_feed_blocked": payload.get("global_feed_blocked") is True,
            "feed_ok_scope": "symbol_aggregate" if aggregate_is_symbol_scoped else "global_or_unknown",
            "max_option_tick_age_sec": max_option_age,
            "max_ltp_age_sec": max_ltp_age,
            "max_depth_age_sec": max_depth_age,
            "runtime_state": runtime_state or None,
            "feed_state": feed_state or None,
            "last_tick_age_sec": last_tick_age,
            "last_depth_age_sec": last_depth_age,
        },
    )
