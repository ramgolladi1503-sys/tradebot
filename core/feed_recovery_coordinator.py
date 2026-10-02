from __future__ import annotations

import copy
import time
import threading
import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Literal, Mapping

from config import feed_runtime_reliability as reliability_cfg


RecoveryAction = Literal[
    "SOFT_RECONNECT",
    "BLOCKED",
    "RECOVERY_TIMEOUT",
    "RECOVERY_BLOCKED",
    "TERMINAL",
    "AUTH_REQUIRED",
]


def is_plain_ws1006_peer_drop(*, code: int | None, reason: str | None) -> bool:
    """Recognize known plain transport-close text for websocket close code 1006."""
    try:
        code_int = int(code or 0)
    except (TypeError, ValueError):
        return False
    if code_int != 1006:
        return False
    reason_lower = str(reason or "").lower()
    return any(
        marker in reason_lower
        for marker in (
            "connection was closed uncleanly",
            "peer dropped",
            "closed abnormally",
            "without closing handshake",
        )
    )


@dataclass(frozen=True)
class FeedRecoveryState:
    recovery_in_progress: bool = False
    recovery_reason: str = ""
    recovery_source: str = ""
    recovery_started_epoch: float = 0.0
    recovery_attempt_window_start_epoch: float = 0.0
    recovery_attempt_count: int = 0
    last_recovery_action: str = ""
    last_recovery_action_epoch: float = 0.0
    recovery_generation_id: int = 0
    terminal_failure: bool = False
    process_restart_required: bool = False
    recovery_timeout: bool = False
    recovery_blocked: bool = False
    auth_required: bool = False


@dataclass(frozen=True)
class FeedRecoveryDecision:
    event: str
    accepted: bool
    action: RecoveryAction
    events_emitted: list[str]
    state: FeedRecoveryState


class FeedRecoveryCoordinator:
    def __init__(
        self,
        *,
        max_recoverable_attempts_per_session: int = 2,
        recoverable_retry_cooldown_sec: float = 10.0,
        recovery_timeout_sec: float = 90.0,
        max_recoveries_per_window: int = 3,
        recovery_window_sec: float = 600.0,
        max_recovery_gap_sec: float | None = None,
        now_epoch_fn: Callable[[], float] | None = None,
    ) -> None:
        self._max_recoverable_attempts_per_session = max(1, int(max_recoverable_attempts_per_session or 1))
        self._recoverable_retry_cooldown_sec = max(0.0, float(recoverable_retry_cooldown_sec or 0.0))
        self._recovery_timeout_sec = max(0.0, float(recovery_timeout_sec or 0.0))
        self._max_recoveries_per_window = max(1, int(max_recoveries_per_window or 1))
        self._recovery_window_sec = max(0.0, float(recovery_window_sec or 0.0))
        try:
            gap_limit = float(
                max_recovery_gap_sec
                if max_recovery_gap_sec is not None
                else getattr(reliability_cfg, "FEED_RECOVERY_MAX_GAP_SEC", 3.0)
            )
        except (TypeError, ValueError):
            gap_limit = 0.0
        self._max_recovery_gap_sec = max(0.0, gap_limit) if math.isfinite(gap_limit) else 0.0
        try:
            health_window = float(getattr(reliability_cfg, "FEED_RECOVERY_HEALTH_WINDOW_SEC", 2.0))
        except (TypeError, ValueError):
            health_window = math.inf
        self._min_healthy_window_sec = (
            health_window if math.isfinite(health_window) and health_window > 0.0 else math.inf
        )
        self._now_epoch_fn = now_epoch_fn or time.time
        self._state = FeedRecoveryState()
        self._incident_history: list[dict[str, Any]] = []

    @property
    def incident_history(self) -> tuple[dict[str, Any], ...]:
        """Return isolated snapshots; nested evidence must not alias internal history."""
        return tuple(copy.deepcopy(row) for row in self._incident_history)

    @property
    def state(self) -> FeedRecoveryState:
        return self._state

    def get_state_snapshot(self) -> FeedRecoveryState:
        """Returns an immutable snapshot of the current recovery state."""
        return self._state

    def _now_epoch(self) -> float:
        try:
            return float(self._now_epoch_fn())
        except Exception:
            return 0.0

    def _reset_window_if_needed(self, state: FeedRecoveryState, now_epoch: float) -> FeedRecoveryState:
        window_start = float(state.recovery_attempt_window_start_epoch or 0.0)
        if window_start <= 0.0:
            return replace(state, recovery_attempt_window_start_epoch=now_epoch)
        if self._recovery_window_sec <= 0.0:
            return replace(state, recovery_attempt_window_start_epoch=now_epoch)
        if (now_epoch - window_start) > self._recovery_window_sec:
            return replace(state, recovery_attempt_window_start_epoch=now_epoch, recovery_attempt_count=0)
        return state

    def _current_state(self) -> FeedRecoveryState:
        now_epoch = self._now_epoch()
        state = self._reset_window_if_needed(self._state, now_epoch)
        if state.recovery_in_progress and self._recovery_timeout_sec > 0.0:
            started = float(state.recovery_started_epoch or 0.0)
            if started > 0.0 and (now_epoch - started) > self._recovery_timeout_sec:
                state = replace(
                    state,
                    recovery_in_progress=False,
                    recovery_timeout=True,
                    recovery_blocked=False,
                    last_recovery_action="RECOVERY_TIMEOUT",
                    last_recovery_action_epoch=now_epoch,
                    recovery_generation_id=int(state.recovery_generation_id) + 1,
                )
        self._state = state
        return state

    def reset(self) -> FeedRecoveryState:
        self._state = FeedRecoveryState()
        self._incident_history.clear()
        return self._state

    def clear_recovery(
        self, *, source: str, reason: str, proof: Mapping[str, Any] | None = None
    ) -> FeedRecoveryState:
        now_epoch = self._now_epoch()
        valid, failures = self._validate_recovery_proof(proof, now_epoch=now_epoch)
        self._incident_history.append({
            "event": "RECOVERY_RESOLVED" if valid else "RECOVERY_CLEAR_REJECTED",
            "source": str(source),
            "reason": str(reason),
            "at_epoch": now_epoch,
            "proof": copy.deepcopy(dict(proof or {})),
            "failures": list(failures),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        })
        if not valid:
            return self._current_state()
        next_state = replace(
            self._current_state(),
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="CLEARED",
            last_recovery_action_epoch=now_epoch,
            recovery_generation_id=int(self._state.recovery_generation_id) + 1,
            terminal_failure=False,
            process_restart_required=False,
            recovery_timeout=False,
            recovery_blocked=False,
            auth_required=False,
        )
        self._state = next_state
        return next_state

    def _validate_recovery_proof(
        self, proof: Mapping[str, Any] | None, *, now_epoch: float
    ) -> tuple[bool, tuple[str, ...]]:
        if not isinstance(proof, Mapping):
            return False, ("recovery_proof_missing",)
        failures: list[str] = []
        try:
            disconnect = float(proof.get("disconnect_started_at"))
            reconnect = float(proof.get("reconnected_at"))
        except (TypeError, ValueError):
            disconnect = reconnect = 0.0
        if (
            not math.isfinite(disconnect)
            or not math.isfinite(reconnect)
            or disconnect <= 0
            or reconnect < disconnect
            or reconnect > now_epoch
        ):
            failures.append("recovery_timestamps_invalid")
        expected_raw = proof.get("expected_tokens")
        actual_raw = proof.get("actual_tokens")
        if not isinstance(expected_raw, (list, tuple, set)) or not isinstance(actual_raw, (list, tuple, set)):
            failures.append("required_token_set_invalid")
            expected_raw, actual_raw = (), ()
        expected_values = [str(x).strip() for x in expected_raw if str(x).strip()]
        actual_values = [str(x).strip() for x in actual_raw if str(x).strip()]
        expected = tuple(sorted(set(expected_values)))
        actual = tuple(sorted(set(actual_values)))
        if len(expected) != len(expected_values) or len(actual) != len(actual_values):
            failures.append("required_token_set_has_duplicates")
        if not expected:
            failures.append("required_token_set_missing")
        if expected != actual:
            failures.append("required_token_set_mismatch")
        if type(proof.get("expected_token_count")) is not int or proof.get("expected_token_count") != len(expected):
            failures.append("expected_token_count_mismatch")
        if (
            type(proof.get("actual_resubscribed_token_count")) is not int
            or proof.get("actual_resubscribed_token_count") != len(actual)
        ):
            failures.append("actual_resubscribed_token_count_mismatch")
        if str(proof.get("actual_subscription_evidence") or "").strip().upper() != "LOCAL_SUBSCRIBE_AND_MODE_CALL_RETURNED":
            failures.append("actual_subscription_evidence_unproven")
        gaps = proof.get("gap_duration_by_identity")
        pre_ticks = proof.get("last_pre_disconnect_timestamp_by_required_identity")
        post_ticks = proof.get("first_post_disconnect_timestamp_by_required_identity")
        required_raw = proof.get("required_identity_tokens")
        if not isinstance(required_raw, (list, tuple, set)):
            failures.append("required_identity_set_invalid")
            required_raw = ()
        required_values = [str(x).strip() for x in required_raw if str(x).strip()]
        required = tuple(sorted(set(required_values)))
        if len(required) != len(required_values):
            failures.append("required_identity_set_has_duplicates")
        if not required:
            failures.append("required_identity_set_missing")
        if not set(required).issubset(set(expected)):
            failures.append("required_identity_not_subscribed")
        if (
            not isinstance(gaps, Mapping)
            or not isinstance(pre_ticks, Mapping)
            or not isinstance(post_ticks, Mapping)
            or set(map(str, gaps.keys())) != set(required)
            or set(map(str, pre_ticks.keys())) != set(required)
            or set(map(str, post_ticks.keys())) != set(required)
        ):
            failures.append("required_identity_gap_evidence_incomplete")
        else:
            for identity, raw_gap in gaps.items():
                try:
                    gap = float(raw_gap)
                    pre_tick = float(pre_ticks[identity])
                    post_tick = float(post_ticks[identity])
                except (TypeError, ValueError):
                    gap = pre_tick = post_tick = -1.0
                if (
                    not math.isfinite(gap)
                    or not math.isfinite(pre_tick)
                    or not math.isfinite(post_tick)
                    or
                    gap < 0.0
                    or gap > self._max_recovery_gap_sec
                    or pre_tick <= 0.0
                    or pre_tick > disconnect
                    or post_tick < reconnect
                    or post_tick > now_epoch
                    or abs((post_tick - pre_tick) - gap) > 0.001
                ):
                    failures.append(f"required_identity_gap_invalid:{identity}")
        if str(proof.get("state_rebuild_status") or "").strip().upper() != "REBUILT":
            failures.append("state_rebuild_unproven")
        try:
            window_start = float(proof.get("health_window_start"))
            window_end = float(proof.get("health_window_end"))
        except (TypeError, ValueError):
            window_start = window_end = 0.0
        if (
            window_start < reconnect
            or window_end <= window_start
            or window_end > now_epoch
            or (window_end - window_start) < self._min_healthy_window_sec
        ):
            failures.append("health_window_unproven")
        if not math.isfinite(window_start) or not math.isfinite(window_end):
            failures.append("health_window_unproven")
        if str(proof.get("recovery_verdict") or "").strip().upper() != "RECOVERED":
            failures.append("recovery_verdict_unproven")
        if str(proof.get("health_window_status") or "").strip().upper() != "HEALTHY":
            failures.append("health_window_not_healthy")
        if proof.get("ws_connected") is not True:
            failures.append("health_window_websocket_not_connected")
        if proof.get("required_feeds_fresh") is not True:
            failures.append("health_window_required_feeds_not_fresh")
        runtime_state = str(proof.get("runtime_state") or "").strip().upper()
        if runtime_state not in {"RUNNING", "LIVE", "HEALTHY", "OK"}:
            failures.append("health_window_runtime_state_unsafe")
        return not failures, tuple(failures)

    def request_recovery(
        self,
        *,
        source: str,
        code: int | None,
        reason: str | None,
        max_recoverable_attempts_per_session: int | None = None,
    ) -> FeedRecoveryDecision:
        current_state = self._current_state()
        reason_text = str(reason or "")
        now_epoch = self._now_epoch()
        if current_state.terminal_failure or current_state.process_restart_required:
            return self._terminal_decision(source=source, reason=current_state.recovery_reason or reason_text)
        if self._is_terminal_reactor_failure(reason=reason_text):
            return self._terminal_decision(source=source, reason=reason_text)
        if self._is_auth_failure(code=code, reason=reason_text):
            return self._auth_required_decision(source=source, reason=reason_text)
        if current_state.recovery_timeout:
            return self._timeout_decision(source=source, reason=reason_text)
        if current_state.recovery_in_progress:
            return self._already_in_progress_decision(source=source, reason=reason_text)
        if self._is_plain_ws1006_peer_drop(code=code, reason=reason_text):
            effective_max_attempts = (
                int(max_recoverable_attempts_per_session)
                if max_recoverable_attempts_per_session is not None
                else self._max_recoverable_attempts_per_session
            )
            windowed_state = self._reset_window_if_needed(current_state, now_epoch)
            window_limit = max(0, int(self._max_recoveries_per_window) - 1)
            if int(windowed_state.recovery_attempt_count) >= window_limit:
                return self._blocked_decision(source=source, reason=reason_text, recovery_blocked=True)
            return self._accept_soft_recovery(
                source=source,
                reason=reason_text,
                max_recoverable_attempts_per_session=max(1, effective_max_attempts),
            )
        return self._blocked_decision(source=source, reason=reason_text)

    def _is_terminal_reactor_failure(self, *, reason: str) -> bool:
        reason_lower = reason.lower()
        return "main loop terminated" in reason_lower or "reactornotrestartable" in reason_lower or "ws1006_process_restart" in reason_lower

    def _is_auth_failure(self, *, code: int | None, reason: str) -> bool:
        reason_lower = reason.lower()
        code_text = str(code or "").strip()
        return "auth" in reason_lower or "token" in reason_lower or code_text in {"401", "403"}

    def _is_plain_ws1006_peer_drop(self, *, code: int | None, reason: str) -> bool:
        return is_plain_ws1006_peer_drop(code=code, reason=reason)

    def _terminal_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        next_state = replace(
            self._current_state(),
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="TERMINAL",
            last_recovery_action_epoch=now_epoch,
            terminal_failure=True,
            process_restart_required=True,
            recovery_timeout=False,
            recovery_blocked=True,
            auth_required=False,
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_REQUESTED",
            accepted=False,
            action="TERMINAL",
            events_emitted=[
                "FEED_RECOVERY_REQUESTED",
                "FEED_RECOVERY_ACCEPTED",
                "FEED_RECOVERY_ACTION_SELECTED",
                "FEED_WS_PROCESS_RESTART_REQUIRED",
            ],
            state=next_state,
        )

    def _timeout_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        next_state = replace(
            self._current_state(),
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="RECOVERY_TIMEOUT",
            last_recovery_action_epoch=now_epoch,
            recovery_timeout=True,
            recovery_blocked=True,
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_TIMEOUT",
            accepted=False,
            action="RECOVERY_TIMEOUT",
            events_emitted=["FEED_RECOVERY_TIMEOUT"],
            state=next_state,
        )

    def _auth_required_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        next_state = replace(
            self._current_state(),
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="AUTH_REQUIRED",
            last_recovery_action_epoch=now_epoch,
            process_restart_required=False,
            recovery_timeout=False,
            recovery_blocked=True,
            auth_required=True,
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_AUTH_REQUIRED",
            accepted=False,
            action="AUTH_REQUIRED",
            events_emitted=["FEED_AUTH_REQUIRED"],
            state=next_state,
        )

    def _already_in_progress_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        next_state = replace(
            self._current_state(),
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="RECOVERY_BLOCKED",
            last_recovery_action_epoch=now_epoch,
            recovery_blocked=True,
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_ALREADY_IN_PROGRESS",
            accepted=False,
            action="RECOVERY_BLOCKED",
            events_emitted=[
                "FEED_RECOVERY_ALREADY_IN_PROGRESS",
            ],
            state=next_state,
        )

    def _accept_soft_recovery(
        self,
        *,
        source: str,
        reason: str,
        max_recoverable_attempts_per_session: int | None = None,
    ) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        effective_max_attempts = (
            int(max_recoverable_attempts_per_session)
            if max_recoverable_attempts_per_session is not None
            else self._max_recoverable_attempts_per_session
        )
        current_state = self._reset_window_if_needed(self._current_state(), now_epoch)
        if int(current_state.recovery_attempt_count) >= max(1, effective_max_attempts):
            return self._blocked_decision(source=source, reason=reason, recovery_blocked=True)
        next_generation_id = int(current_state.recovery_generation_id) + 1
        next_state = replace(
            current_state,
            recovery_in_progress=True,
            recovery_reason=reason,
            recovery_source=source,
            recovery_started_epoch=now_epoch,
            recovery_attempt_window_start_epoch=float(current_state.recovery_attempt_window_start_epoch or now_epoch or 0.0),
            recovery_attempt_count=int(current_state.recovery_attempt_count) + 1,
            last_recovery_action="SOFT_RECONNECT",
            last_recovery_action_epoch=now_epoch,
            recovery_generation_id=next_generation_id,
            terminal_failure=False,
            process_restart_required=False,
            recovery_timeout=False,
            recovery_blocked=False,
            auth_required=False,
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_REQUESTED",
            accepted=True,
            action="SOFT_RECONNECT",
            events_emitted=[
                "FEED_RECOVERY_REQUESTED",
                "FEED_RECOVERY_ACCEPTED",
                "FEED_RECOVERY_ACTION_SELECTED",
                "FEED_WS_1006_RECOVERABLE",
                "FEED_WS_1006_RECOVERY_ATTEMPT",
            ],
            state=next_state,
        )

    def _blocked_decision(self, *, source: str, reason: str, recovery_blocked: bool = False) -> FeedRecoveryDecision:
        now_epoch = self._now_epoch()
        state = replace(
            self._current_state(),
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="RECOVERY_BLOCKED",
            last_recovery_action_epoch=now_epoch,
            terminal_failure=False,
            process_restart_required=False,
            recovery_timeout=False,
            recovery_blocked=bool(recovery_blocked),
            auth_required=False,
        )
        self._state = state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_BLOCKED",
            accepted=False,
            action="RECOVERY_BLOCKED",
            events_emitted=["FEED_RECOVERY_BLOCKED"],
            state=state,
        )

_DEFAULT_COORDINATOR: FeedRecoveryCoordinator | None = None
_DEFAULT_LOCK = threading.Lock()

def get_feed_recovery_coordinator() -> FeedRecoveryCoordinator:
    global _DEFAULT_COORDINATOR
    if _DEFAULT_COORDINATOR is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_COORDINATOR is None:
                _DEFAULT_COORDINATOR = FeedRecoveryCoordinator()
    return _DEFAULT_COORDINATOR
