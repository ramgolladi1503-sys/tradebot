from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


FEED_TRUTH_CONTRACT_SCHEMA_VERSION = 1

LIVE = "LIVE"
DEGRADED = "DEGRADED"
STALE = "STALE"
DISCONNECTED = "DISCONNECTED"
RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
AUTH_BLOCKED = "AUTH_BLOCKED"
IMPORT_MISSING = "IMPORT_MISSING"
UNKNOWN = "UNKNOWN"

_KNOWN_STATES = {
    LIVE,
    DEGRADED,
    STALE,
    DISCONNECTED,
    RECOVERY_BLOCKED,
    AUTH_BLOCKED,
    IMPORT_MISSING,
    UNKNOWN,
}

_STATE_PRIORITY = (
    AUTH_BLOCKED,
    IMPORT_MISSING,
    RECOVERY_BLOCKED,
    DISCONNECTED,
    STALE,
    DEGRADED,
    LIVE,
    UNKNOWN,
)

_OK_MARKERS = {"", "OK", "LIVE", "FRESH", "HEALTHY", "NONE"}
_ADVISORY_LATENCY_ACTIONS = {"DEGRADE_EXIT_ONLY", "COOLDOWN"}


@dataclass(frozen=True)
class FeedTruthContract:
    state: str
    entries_allowed: bool
    exits_allowed: bool
    quotes_trusted: bool
    depth_trusted: bool
    reconnect_allowed: bool
    process_restart_required: bool
    blockers: tuple[str, ...] = ()
    advisory_reasons: tuple[str, ...] = ()
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    reason_code: str = "unknown"

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = FEED_TRUTH_CONTRACT_SCHEMA_VERSION
        return payload


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "healthy", "live", "fresh"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded"}:
        return False
    return None


def _append_unique(items: list[str], reason: Any) -> None:
    normalized = _upper(reason)
    if not normalized or normalized in _OK_MARKERS or normalized.endswith("_OK"):
        return
    if normalized not in items:
        items.append(normalized)


def _normalize_state(value: Any) -> str:
    state = _upper(value)
    return state if state in _KNOWN_STATES else UNKNOWN


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None", {}):
            return value
    return None


def _snapshot_dict(value: Any) -> dict[str, Any]:
    return _as_mapping(value)


def _is_auth_blocked(snapshot: dict[str, Any]) -> bool:
    runtime_state = _upper(snapshot.get("runtime_state"))
    feed_truth_state = _upper(snapshot.get("feed_truth_state"))
    reconnect_reason = _upper(snapshot.get("reconnect_blocked_reason"))
    return (
        runtime_state.startswith("AUTH")
        or runtime_state in {"TOKEN_INVALID", "LOGIN_REQUIRED"}
        or feed_truth_state == AUTH_BLOCKED
        or reconnect_reason.startswith("AUTH")
    )


def _is_import_missing(snapshot: dict[str, Any]) -> bool:
    runtime_state = _upper(snapshot.get("runtime_state"))
    feed_truth_state = _upper(snapshot.get("feed_truth_state"))
    feed_truth_reason_code = _upper(snapshot.get("feed_truth_reason_code"))
    return (
        runtime_state == IMPORT_MISSING
        or feed_truth_state == IMPORT_MISSING
        or feed_truth_reason_code == IMPORT_MISSING
        or bool(snapshot.get("import_missing"))
    )


def _is_recovery_blocked(snapshot: dict[str, Any]) -> bool:
    runtime_state = _upper(snapshot.get("runtime_state"))
    feed_truth_state = _upper(snapshot.get("feed_truth_state"))
    feed_truth_reason_code = _upper(snapshot.get("feed_truth_reason_code"))
    reconnect_reason = _upper(snapshot.get("reconnect_blocked_reason"))
    recovery_action = _upper(snapshot.get("recovery_action"))
    blocked_reasons = {
        "PROCESS_RESTART_REQUIRED",
        "WS1006_PROCESS_RESTART_REQUIRED",
        "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
    }
    return (
        runtime_state == RECOVERY_BLOCKED
        or feed_truth_state in {"RECONNECT_BLOCKED", RECOVERY_BLOCKED}
        or feed_truth_reason_code in blocked_reasons
        or reconnect_reason in blocked_reasons
        or recovery_action == "PROCESS_RESTART_REQUIRED"
    )


def _is_disconnected(snapshot: dict[str, Any]) -> bool:
    ws_connected = _bool_or_none(_first_non_empty(snapshot.get("ws_connected"), snapshot.get("effective_ws_connected")))
    return ws_connected is False


def _latency_advisory(snapshot: dict[str, Any]) -> str | None:
    latency = _as_mapping(snapshot.get("latency_guard"))
    action = _upper(latency.get("latency_guard_action"))
    reason = _upper(latency.get("latency_guard_reason"))
    if reason in _OK_MARKERS or reason.endswith("_OK"):
        return None
    if action in _ADVISORY_LATENCY_ACTIONS:
        return f"LATENCY_GUARD_{action}"
    if action and action not in {"OK", "NONE"}:
        return f"LATENCY_GUARD_{action}"
    if reason and reason not in _OK_MARKERS and not reason.endswith("_OK"):
        return reason
    if bool(latency.get("latency_guard_triggered")):
        return "LATENCY_GUARD_TRIGGERED"
    return None


def build_feed_truth_contract(snapshot: Mapping[str, Any] | None = None) -> FeedTruthContract:
    source = _snapshot_dict(snapshot)
    quote_health = _snapshot_dict(source.get("quote_health"))
    latency = _snapshot_dict(source.get("latency_guard"))

    runtime_state = _normalize_state(source.get("runtime_state"))
    feed_truth_state = _normalize_state(source.get("feed_truth_state"))
    feed_truth_reason_code = _upper(source.get("feed_truth_reason_code"))
    ws_connected = _bool_or_none(_first_non_empty(source.get("ws_connected"), source.get("effective_ws_connected")))
    feed_ok = _bool_or_none(source.get("feed_ok"))
    feed_truth_strict_live = _bool_or_none(source.get("feed_truth_strict_live"))
    quote_health_state = _upper(quote_health.get("state"))
    quote_health_stale_reasons = [_upper(reason) for reason in _as_list(quote_health.get("stale_reasons")) if _upper(reason)]
    option_feed_block_reason = _upper(source.get("option_feed_block_reason"))
    option_feed_block_reason_by_symbol = _snapshot_dict(source.get("option_feed_block_reason_by_symbol"))
    reconnect_blocked_reason = _upper(source.get("reconnect_blocked_reason"))
    recovery_action = _upper(source.get("recovery_action"))

    blockers: list[str] = []
    advisory_reasons: list[str] = []

    def _present(value: Any) -> bool:
        return value not in (None, "", "None", {}, [], ())

    meaningful_signals = any(
        _present(value)
        for value in (
            source.get("runtime_state"),
            source.get("ws_connected"),
            source.get("effective_ws_connected"),
            source.get("feed_truth_state"),
            source.get("feed_truth_reason_code"),
            source.get("feed_ok"),
            source.get("feed_truth_strict_live"),
            quote_health.get("state"),
            option_feed_block_reason,
            reconnect_blocked_reason,
            recovery_action,
            latency.get("latency_guard_action"),
            latency.get("latency_guard_reason"),
            latency.get("latency_guard_triggered"),
        )
    )

    if not meaningful_signals:
        return FeedTruthContract(
            state=UNKNOWN,
            entries_allowed=False,
            exits_allowed=False,
            quotes_trusted=False,
            depth_trusted=False,
            reconnect_allowed=False,
            process_restart_required=False,
            blockers=("UNKNOWN_INPUT",),
            advisory_reasons=(),
            source_snapshot={"input": source, "quote_health": quote_health, "latency_guard": latency},
            reason_code="unknown_input",
        )

    process_restart_required = _is_recovery_blocked(source)
    if _is_auth_blocked(source):
        blockers.append(AUTH_BLOCKED)
    if _is_import_missing(source):
        blockers.append(IMPORT_MISSING)
    if process_restart_required:
        blockers.append(RECOVERY_BLOCKED)
    if _is_disconnected(source):
        blockers.append(DISCONNECTED)

    if feed_truth_state in {RECOVERY_BLOCKED, "RECONNECT_BLOCKED"}:
        blockers.append(RECOVERY_BLOCKED)
    if runtime_state == RECOVERY_BLOCKED:
        blockers.append(RECOVERY_BLOCKED)

    stale_blocked = False
    if feed_truth_reason_code in {"STALE_OPTION_LTP", "LTP_STALE", "DEPTH_STALE", "WS1006_PROCESS_RESTART_REQUIRED", "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED"}:
        stale_blocked = True
        blockers.append(STALE)
    if option_feed_block_reason in {"STALE_OPTION_LTP", "LTP_STALE", "DEPTH_STALE"}:
        stale_blocked = True
        blockers.append(STALE)
    if any(reason in {"STALE_OPTION_LTP", "LTP_STALE", "DEPTH_STALE"} for reason in quote_health_stale_reasons):
        stale_blocked = True
        blockers.append(STALE)

    quote_health_blocked = quote_health_state not in _OK_MARKERS
    latency_advisory = _latency_advisory(source)
    if latency_advisory:
        advisory_reasons.append(latency_advisory)

    if _bool_or_none(feed_ok) is False:
        blockers.append(DEGRADED)
    if feed_truth_strict_live is False:
        blockers.append(DEGRADED)
    if quote_health_blocked and quote_health_state not in {"STALE", "BLOCKED"}:
        blockers.append(DEGRADED)
    if option_feed_block_reason_by_symbol and not option_feed_block_reason and not stale_blocked:
        blockers.append(DEGRADED)

    blockers = [item for item in blockers if item]
    deduped_blockers: list[str] = []
    for reason in blockers:
        _append_unique(deduped_blockers, reason)

    state = UNKNOWN
    if AUTH_BLOCKED in deduped_blockers:
        state = AUTH_BLOCKED
    elif IMPORT_MISSING in deduped_blockers:
        state = IMPORT_MISSING
    elif RECOVERY_BLOCKED in deduped_blockers:
        state = RECOVERY_BLOCKED
    elif DISCONNECTED in deduped_blockers:
        state = DISCONNECTED
    elif STALE in deduped_blockers:
        state = STALE
    elif DEGRADED in deduped_blockers or advisory_reasons:
        state = DEGRADED
    elif (
        ws_connected is True
        and feed_ok is not False
        and feed_truth_strict_live is not False
        and not deduped_blockers
        and quote_health_state in _OK_MARKERS
    ):
        state = LIVE
    elif not meaningful_signals:
        state = UNKNOWN
    else:
        state = DEGRADED if ws_connected is True else UNKNOWN

    quotes_trusted = state == LIVE and ws_connected is True and not deduped_blockers
    depth_trusted = state == LIVE and ws_connected is True and not deduped_blockers
    entries_allowed = state == LIVE and quotes_trusted and depth_trusted and not process_restart_required
    exits_allowed = state in {LIVE, DEGRADED, STALE, DISCONNECTED}
    reconnect_allowed = state not in {AUTH_BLOCKED, IMPORT_MISSING, RECOVERY_BLOCKED, UNKNOWN}

    if state in {RECOVERY_BLOCKED, DISCONNECTED, STALE}:
        quotes_trusted = False
        depth_trusted = False
        entries_allowed = False

    if state in {AUTH_BLOCKED, IMPORT_MISSING, UNKNOWN}:
        quotes_trusted = False
        depth_trusted = False
        entries_allowed = False
        exits_allowed = False
        reconnect_allowed = False

    source_snapshot = {
        "runtime_state": runtime_state or None,
        "ws_connected": ws_connected,
        "feed_truth_state": feed_truth_state or None,
        "feed_truth_reason_code": feed_truth_reason_code or None,
        "feed_ok": feed_ok,
        "feed_truth_strict_live": feed_truth_strict_live,
        "quote_health_state": quote_health_state or None,
        "quote_health_stale_reasons": quote_health_stale_reasons,
        "option_feed_block_reason": option_feed_block_reason or None,
        "option_feed_block_reason_by_symbol": option_feed_block_reason_by_symbol,
        "reconnect_blocked_reason": reconnect_blocked_reason or None,
        "recovery_action": recovery_action or None,
        "latency_guard_action": _upper(latency.get("latency_guard_action")) or None,
        "latency_guard_reason": _upper(latency.get("latency_guard_reason")) or None,
        "latency_guard_source": latency.get("latency_guard_source"),
        "latency_guard_triggered": latency.get("latency_guard_triggered"),
        "latency_guard_metric": latency.get("latency_guard_metric"),
        "latency_guard_value": latency.get("latency_guard_value"),
        "latency_guard_threshold": latency.get("latency_guard_threshold"),
        "latency_guard_age_sec": latency.get("latency_guard_age_sec"),
        "latency_guard_recovery_required": latency.get("latency_guard_recovery_required"),
    }

    return FeedTruthContract(
        state=state,
        entries_allowed=entries_allowed,
        exits_allowed=exits_allowed,
        quotes_trusted=quotes_trusted,
        depth_trusted=depth_trusted,
        reconnect_allowed=reconnect_allowed,
        process_restart_required=process_restart_required,
        blockers=tuple(deduped_blockers),
        advisory_reasons=tuple(dict.fromkeys(advisory_reasons)),
        source_snapshot=source_snapshot,
        reason_code=(
            "auth_blocked"
            if state == AUTH_BLOCKED
            else "import_missing"
            if state == IMPORT_MISSING
            else "recovery_blocked"
            if state == RECOVERY_BLOCKED
            else "disconnected"
            if state == DISCONNECTED
            else "stale"
            if state == STALE
            else "degraded"
            if state == DEGRADED
            else "live"
            if state == LIVE
            else "unknown"
        ),
    )


FeedTruth = FeedTruthContract


__all__ = [
    "AUTH_BLOCKED",
    "DEGRADED",
    "DISCONNECTED",
    "FEED_TRUTH_CONTRACT_SCHEMA_VERSION",
    "FeedTruth",
    "FeedTruthContract",
    "IMPORT_MISSING",
    "LIVE",
    "RECOVERY_BLOCKED",
    "STALE",
    "UNKNOWN",
    "build_feed_truth_contract",
]
