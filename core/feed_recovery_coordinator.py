from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal


RecoveryAction = Literal["SOFT_RECONNECT", "FULL_RESTART", "TERMINAL", "BLOCKED"]


@dataclass(frozen=True)
class FeedRecoveryState:
    recovery_in_progress: bool = False
    recovery_reason: str = ""
    recovery_source: str = ""
    recovery_started_epoch: float = 0.0
    recovery_attempt_count: int = 0
    last_recovery_action: str = ""
    last_recovery_action_epoch: float = 0.0
    recovery_generation_id: int = 0
    terminal_failure: bool = False
    process_restart_required: bool = False


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
    ) -> None:
        self._max_recoverable_attempts_per_session = max(1, int(max_recoverable_attempts_per_session or 1))
        self._recoverable_retry_cooldown_sec = max(0.0, float(recoverable_retry_cooldown_sec or 0.0))
        self._state = FeedRecoveryState()

    @property
    def state(self) -> FeedRecoveryState:
        return self._state

    def reset(self) -> FeedRecoveryState:
        self._state = FeedRecoveryState()
        return self._state

    def clear_recovery(self, *, source: str, reason: str) -> FeedRecoveryState:
        next_state = replace(
            self._state,
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="CLEARED",
            last_recovery_action_epoch=0.0,
            recovery_generation_id=int(self._state.recovery_generation_id) + 1,
            terminal_failure=False,
            process_restart_required=False,
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
        reason_text = str(reason or "")
        if self._is_terminal_reactor_failure(reason=reason_text):
            return self._terminal_decision(source=source, reason=reason_text)
        if self._state.recovery_in_progress:
            return self._already_in_progress_decision(source=source, reason=reason_text)
        if self._is_plain_ws1006_peer_drop(code=code, reason=reason_text):
            effective_max_attempts = (
                int(max_recoverable_attempts_per_session)
                if max_recoverable_attempts_per_session is not None
                else self._max_recoverable_attempts_per_session
            )
            return self._accept_soft_recovery(
                source=source,
                reason=reason_text,
                max_recoverable_attempts_per_session=max(1, effective_max_attempts),
            )
        return self._block_request(source=source, reason=reason_text)

    def _is_terminal_reactor_failure(self, *, reason: str) -> bool:
        reason_lower = reason.lower()
        return "main loop terminated" in reason_lower or "reactornotrestartable" in reason_lower

    def _is_plain_ws1006_peer_drop(self, *, code: int | None, reason: str) -> bool:
        if int(code or 0) != 1006:
            return False
        reason_lower = reason.lower()
        return any(marker in reason_lower for marker in ("connection was closed uncleanly", "peer dropped"))

    def _terminal_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        next_state = replace(
            self._state,
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="TERMINAL",
            last_recovery_action_epoch=0.0,
            terminal_failure=True,
            process_restart_required=True,
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

    def _already_in_progress_decision(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        next_state = replace(
            self._state,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="BLOCKED",
        )
        self._state = next_state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_ALREADY_IN_PROGRESS",
            accepted=False,
            action="BLOCKED",
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
        now_epoch = 0.0
        effective_max_attempts = (
            int(max_recoverable_attempts_per_session)
            if max_recoverable_attempts_per_session is not None
            else self._max_recoverable_attempts_per_session
        )
        if int(self._state.recovery_attempt_count) >= max(1, effective_max_attempts):
            return self._escalate_to_full_restart(source=source, reason=reason)
        next_generation_id = int(self._state.recovery_generation_id) + 1
        next_state = replace(
            self._state,
            recovery_in_progress=True,
            recovery_reason=reason,
            recovery_source=source,
            recovery_started_epoch=now_epoch,
            recovery_attempt_count=int(self._state.recovery_attempt_count) + 1,
            last_recovery_action="SOFT_RECONNECT",
            last_recovery_action_epoch=now_epoch,
            recovery_generation_id=next_generation_id,
            terminal_failure=False,
            process_restart_required=False,
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

    def _escalate_to_full_restart(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        now_epoch = 0.0
        next_state = replace(
            self._state,
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="TERMINAL",
            last_recovery_action_epoch=now_epoch,
            recovery_generation_id=int(self._state.recovery_generation_id) + 1,
            terminal_failure=True,
            process_restart_required=True,
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
                "FEED_WS_1006_RECOVERY_ESCALATED",
                "FEED_WS_PROCESS_RESTART_REQUIRED",
            ],
            state=next_state,
        )

    def _block_request(self, *, source: str, reason: str) -> FeedRecoveryDecision:
        state = replace(
            self._state,
            recovery_in_progress=False,
            recovery_reason=reason,
            recovery_source=source,
            last_recovery_action="BLOCKED",
            last_recovery_action_epoch=0.0,
            terminal_failure=False,
            process_restart_required=False,
        )
        self._state = state
        return FeedRecoveryDecision(
            event="FEED_RECOVERY_REQUESTED",
            accepted=False,
            action="BLOCKED",
            events_emitted=[
                "FEED_RECOVERY_REQUESTED",
                "FEED_RECOVERY_BLOCKED",
            ],
            state=state,
        )
