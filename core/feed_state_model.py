from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

class FeedLifecycleState(str, Enum):
    STARTING = "STARTING"
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    MARKET_CLOSED = "MARKET_CLOSED"
    AUTH_BLOCKED = "AUTH_BLOCKED"

class FeedOperationalState(str, Enum):
    STARTING = "STARTING"
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    DEAD = "DEAD"

class FeedState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED_NO_TICKS = "CONNECTED_NO_TICKS"
    UNDERLYING_TICKS_FLOWING = "UNDERLYING_TICKS_FLOWING"
    OPTION_TICKS_FLOWING = "OPTION_TICKS_FLOWING"
    DEPTH_FLOWING = "DEPTH_FLOWING"
    FULL_FEED_READY = "FULL_FEED_READY"
    DEGRADED_LTP_ONLY = "DEGRADED_LTP_ONLY"
    DEGRADED_STALE = "DEGRADED_STALE"
    RECOVERING = "RECOVERING"

@dataclass(frozen=True)
class FeedHysteresisState:
    consecutive_good: int
    consecutive_bad: int
    feed_ok: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "consecutive_good": self.consecutive_good,
            "consecutive_bad": self.consecutive_bad,
            "feed_ok": self.feed_ok,
        }

@dataclass(frozen=True)
class FeedSnapshot:
    # Preserve legacy fields
    ts_epoch: float
    start_epoch: Optional[float]
    runtime_state: str
    ws_connected: bool
    effective_ws_connected: bool
    market_open: bool
    last_tick_age_sec: Optional[float]
    last_depth_age_sec: Optional[float]
    latest_ltp_age_sec: Optional[float]
    latest_option_tick_age_sec: Optional[float]
    subscribed_tokens_count: int
    subscribed_option_tokens_count: int
    missing_option_tokens_count: int
    process_restart_required: bool
    recovery_blocked: bool
    recovery_state: str
    feed_error_code: str
    feed_error_reason: str
    feed_ok_hysteresis_state: FeedHysteresisState
    reason_code: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "ts_epoch": self.ts_epoch,
            "start_epoch": self.start_epoch,
            "runtime_state": self.runtime_state,
            "ws_connected": self.ws_connected,
            "effective_ws_connected": self.effective_ws_connected,
            "market_open": self.market_open,
            "last_tick_age_sec": self.last_tick_age_sec,
            "last_depth_age_sec": self.last_depth_age_sec,
            "latest_ltp_age_sec": self.latest_ltp_age_sec,
            "latest_option_tick_age_sec": self.latest_option_tick_age_sec,
            "subscribed_tokens_count": self.subscribed_tokens_count,
            "subscribed_option_tokens_count": self.subscribed_option_tokens_count,
            "missing_option_tokens_count": self.missing_option_tokens_count,
            "process_restart_required": self.process_restart_required,
            "recovery_blocked": self.recovery_blocked,
            "recovery_state": self.recovery_state,
            "feed_error_code": self.feed_error_code,
            "feed_error_reason": self.feed_error_reason,
            "feed_ok_hysteresis_state": self.feed_ok_hysteresis_state.to_payload(),
            "reason_code": self.reason_code,
        }

@dataclass(frozen=True)
class FeedVerdict:
    lifecycle_state: FeedLifecycleState
    operational_state: FeedOperationalState
    feed_ok: bool
    restart_required: bool
    reason_code: str
    blockers: List[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "lifecycle_state": self.lifecycle_state.value,
            "operational_state": self.operational_state.value,
            "feed_ok": self.feed_ok,
            "restart_required": self.restart_required,
            "reason_code": self.reason_code,
            "blockers": list(self.blockers),
        }
