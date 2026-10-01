from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.candidate_feed_dependencies import REGISTRY_ENTRIES, resolve_candidate_dependencies
from core.feed_health_truth import classify_feed_health_truth

SYMBOL_EXECUTION_SAFETY_BLOCK_REASON = "symbol_execution_safety_failed"
SYMBOL_MISSING_REASON = "symbol_missing"
SYMBOL_FEED_UNSAFE_REASON = "symbol_feed_unsafe"
SYMBOL_SUBSCRIPTION_FAILED_REASON = "symbol_subscription_failed"
SYMBOL_STALE_OPTION_REASON = "symbol_stale_option_ticks"
SYMBOL_OPTION_BLOCKED_REASON = "symbol_option_feed_blocked"
SYMBOL_FEED_DEPENDENCIES_MISSING_REASON = "candidate_feed_dependencies_missing"
SYMBOL_FEED_DEPENDENCIES_INVALID_REASON = "candidate_feed_dependencies_invalid"
SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON = "candidate_feed_dependency_id_missing"
SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON = "candidate_feed_dependency_authority_blocked"


@dataclass(frozen=True)
class SymbolExecutionSafetyDecision:
    execution_allowed: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    symbol: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _candidate_get(candidate, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _safety_metadata() -> dict[str, bool]:
    return {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def resolve_candidate_symbol(candidate: Any) -> str | None:
    flags = _source_flags(candidate)
    symbol = _coalesce(
        _candidate_get(candidate, "symbol"),
        _candidate_get(candidate, "underlying"),
        _candidate_get(candidate, "underlying_symbol"),
        _candidate_get(candidate, "index_symbol"),
        flags.get("symbol"),
        flags.get("underlying"),
        flags.get("underlying_symbol"),
        flags.get("index_symbol"),
    )
    normalized = _normalize_symbol(symbol)
    return normalized or None


def _feed_payload(candidate: Any) -> dict[str, Any]:
    flags = _source_flags(candidate)
    payload = _mapping(_candidate_get(candidate, "feed_health"))
    payload.update(_mapping(flags.get("feed_health")))
    runtime_feed = _mapping(_candidate_get(candidate, "feed_runtime"))
    runtime_feed.update(_mapping(flags.get("feed_runtime")))
    for key, value in runtime_feed.items():
        payload.setdefault(key, value)

    for key in (
        "feed_ok",
        "feed_ok_scope",
        "global_feed_blocked",
        "ws_connected",
        "effective_ws_connected",
        "option_feed_block_reason_by_symbol",
        "option_last_tick_age_by_symbol",
        "symbol_feed_ok_by_symbol",
        "feed_ok_by_symbol",
        "last_tick_age_sec",
        "last_depth_age_sec",
        "subscribed_option_tokens_count",
        "option_subscribe_count",
        "subscribed_option_tokens",
        "required_feed_domains",
        "required_feed_identities",
        "domain_health_by_domain",
        "feed_health_by_identity",
    ):
        candidate_value = _candidate_get(candidate, key)
        flag_value = flags.get(key)
        if candidate_value not in (None, "", "None"):
            payload[key] = candidate_value
        elif flag_value not in (None, "", "None"):
            payload[key] = flag_value
    return payload


def has_symbol_execution_safety_evidence(candidate: Any) -> bool:
    """Return true when EDGE-45 has symbol/feed evidence to evaluate.

    Legacy executable-truth unit fixtures sometimes exercise only quote,
    spread, or strategy contracts and intentionally omit symbol/feed payloads.
    Those should not be retroactively failed by EDGE-45. Real candidates that
    carry symbol identity or feed-health evidence are still gated.
    """
    if str(_candidate_get(candidate, "feed_health_scope", "") or "").strip().upper() == "HISTORICAL_REPLAY":
        return False
    if str(_source_flags(candidate).get("feed_health_scope", "") or "").strip().upper() == "HISTORICAL_REPLAY":
        return False
    if resolve_candidate_symbol(candidate):
        return True
    return bool(_feed_payload(candidate))


def _map_feed_reason(reason: str) -> str:
    lower = str(reason or "").strip().lower()
    if lower.endswith(":option_ticks_stale"):
        return SYMBOL_STALE_OPTION_REASON
    if lower.endswith(":option_feed_blocked"):
        return SYMBOL_OPTION_BLOCKED_REASON
    if "subscription" in lower and "failed" in lower:
        return SYMBOL_SUBSCRIPTION_FAILED_REASON
    if lower.startswith("global_feed_unhealthy") or lower.startswith("websocket_disconnected"):
        return SYMBOL_FEED_UNSAFE_REASON
    if lower.endswith(":option_age_missing"):
        return SYMBOL_FEED_UNSAFE_REASON
    if lower.endswith(":symbol_feed_unknown"):
        return SYMBOL_FEED_UNSAFE_REASON
    return SYMBOL_FEED_UNSAFE_REASON


def classify_symbol_execution_safety(
    candidate: Any,
    *,
    max_option_tick_age_sec: float = 3.0,
) -> SymbolExecutionSafetyDecision:
    """Gate execution using symbol-specific feed health evidence.

    This function is read-only. It does not reconnect feeds, mutate runtime
    subscriptions, call broker APIs, or place/modify/cancel orders.
    """
    symbol = resolve_candidate_symbol(candidate)
    if not symbol:
        return SymbolExecutionSafetyDecision(
            execution_allowed=False,
            reason_code=SYMBOL_EXECUTION_SAFETY_BLOCK_REASON,
            reasons=(SYMBOL_MISSING_REASON,),
            symbol=None,
            context={"feed_health_truth": None, **_safety_metadata()},
        )

    payload = _feed_payload(candidate)
    flags = _source_flags(candidate)
    # Prefer a governed family or exact candidate ID. When candidate_id is a
    # per-signal lineage key, resolve only through an explicit strategy_id;
    # never discard an opaque ID into symbol-only compatibility.
    declared_family = _coalesce(
        _candidate_get(candidate, "candidate_family"),
        flags.get("candidate_family"),
    )
    candidate_id = _coalesce(
        _candidate_get(candidate, "candidate_id"),
        flags.get("candidate_id"),
    )
    strategy_id = _coalesce(
        _candidate_get(candidate, "strategy_id"),
        flags.get("strategy_id"),
    )
    registered_ids = {entry.candidate_id for entry in REGISTRY_ENTRIES}
    if declared_family is not None:
        dependency_family = declared_family
    elif candidate_id in registered_ids:
        dependency_family = candidate_id
    elif strategy_id is not None:
        # Opaque candidate IDs are lineage identifiers in several producers;
        # resolve them only through an explicit registered strategy ID.
        dependency_family = strategy_id
    else:
        # Do not silently discard an unrecognized ID into symbol-only legacy
        # compatibility. It has candidate identity but no dependency authority.
        dependency_family = candidate_id
    has_domain_evidence = any(
        key in payload
        for key in (
            "domain_health_by_domain",
            "feed_health_by_identity",
            "required_feed_domains",
            "required_feed_identities",
        )
    )
    dependency_resolution = None
    if dependency_family is not None or has_domain_evidence:
        dependency_resolution = resolve_candidate_dependencies(
            None if dependency_family is None else str(dependency_family),
            caller_required_domains=payload.get("required_feed_domains"),
            identity_health_by_identity=payload.get("feed_health_by_identity"),
        )
    # This consumer has already selected a candidate symbol; the legacy
    # feed_ok field is an aggregate over all monitored subscriptions. It may
    # be ignored only when the caller carries explicit per-symbol evidence.
    feed_truth = classify_feed_health_truth(
        payload,
        symbols=(symbol,),
        max_option_tick_age_sec=max_option_tick_age_sec,
        required_domains=_required_feed_domains(payload.get("required_feed_domains")),
    )
    reasons: list[str] = []
    if not feed_truth.feed_ok:
        for reason in feed_truth.reasons:
            _append_unique(reasons, _map_feed_reason(reason))
    if "domain_health_by_domain" in payload:
        raw_domains = payload.get("required_feed_domains")
        if raw_domains is None or (isinstance(raw_domains, (list, tuple)) and not raw_domains):
            _append_unique(reasons, SYMBOL_FEED_DEPENDENCIES_MISSING_REASON)
        elif not _valid_required_feed_domains(raw_domains):
            _append_unique(reasons, SYMBOL_FEED_DEPENDENCIES_INVALID_REASON)
    if dependency_resolution is not None and not dependency_resolution.execution_eligible:
        reason = dependency_resolution.reason
        if reason == "CANDIDATE_FEED_DEPENDENCY_ID_MISSING":
            _append_unique(reasons, SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON)
        else:
            _append_unique(reasons, SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON)
    for symbol_truth in feed_truth.symbols:
        if symbol_truth.symbol != symbol:
            continue
        if not symbol_truth.feed_ok:
            for reason in symbol_truth.reasons:
                _append_unique(reasons, _map_feed_reason(f"{symbol}:{reason}"))
            if symbol_truth.option_feed_block_reason and "subscription" in symbol_truth.option_feed_block_reason:
                _append_unique(reasons, SYMBOL_SUBSCRIPTION_FAILED_REASON)

    allowed = not reasons
    return SymbolExecutionSafetyDecision(
        execution_allowed=allowed,
        reason_code="ok" if allowed else SYMBOL_EXECUTION_SAFETY_BLOCK_REASON,
        reasons=tuple(reasons),
        symbol=symbol,
        context={
            "feed_health_truth": feed_truth.to_payload(),
            "candidate_feed_dependency": (
                dependency_resolution.to_payload()
                if dependency_resolution is not None
                else {
                    "status": "LEGACY_UNRESOLVED",
                    "reason": "SYMBOL_ONLY_COMPATIBILITY_WITHOUT_STRUCTURED_DOMAIN_EVIDENCE",
                    "registry_coverage": False,
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                    "append": False,
                }
            ),
            **_safety_metadata(),
        },
    )


def _required_feed_domains(value: Any) -> tuple[str, ...]:
    """Normalize explicit candidate dependencies; malformed declarations block."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ("__INVALID_REQUIRED_FEED_DOMAINS__",)


def _valid_required_feed_domains(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return all(isinstance(item, str) and item.strip() for item in value)
