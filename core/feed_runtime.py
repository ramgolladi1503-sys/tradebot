from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping


_BOOTING_STATES = {"BOOTING", "STARTING", "INIT", "INITIALIZING"}
_CONNECTING_STATES = {"CONNECTING", "SUBSCRIBE_PENDING", "SUBSCRIPTION_REQUESTED", "SUBSCRIPTION_SENT"}
_SUBSCRIBED_STATES = {"SUBSCRIBED", "FEED_SUBSCRIBED", "FEED_ON_CONNECT_SUBSCRIBE", "FEED_RESUBSCRIBE"}
_VERIFYING_STATES = {"VERIFYING_OPTION_TICKS", "OPTION_VERIFYING", "OPTION_TICK_VERIFYING", "FEED_OPTION_VERIFY_BEGIN"}
_HEALTHY_STATES = {"VERIFIED_HEALTHY", "LIVE", "HEALTHY"}
_DEGRADED_STATES = {"DEGRADED", "UNHEALTHY", "STALE", "PARTIAL"}
_RECOVERY_BLOCKED_STATES = {"RECOVERY_BLOCKED", "RECONNECT_BLOCKED", "FEED_LIFECYCLE_FATAL"}
_RESTART_REQUIRED_STATES = {
    "RESTART_REQUIRED",
    "WS1006_PROCESS_RESTART_REQUIRED",
    "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
    "RESTART_VERIFY_FAILED",
    "FEED_LIFECYCLE_FATAL",
}
_RECOVERING_STATES = {"RECOVERING_WS_DROP", "RECONNECTING", "RESUBSCRIBING"}


@dataclass(frozen=True)
class CanonicalFeedTruthState:
    state: str
    reason_code: str
    recovery_state: str
    ws_error_code: int | None
    ws_error_reason: str | None
    ws_fault_class: str
    blockers: tuple[str, ...]
    ws_connected: bool
    underlying_tick_fresh: bool
    option_ticks_verified: bool
    depth_fresh: bool
    latest_ltp_age_sec: float | None
    latest_depth_age_sec: float | None
    latest_option_tick_age_sec: float | None
    subscribed_option_tokens_count: int
    verified_option_symbols: tuple[str, ...]
    missing_option_symbols: tuple[str, ...]
    recovery_blocked: bool
    process_restart_required: bool
    restart_failure_reason: str | None
    session_id: str
    updated_at_epoch: float
    updated_at_ist: str

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["verified_option_symbols"] = list(self.verified_option_symbols)
        payload["missing_option_symbols"] = list(self.missing_option_symbols)
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["read_only"] = True
        payload["append"] = True
        return payload

    def restart_artifact_payload(self, *, restart_failure_reason: str | None = None) -> dict[str, Any]:
        return {
            "reason": restart_failure_reason or "ws1006_process_restart_required",
            "restart_failure_reason": restart_failure_reason or "ws1006_process_restart_required",
            "no_order_action": True,
            "order_safe": True,
            "session_id": self.session_id,
            "pid": int(os.getpid()),
            "timestamp": self.updated_at_epoch,
            "updated_at_ist": self.updated_at_ist,
            "restart_allowed_only_if_no_open_positions": True,
        }


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
    if text in {"1", "true", "yes", "y", "ok", "healthy", "live", "fresh"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded"}:
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


def _ist_timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()


def _normalize_symbols(value: Any) -> tuple[str, ...]:
    if value in (None, "", "None"):
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(sorted({str(item).strip().upper() for item in value if str(item).strip()}))
    text = str(value).strip().upper()
    return (text,) if text else ()


def _truthy_any(*values: Any) -> bool:
    for value in values:
        flag = _as_bool(value)
        if flag is True:
            return True
    return False


def _ws_fault_class(*, feed_error_code: Any, recovery_blocked: bool, process_restart_required: bool, runtime_state: str, reason_code: str) -> str:
    runtime_state_upper = _upper(runtime_state)
    reason_code_upper = _upper(reason_code)
    try:
        code_int = int(feed_error_code) if feed_error_code is not None else None
    except Exception:
        code_int = None
    if reason_code_upper in {"AUTH_BLOCKED", "TOKEN_INVALID", "LOGIN_REQUIRED"}:
        return "AUTH_BLOCKED"
    if recovery_blocked or process_restart_required or runtime_state_upper in {"RECOVERY_BLOCKED", "RESTART_REQUIRED"} or reason_code_upper in {"WS1006_PROCESS_RESTART_REQUIRED", "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED", "RESTART_VERIFY_FAILED"}:
        return "TERMINAL"
    if runtime_state_upper in _RECOVERING_STATES:
        return "RECOVERABLE_WS_DROP"
    if code_int == 1006:
        return "RECOVERABLE_WS_DROP"
    return "UNKNOWN"


def build_canonical_feed_truth_state(
    payload: Mapping[str, Any] | None,
    *,
    restart_artifact_dir: Path | None = None,
) -> CanonicalFeedTruthState:
    source = _as_mapping(payload)
    now_epoch = float(source.get("updated_at_epoch") or source.get("ts_epoch") or time.time())
    updated_at_ist = str(source.get("updated_at_ist") or _ist_timestamp(now_epoch))
    session_id = str(source.get("session_id") or source.get("run_id") or "").strip()
    runtime_state = _upper(source.get("runtime_state"))
    recovery_state = _upper(source.get("recovery_state") or source.get("ws_recovery_state") or runtime_state)
    ws_error_code = _as_int(source.get("ws_error_code") or source.get("feed_error_code") or source.get("disconnected_code") or source.get("ws_error"))
    ws_error_reason = str(source.get("ws_error_reason") or source.get("disconnected_reason") or source.get("last_error") or "").strip() or None
    restart_failure_reason = str(
        source.get("restart_failure_reason")
        or source.get("restart_blocked_reason")
        or source.get("reconnect_blocked_reason")
        or ws_error_reason
        or ""
    ).strip() or None
    ws_connected = _as_bool(source.get("ws_connected"))
    if ws_connected is None:
        ws_connected = _as_bool(source.get("effective_ws_connected"))
    if ws_connected is None:
        ws_connected = False
    latest_ltp_age_sec = _as_float(source.get("latest_ltp_age_sec") or source.get("ltp_age_sec"))
    latest_depth_age_sec = _as_float(source.get("latest_depth_age_sec") or source.get("depth_age_sec"))
    latest_option_tick_age_sec = _as_float(source.get("latest_option_tick_age_sec") or source.get("option_tick_age_sec") or source.get("latest_option_tick_age"))
    subscribed_option_tokens_count = _as_int(source.get("subscribed_option_tokens_count") or source.get("option_subscribe_count"))
    verified_option_symbols = _normalize_symbols(source.get("verified_option_symbols") or source.get("option_symbols_verified") or source.get("verified_symbols"))
    missing_option_symbols = _normalize_symbols(source.get("missing_option_symbols") or source.get("option_symbols_missing"))
    process_restart_required = _truthy_any(
        source.get("process_restart_required"),
        runtime_state in _RESTART_REQUIRED_STATES,
        _upper(source.get("feed_truth_reason_code")) in _RESTART_REQUIRED_STATES,
        _upper(source.get("reconnect_blocked_reason")) in _RESTART_REQUIRED_STATES,
    )
    if not process_restart_required and ws_connected is False and ws_error_code == 1006 and runtime_state not in _RECOVERING_STATES:
        process_restart_required = True
    recovery_blocked = _truthy_any(source.get("recovery_blocked"), source.get("feed_recovery_blocked"), runtime_state in _RECOVERY_BLOCKED_STATES, process_restart_required)
    underlying_tick_fresh = _truthy_any(source.get("underlying_tick_fresh"), latest_ltp_age_sec is not None and latest_ltp_age_sec <= float(source.get("max_ltp_age_sec") or 2.5))
    depth_fresh = _truthy_any(source.get("depth_fresh"), latest_depth_age_sec is not None and latest_depth_age_sec <= float(source.get("max_depth_age_sec") or 6.0))
    option_ticks_verified = _truthy_any(source.get("option_ticks_verified"), bool(verified_option_symbols) and not missing_option_symbols)

    blockers: list[str] = []
    reason_code = _upper(source.get("reason_code") or source.get("feed_truth_reason_code") or runtime_state or "unknown") or "UNKNOWN"

    if recovery_state in _RECOVERING_STATES:
        reason_code = reason_code if reason_code not in {"UNKNOWN", ""} else recovery_state
    if process_restart_required:
        blockers.append("WS1006_PROCESS_RESTART_REQUIRED")
    if recovery_blocked:
        blockers.append("RECOVERY_BLOCKED")
    if not ws_connected and runtime_state not in _BOOTING_STATES:
        blockers.append("WS_DISCONNECTED")
    if latest_ltp_age_sec is not None and latest_ltp_age_sec > float(source.get("max_ltp_age_sec") or 2.5):
        blockers.append("LTP_STALE")
    if latest_depth_age_sec is not None and latest_depth_age_sec > float(source.get("max_depth_age_sec") or 6.0):
        blockers.append("DEPTH_STALE")
    if latest_option_tick_age_sec is not None and latest_option_tick_age_sec > float(source.get("max_option_tick_age_sec") or 3.0):
        blockers.append("OPTION_TICK_STALE")
    if missing_option_symbols:
        blockers.append("MISSING_OPTION_SYMBOLS")
    if not option_ticks_verified:
        blockers.append("OPTION_TICKS_UNVERIFIED")
    if not underlying_tick_fresh:
        blockers.append("UNDERLYING_TICK_STALE")
    if not depth_fresh:
        blockers.append("DEPTH_STALE")

    if runtime_state in _BOOTING_STATES:
        state = "BOOTING"
        reason_code = reason_code or "BOOTING"
    elif runtime_state in _CONNECTING_STATES:
        state = "CONNECTING"
        reason_code = reason_code or "CONNECTING"
    elif runtime_state in _RECOVERING_STATES:
        state = "DEGRADED"
        reason_code = reason_code or recovery_state or "RECOVERING_WS_DROP"
    elif runtime_state in _SUBSCRIBED_STATES and not option_ticks_verified:
        state = "SUBSCRIBED"
        reason_code = reason_code or "SUBSCRIBED"
    elif runtime_state in _VERIFYING_STATES or (runtime_state in _SUBSCRIBED_STATES and option_ticks_verified is False):
        state = "VERIFYING_OPTION_TICKS"
        reason_code = reason_code or "VERIFYING_OPTION_TICKS"
    elif process_restart_required:
        state = "RESTART_REQUIRED"
        reason_code = "WS1006_PROCESS_RESTART_REQUIRED" if _upper(source.get("feed_error_code")) == "1006" else reason_code or "RESTART_REQUIRED"
    elif recovery_blocked:
        state = "RECOVERY_BLOCKED"
        reason_code = reason_code or "RECOVERY_BLOCKED"
    elif not ws_connected:
        state = "DEGRADED"
        reason_code = "WS_DISCONNECTED"
    elif runtime_state in _HEALTHY_STATES:
        if ws_connected and underlying_tick_fresh and depth_fresh and option_ticks_verified and not recovery_blocked and not process_restart_required:
            state = "VERIFIED_HEALTHY"
            blockers = []
            reason_code = reason_code or "VERIFIED_HEALTHY"
        else:
            state = "DEGRADED"
            reason_code = reason_code or "DEGRADED"
    elif runtime_state in _DEGRADED_STATES:
        state = "DEGRADED"
        reason_code = reason_code or "DEGRADED"
    elif option_ticks_verified and ws_connected and underlying_tick_fresh and depth_fresh and not recovery_blocked and not process_restart_required:
        state = "VERIFIED_HEALTHY"
        blockers = []
        reason_code = reason_code or "VERIFIED_HEALTHY"
    else:
        state = "DEGRADED"
        reason_code = reason_code or "DEGRADED"

    if state != "VERIFIED_HEALTHY" and not blockers:
        blockers.append(state)

    state_obj = CanonicalFeedTruthState(
        state=state,
        reason_code=reason_code,
        recovery_state=recovery_state if recovery_state in _RECOVERING_STATES or recovery_state in _VERIFYING_STATES else (recovery_state or state),
        ws_error_code=ws_error_code if ws_error_code != 0 else None,
        ws_error_reason=ws_error_reason,
        ws_fault_class=_ws_fault_class(
            feed_error_code=ws_error_code,
            recovery_blocked=bool(recovery_blocked),
            process_restart_required=bool(process_restart_required),
            runtime_state=runtime_state,
            reason_code=reason_code,
        ),
        blockers=tuple(dict.fromkeys(blockers)),
        ws_connected=bool(ws_connected),
        underlying_tick_fresh=bool(underlying_tick_fresh),
        option_ticks_verified=bool(option_ticks_verified),
        depth_fresh=bool(depth_fresh),
        latest_ltp_age_sec=latest_ltp_age_sec,
        latest_depth_age_sec=latest_depth_age_sec,
        latest_option_tick_age_sec=latest_option_tick_age_sec,
        subscribed_option_tokens_count=subscribed_option_tokens_count,
        verified_option_symbols=verified_option_symbols,
        missing_option_symbols=missing_option_symbols,
        recovery_blocked=bool(recovery_blocked),
        process_restart_required=bool(process_restart_required),
        restart_failure_reason=restart_failure_reason,
        session_id=session_id,
        updated_at_epoch=now_epoch,
        updated_at_ist=updated_at_ist,
    )

    if state_obj.process_restart_required and restart_artifact_dir is not None:
        restart_artifact_dir.mkdir(parents=True, exist_ok=True)
        restart_path = restart_artifact_dir / "feed_restart_required.json"
        restart_path.write_text(
            json.dumps(state_obj.restart_artifact_payload(restart_failure_reason=restart_failure_reason), sort_keys=True),
            encoding="utf-8",
        )

    return state_obj
