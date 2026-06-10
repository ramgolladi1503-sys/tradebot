from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable, Literal


RecoveryAction = Literal[
    "SOFT_RECONNECT",
    "BLOCKED",
    "RECOVERY_TIMEOUT",
    "RECOVERY_BLOCKED",
    "TERMINAL",
    "AUTH_REQUIRED",
]


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
        now_epoch_fn: Callable[[], float] | None = None,
    ) -> None:
        self._max_recoverable_attempts_per_session = max(1, int(max_recoverable_attempts_per_session or 1))
        self._recoverable_retry_cooldown_sec = max(0.0, float(recoverable_retry_cooldown_sec or 0.0))
        self._recovery_timeout_sec = max(0.0, float(recovery_timeout_sec or 0.0))
        self._max_recoveries_per_window = max(1, int(max_recoveries_per_window or 1))
        self._recovery_window_sec = max(0.0, float(recovery_window_sec or 0.0))
        self._now_epoch_fn = now_epoch_fn or time.time
        self._state = FeedRecoveryState()

    @property
    def state(self) -> FeedRecoveryState:
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
        return self._state

    def clear_recovery(self, *, source: str, reason: str) -> FeedRecoveryState:
        now_epoch = self._now_epoch()
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
        if int(code or 0) != 1006:
            return False
        reason_lower = reason.lower()
        return any(marker in reason_lower for marker in ("connection was closed uncleanly", "peer dropped"))

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
