from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

GLOBAL_FEED_UNHEALTHY_REASON = "global_feed_unhealthy"
WEBSOCKET_DISCONNECTED_REASON = "websocket_disconnected"
OPTION_FEED_BLOCKED_REASON = "option_feed_blocked"
OPTION_TICKS_STALE_REASON = "option_ticks_stale"
OPTION_AGE_MISSING_REASON = "option_age_missing"
SYMBOL_FEED_UNKNOWN_REASON = "symbol_feed_unknown"
FEED_HEALTH_TRUTH_BLOCK_REASON = "feed_health_truth_failed"

_OPTION_OK_CODES = {"", "OK", "NONE", "HEALTHY", "FRESH"}


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


def _global_websocket_ok(payload: dict[str, Any]) -> bool | None:
    effective = _bool_or_none(payload.get("effective_ws_connected"))
    if effective is not None:
        return effective
    return _bool_or_none(payload.get("ws_connected"))


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

    if block_reason not in _OPTION_OK_CODES:
        _append_unique(reasons, OPTION_FEED_BLOCKED_REASON)
    if option_age is None:
        if block_reason not in _OPTION_OK_CODES or symbol_feed_ok is False:
            _append_unique(reasons, OPTION_AGE_MISSING_REASON)
    elif option_age > max_option_tick_age_sec:
        _append_unique(reasons, OPTION_TICKS_STALE_REASON)
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
) -> FeedHealthTruthDecision:
    """Reconcile global feed health and per-symbol option feed health.

    This is read-only evidence. It does not reconnect, resubscribe, mutate
    runtime state, or call any broker APIs.
    """
    if not isinstance(payload, dict):
        return FeedHealthTruthDecision(
            feed_ok=False,
            reason_code=FEED_HEALTH_TRUTH_BLOCK_REASON,
            reasons=("invalid_payload",),
            context={},
        )

    global_feed_ok = _bool_or_none(payload.get("feed_ok"))
    websocket_ok = _global_websocket_ok(payload)
    requested_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol))
    symbol_names = _symbols_from_payload(payload, requested_symbols)
    symbol_truths = tuple(
        classify_symbol_feed_truth(payload, symbol, max_option_tick_age_sec=max(0.0, float(max_option_tick_age_sec)))
        for symbol in symbol_names
    )

    reasons: list[str] = []
    if global_feed_ok is False:
        _append_unique(reasons, GLOBAL_FEED_UNHEALTHY_REASON)
    if websocket_ok is False:
        _append_unique(reasons, WEBSOCKET_DISCONNECTED_REASON)
    for symbol_truth in symbol_truths:
        for reason in symbol_truth.reasons:
            _append_unique(reasons, f"{symbol_truth.symbol}:{reason}")

    feed_ok = not reasons and global_feed_ok is not False and websocket_ok is not False
    return FeedHealthTruthDecision(
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else FEED_HEALTH_TRUTH_BLOCK_REASON,
        reasons=tuple(reasons),
        global_feed_ok=global_feed_ok,
        websocket_ok=websocket_ok,
        symbols=symbol_truths,
        context={
            "symbols_requested": list(requested_symbols),
            "symbols_evaluated": list(symbol_names),
            "max_option_tick_age_sec": max(0.0, float(max_option_tick_age_sec)),
        },
    )