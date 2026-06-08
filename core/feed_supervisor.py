from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_BOOTING_STATES = {"BOOTING", "STARTING", "INIT", "INITIALIZING"}
_CONNECTING_STATES = {"CONNECTING", "SUBSCRIBE_PENDING", "SUBSCRIPTION_REQUESTED", "SUBSCRIPTION_SENT"}
_CONNECTED_STATES = {"CONNECTED", "RUNNING"}
_SUBSCRIBING_STATES = {"SUBSCRIBING", "SUBSCRIBE_REQUESTED", "SUBSCRIPTION_PENDING"}
_SUBSCRIBED_STATES = {"SUBSCRIBED", "FEED_SUBSCRIBED", "FEED_ON_CONNECT_SUBSCRIBE", "FEED_RESUBSCRIBE"}
_VERIFYING_STATES = {"VERIFYING", "VERIFYING_OPTION_TICKS", "OPTION_VERIFYING", "OPTION_TICK_VERIFYING", "FEED_OPTION_VERIFY_BEGIN"}
_WARMING_UP_STATES = {"WARMING_UP", "WARMUP", "WARMUP_PENDING"}
_DEGRADED_STATES = {"DEGRADED", "UNHEALTHY", "STALE", "PARTIAL"}
_RECOVERING_STATES = {"RECOVERING", "RECOVERING_WS_DROP", "RECONNECTING", "RESUBSCRIBING"}
_RECOVERY_TIMEOUT_STATES = {"RECOVERY_TIMEOUT", "RESTART_VERIFY_FAILED"}
_RECOVERY_BLOCKED_STATES = {"RECOVERY_BLOCKED", "RECONNECT_BLOCKED"}
_RESTART_REQUIRED_STATES = {"RESTART_REQUIRED", "WS1006_PROCESS_RESTART_REQUIRED", "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED"}
_AUTH_REQUIRED_STATES = {"AUTH_REQUIRED", "AUTH_BLOCKED", "LOGIN_REQUIRED", "TOKEN_INVALID"}
_SHUTDOWN_STATES = {"SHUTDOWN", "STOPPED", "STOPPING", "TERMINATED"}


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "healthy", "live", "fresh", "connected"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded", "disconnected"}:
        return False
    return None


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _truthy(*values: Any) -> bool:
    for value in values:
        flag = _as_bool(value)
        if flag is True:
            return True
    return False


@dataclass(frozen=True)
class FeedSupervisorSnapshot:
    state: str
    reason_code: str
    blockers: tuple[str, ...]
    read_only: bool = True
    append: bool = False
    allowed_for_live_execution: bool = False
    runtime_state: str = "UNKNOWN"
    ws_connected: bool = False
    market_open: bool = False
    auth_ready: bool = False
    subscribed_option_tokens_count: int = 0
    subscribed_tokens_count: int = 0
    option_ticks_verified: bool = False
    underlying_tick_fresh: bool = False
    depth_fresh: bool = False
    recovery_in_progress: bool = False
    recovery_blocked: bool = False
    recovery_timeout: bool = False
    process_restart_required: bool = False
    auth_required: bool = False
    verified_option_symbols: tuple[str, ...] = ()
    missing_option_symbols: tuple[str, ...] = ()

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["verified_option_symbols"] = list(self.verified_option_symbols)
        payload["missing_option_symbols"] = list(self.missing_option_symbols)
        _mark_non_action(payload)
        payload["allowed_for_live_execution"] = False
        return payload


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


def build_feed_supervisor_snapshot(payload: Mapping[str, Any] | None) -> FeedSupervisorSnapshot:
    source = _as_mapping(payload)
    runtime_state = _upper(source.get("runtime_state") or source.get("ws_recovery_state") or source.get("state"))
    state_machine = _as_mapping(source.get("state_machine"))
    state_machine_state = _upper(state_machine.get("state"))
    if not runtime_state:
        runtime_state = state_machine_state or "UNKNOWN"
    market_open = _truthy(source.get("market_open"))
    ws_connected = _as_bool(source.get("effective_ws_connected"))
    if ws_connected is None:
        ws_connected = _as_bool(source.get("ws_connected"))
    if ws_connected is None:
        ws_connected = False
    auth_ready = _truthy(source.get("auth_ready"), source.get("auth_ok"), source.get("auth_state") in {"OK", "READY", "AUTH_READY"})
    auth_required = _truthy(source.get("auth_required"), source.get("auth_blocked"), runtime_state in _AUTH_REQUIRED_STATES)
    recovery_in_progress = _truthy(source.get("recovery_in_progress"), source.get("recovery_state") in _RECOVERING_STATES, runtime_state in _RECOVERING_STATES)
    recovery_timeout = _truthy(source.get("recovery_timeout"), runtime_state in _RECOVERY_TIMEOUT_STATES)
    recovery_blocked = _truthy(source.get("recovery_blocked"), source.get("feed_recovery_blocked"), runtime_state in _RECOVERY_BLOCKED_STATES, recovery_timeout)
    process_restart_required = _truthy(source.get("process_restart_required"), runtime_state in _RESTART_REQUIRED_STATES)
    subscribed_option_tokens_count = _as_int(source.get("subscribed_option_tokens_count") or source.get("option_subscribe_count"))
    subscribed_tokens_count = _as_int(source.get("subscribed_tokens_count"))
    option_ticks_verified = _truthy(source.get("option_ticks_verified"), source.get("option_verification_ok"))
    if not option_ticks_verified:
        verified_option_symbols = tuple(
            sorted(
                {
                    str(symbol).strip().upper()
                    for symbol in list(source.get("verified_option_symbols") or [])
                    if str(symbol).strip()
                }
            )
        )
        missing_option_symbols = tuple(
            sorted(
                {
                    str(symbol).strip().upper()
                    for symbol in list(source.get("missing_option_symbols") or [])
                    if str(symbol).strip()
                }
            )
        )
        option_ticks_verified = bool(verified_option_symbols) and not missing_option_symbols
    else:
        verified_option_symbols = tuple(
            sorted(
                {
                    str(symbol).strip().upper()
                    for symbol in list(source.get("verified_option_symbols") or [])
                    if str(symbol).strip()
                }
            )
        )
        missing_option_symbols = tuple(
            sorted(
                {
                    str(symbol).strip().upper()
                    for symbol in list(source.get("missing_option_symbols") or [])
                    if str(symbol).strip()
                }
            )
        )
    underlying_tick_fresh = _truthy(source.get("underlying_tick_fresh"), _as_float(source.get("latest_ltp_age_sec")) is not None and _as_float(source.get("latest_ltp_age_sec")) <= float(source.get("max_ltp_age_sec") or 2.5))
    depth_fresh = _truthy(source.get("depth_fresh"), _as_float(source.get("latest_depth_age_sec")) is not None and _as_float(source.get("latest_depth_age_sec")) <= float(source.get("max_depth_age_sec") or 6.0))

    blockers: list[str] = []
    if auth_required:
        blockers.append("AUTH_REQUIRED")
    if process_restart_required:
        blockers.append("RESTART_REQUIRED")
    if recovery_timeout:
        blockers.append("RECOVERY_TIMEOUT")
    if recovery_blocked:
        blockers.append("RECOVERY_BLOCKED")
    if recovery_in_progress:
        blockers.append("RECOVERING")
    if not ws_connected and runtime_state not in _BOOTING_STATES:
        blockers.append("WS_DISCONNECTED")
    if (
        subscribed_option_tokens_count <= 0
        and runtime_state not in _BOOTING_STATES | _SHUTDOWN_STATES | _SUBSCRIBED_STATES | _VERIFYING_STATES | _WARMING_UP_STATES
    ):
        blockers.append("NO_OPTION_SUBSCRIPTIONS")
    if not option_ticks_verified and runtime_state not in _BOOTING_STATES | _SHUTDOWN_STATES:
        blockers.append("OPTION_TICKS_UNVERIFIED")
    if not underlying_tick_fresh and runtime_state not in _BOOTING_STATES | _SHUTDOWN_STATES:
        blockers.append("UNDERLYING_TICK_STALE")
    if not depth_fresh and runtime_state not in _BOOTING_STATES | _SHUTDOWN_STATES:
        blockers.append("DEPTH_STALE")

    if runtime_state in _SHUTDOWN_STATES:
        state = "SHUTDOWN"
        reason_code = runtime_state or "SHUTDOWN"
    elif auth_required:
        state = "AUTH_REQUIRED"
        reason_code = runtime_state or "AUTH_REQUIRED"
    elif process_restart_required:
        state = "RESTART_REQUIRED"
        reason_code = runtime_state or "RESTART_REQUIRED"
    elif recovery_timeout:
        state = "RECOVERY_TIMEOUT"
        reason_code = runtime_state or "RECOVERY_TIMEOUT"
    elif recovery_blocked:
        state = "RECOVERY_BLOCKED"
        reason_code = runtime_state or "RECOVERY_BLOCKED"
    elif recovery_in_progress:
        state = "RECOVERING"
        reason_code = runtime_state or "RECOVERING"
    elif runtime_state in _BOOTING_STATES or (not ws_connected and not auth_ready and subscribed_tokens_count <= 0):
        state = "BOOTING"
        reason_code = runtime_state or "BOOTING"
    elif runtime_state in _CONNECTING_STATES:
        state = "CONNECTING"
        reason_code = runtime_state or "CONNECTING"
    elif runtime_state in _SUBSCRIBING_STATES:
        state = "SUBSCRIBING"
        reason_code = runtime_state or "SUBSCRIBING"
    elif ws_connected and subscribed_tokens_count <= 0:
        state = "CONNECTED"
        reason_code = runtime_state or "CONNECTED"
    elif runtime_state in _SUBSCRIBED_STATES or subscribed_tokens_count > 0:
        if runtime_state in _VERIFYING_STATES or not option_ticks_verified:
            state = "VERIFYING"
            reason_code = runtime_state or "VERIFYING"
        elif not underlying_tick_fresh or not depth_fresh:
            state = "WARMING_UP"
            reason_code = runtime_state or "WARMING_UP"
        else:
            state = "CANDIDATE_READY"
            reason_code = runtime_state or "CANDIDATE_READY"
            blockers = []
    elif runtime_state in _VERIFYING_STATES:
        state = "VERIFYING"
        reason_code = runtime_state or "VERIFYING"
    elif runtime_state in _WARMING_UP_STATES:
        state = "WARMING_UP"
        reason_code = runtime_state or "WARMING_UP"
    elif runtime_state in _DEGRADED_STATES or not ws_connected:
        state = "DEGRADED"
        reason_code = runtime_state or "DEGRADED"
    else:
        state = "BOOTING"
        reason_code = runtime_state or "BOOTING"

    if state == "CANDIDATE_READY" and blockers:
        blockers = []

    return FeedSupervisorSnapshot(
        state=state,
        reason_code=reason_code,
        blockers=tuple(dict.fromkeys(str(blocker).strip().upper() for blocker in blockers if str(blocker).strip())),
        runtime_state=runtime_state or "UNKNOWN",
        ws_connected=bool(ws_connected),
        market_open=bool(market_open),
        auth_ready=bool(auth_ready),
        subscribed_option_tokens_count=subscribed_option_tokens_count,
        subscribed_tokens_count=subscribed_tokens_count,
        option_ticks_verified=bool(option_ticks_verified),
        underlying_tick_fresh=bool(underlying_tick_fresh),
        depth_fresh=bool(depth_fresh),
        recovery_in_progress=bool(recovery_in_progress),
        recovery_blocked=bool(recovery_blocked),
        recovery_timeout=bool(recovery_timeout),
        process_restart_required=bool(process_restart_required),
        auth_required=bool(auth_required),
        verified_option_symbols=verified_option_symbols,
        missing_option_symbols=missing_option_symbols,
    )


__all__ = [
    "FeedSupervisorSnapshot",
    "build_feed_supervisor_snapshot",
]
