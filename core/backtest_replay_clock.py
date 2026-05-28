from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Mapping, Sequence

ReplayAccessStatus = Literal["ALLOW", "BLOCK"]

REPLAY_CLOCK_SCHEMA_VERSION = 1
REPLAY_CLOCK_SOURCE = "replay_clock_no_future_leak_guard_v1"

REASON_CURRENT_TIMESTAMP_BEFORE_SESSION = "CURRENT_TIMESTAMP_BEFORE_SESSION"
REASON_CURRENT_TIMESTAMP_AFTER_SESSION = "CURRENT_TIMESTAMP_AFTER_SESSION"
REASON_NON_MONOTONIC_ADVANCE = "NON_MONOTONIC_ADVANCE"
REASON_SNAPSHOT_IN_FUTURE = "SNAPSHOT_IN_FUTURE"
REASON_SNAPSHOT_BEFORE_SESSION = "SNAPSHOT_BEFORE_SESSION"
REASON_SNAPSHOT_AFTER_SESSION = "SNAPSHOT_AFTER_SESSION"
REASON_LOOKBACK_EXCEEDED = "LOOKBACK_EXCEEDED"
REASON_CANDLE_FIELD_IN_FUTURE = "CANDLE_FIELD_IN_FUTURE"
REASON_FULL_SESSION_AGGREGATE_UNAVAILABLE = "FULL_SESSION_AGGREGATE_UNAVAILABLE"
REASON_NON_MONOTONIC_REPLAY_DATA = "NON_MONOTONIC_REPLAY_DATA"


class ReplayClockContractError(ValueError):
    """Raised when replay clock input would allow invalid replay-time behavior."""


@dataclass(frozen=True)
class ReplayAccessDecision:
    """Deterministic read-only decision for replay-time data access."""

    status: ReplayAccessStatus
    reason: str
    current_timestamp: str
    requested_timestamp: str | None = None
    source: str = REPLAY_CLOCK_SOURCE
    schema_version: int = REPLAY_CLOCK_SCHEMA_VERSION
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.status == "ALLOW"

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "allowed": self.allowed,
            "reason": self.reason,
            "current_timestamp": self.current_timestamp,
            "requested_timestamp": self.requested_timestamp,
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": False,
            "is_" + "order_action": False,
            "broker_" + "api_called": False,
            "live_" + "order_action": False,
            "broker_" + "order_action": False,
        }


@dataclass(frozen=True)
class ReplayClockConfig:
    """Configuration for the replay-time authority."""

    session_start: datetime | str
    session_end: datetime | str
    lookback: timedelta | int | float = timedelta(0)

    def normalized(self) -> "ReplayClockConfig":
        start = _parse_timestamp(self.session_start, field_name="session_start")
        end = _parse_timestamp(self.session_end, field_name="session_end")
        if end <= start:
            raise ReplayClockContractError("session_end_must_be_after_session_start")
        lookback = _parse_lookback(self.lookback)
        return ReplayClockConfig(session_start=start, session_end=end, lookback=lookback)


@dataclass(frozen=True)
class ReplayClock:
    """Replay-time authority that blocks access to information beyond current time."""

    config: ReplayClockConfig
    current_timestamp: datetime | str

    @classmethod
    def start(cls, config: ReplayClockConfig) -> "ReplayClock":
        normalized = config.normalized()
        return cls(config=normalized, current_timestamp=normalized.session_start)

    def __post_init__(self) -> None:
        normalized = self.config.normalized()
        current = _parse_timestamp(self.current_timestamp, field_name="current_timestamp")
        _validate_current_in_session(normalized, current)
        object.__setattr__(self, "config", normalized)
        object.__setattr__(self, "current_timestamp", current)

    def advance_to(self, next_timestamp: datetime | str) -> "ReplayClock":
        next_value = _parse_timestamp(next_timestamp, field_name="next_timestamp")
        if next_value < self.current_timestamp:
            raise ReplayClockContractError(REASON_NON_MONOTONIC_ADVANCE)
        _validate_current_in_session(self.config, next_value)
        return ReplayClock(config=self.config, current_timestamp=next_value)

    def snapshot_access(self, snapshot_timestamp: datetime | str) -> ReplayAccessDecision:
        requested = _parse_timestamp(snapshot_timestamp, field_name="snapshot_timestamp")
        if requested < self.config.session_start:
            return self._block(REASON_SNAPSHOT_BEFORE_SESSION, requested)
        if requested > self.config.session_end:
            return self._block(REASON_SNAPSHOT_AFTER_SESSION, requested)
        if requested > self.current_timestamp:
            return self._block(REASON_SNAPSHOT_IN_FUTURE, requested)
        if requested < self.current_timestamp - self.config.lookback:
            return self._block(REASON_LOOKBACK_EXCEEDED, requested)
        return self._allow("SNAPSHOT_VISIBLE", requested)

    def require_snapshot_visible(self, snapshot_timestamp: datetime | str) -> None:
        decision = self.snapshot_access(snapshot_timestamp)
        if decision.blocked:
            raise ReplayClockContractError(decision.reason)

    def candle_field_access(
        self,
        *,
        candle_start: datetime | str,
        candle_end: datetime | str,
        field_name: str,
    ) -> ReplayAccessDecision:
        start = _parse_timestamp(candle_start, field_name="candle_start")
        end = _parse_timestamp(candle_end, field_name="candle_end")
        if end <= start:
            raise ReplayClockContractError("candle_end_must_be_after_candle_start")
        normalized_field = field_name.strip().lower()
        if not normalized_field:
            raise ReplayClockContractError("field_name_required")
        if start > self.current_timestamp:
            return self._block(REASON_CANDLE_FIELD_IN_FUTURE, start, {"field_name": normalized_field})
        if normalized_field in {"high", "low", "close", "hlc3", "ohlc4"} and end > self.current_timestamp:
            return self._block(REASON_CANDLE_FIELD_IN_FUTURE, end, {"field_name": normalized_field})
        if end > self.config.session_end or start < self.config.session_start:
            return self._block(REASON_SNAPSHOT_AFTER_SESSION, end, {"field_name": normalized_field})
        return self._allow("CANDLE_FIELD_VISIBLE", end, {"field_name": normalized_field})

    def require_candle_field_visible(
        self,
        *,
        candle_start: datetime | str,
        candle_end: datetime | str,
        field_name: str,
    ) -> None:
        decision = self.candle_field_access(
            candle_start=candle_start,
            candle_end=candle_end,
            field_name=field_name,
        )
        if decision.blocked:
            raise ReplayClockContractError(decision.reason)

    def full_session_aggregate_access(self, aggregate_name: str) -> ReplayAccessDecision:
        name = aggregate_name.strip()
        if not name:
            raise ReplayClockContractError("aggregate_name_required")
        if self.current_timestamp < self.config.session_end:
            return self._block(
                REASON_FULL_SESSION_AGGREGATE_UNAVAILABLE,
                self.config.session_end,
                {"aggregate_name": name},
            )
        return self._allow("FULL_SESSION_AGGREGATE_VISIBLE", self.config.session_end, {"aggregate_name": name})

    def require_full_session_aggregate_visible(self, aggregate_name: str) -> None:
        decision = self.full_session_aggregate_access(aggregate_name)
        if decision.blocked:
            raise ReplayClockContractError(decision.reason)

    def _allow(
        self,
        reason: str,
        requested_timestamp: datetime,
        metadata: Mapping[str, object] | None = None,
    ) -> ReplayAccessDecision:
        return ReplayAccessDecision(
            status="ALLOW",
            reason=reason,
            current_timestamp=_format_timestamp(self.current_timestamp),
            requested_timestamp=_format_timestamp(requested_timestamp),
            metadata=metadata or {},
        )

    def _block(
        self,
        reason: str,
        requested_timestamp: datetime,
        metadata: Mapping[str, object] | None = None,
    ) -> ReplayAccessDecision:
        return ReplayAccessDecision(
            status="BLOCK",
            reason=reason,
            current_timestamp=_format_timestamp(self.current_timestamp),
            requested_timestamp=_format_timestamp(requested_timestamp),
            metadata=metadata or {},
        )


def build_replay_clock(
    *,
    session_start: datetime | str,
    session_end: datetime | str,
    current_timestamp: datetime | str | None = None,
    lookback_seconds: int | float = 0,
) -> ReplayClock:
    config = ReplayClockConfig(
        session_start=session_start,
        session_end=session_end,
        lookback=lookback_seconds,
    )
    normalized = config.normalized()
    return ReplayClock(config=normalized, current_timestamp=current_timestamp or normalized.session_start)


def validate_monotonic_replay_timestamps(
    timestamps: Iterable[datetime | str],
    *,
    session_start: datetime | str | None = None,
    session_end: datetime | str | None = None,
) -> tuple[str, ...]:
    parsed: list[datetime] = []
    for index, timestamp in enumerate(timestamps):
        current = _parse_timestamp(timestamp, field_name=f"timestamps[{index}]")
        if parsed and current < parsed[-1]:
            raise ReplayClockContractError(REASON_NON_MONOTONIC_REPLAY_DATA)
        parsed.append(current)
    if session_start is not None:
        start = _parse_timestamp(session_start, field_name="session_start")
        if any(timestamp < start for timestamp in parsed):
            raise ReplayClockContractError(REASON_SNAPSHOT_BEFORE_SESSION)
    if session_end is not None:
        end = _parse_timestamp(session_end, field_name="session_end")
        if any(timestamp > end for timestamp in parsed):
            raise ReplayClockContractError(REASON_SNAPSHOT_AFTER_SESSION)
    return tuple(_format_timestamp(timestamp) for timestamp in parsed)


def visible_snapshots(
    clock: ReplayClock,
    snapshots: Sequence[Mapping[str, object]],
    *,
    timestamp_field: str = "timestamp",
) -> tuple[Mapping[str, object], ...]:
    visible: list[Mapping[str, object]] = []
    for snapshot in snapshots:
        if timestamp_field not in snapshot:
            raise ReplayClockContractError("snapshot_timestamp_field_required")
        decision = clock.snapshot_access(snapshot[timestamp_field])  # type: ignore[arg-type]
        if decision.allowed:
            visible.append(snapshot)
    return tuple(visible)


def _parse_timestamp(value: datetime | str | object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ReplayClockContractError(f"{field_name}_required")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ReplayClockContractError(f"{field_name}_invalid") from exc
    else:
        raise ReplayClockContractError(f"{field_name}_invalid_type")
    if parsed.tzinfo is None:
        raise ReplayClockContractError(f"{field_name}_timezone_required")
    return parsed.astimezone(timezone.utc)


def _parse_lookback(value: timedelta | int | float) -> timedelta:
    if isinstance(value, timedelta):
        lookback = value
    elif isinstance(value, (int, float)):
        lookback = timedelta(seconds=value)
    else:
        raise ReplayClockContractError("lookback_invalid_type")
    if lookback < timedelta(0):
        raise ReplayClockContractError("lookback_must_be_non_negative")
    return lookback


def _validate_current_in_session(config: ReplayClockConfig, current: datetime) -> None:
    start = _parse_timestamp(config.session_start, field_name="session_start")
    end = _parse_timestamp(config.session_end, field_name="session_end")
    if current < start:
        raise ReplayClockContractError(REASON_CURRENT_TIMESTAMP_BEFORE_SESSION)
    if current > end:
        raise ReplayClockContractError(REASON_CURRENT_TIMESTAMP_AFTER_SESSION)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
