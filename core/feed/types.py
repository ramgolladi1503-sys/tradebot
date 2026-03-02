from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FeedState(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class FeedGroupType(str, Enum):
    INDEX = "INDEX"
    OPTIONS = "OPTIONS"


@dataclass(frozen=True)
class FeedGroupKey:
    name: str

    def __str__(self) -> str:
        return self.name

    @property
    def group_type(self) -> FeedGroupType:
        raw = str(self.name or "").upper().strip()
        if raw.startswith("INDEX:"):
            return FeedGroupType.INDEX
        return FeedGroupType.OPTIONS


@dataclass(frozen=True)
class FeedThresholds:
    ok_age_p95: float
    deg_age_p95: float
    down_age_p95: float

    ok_spread_p95: float | None = None
    deg_spread_p95: float | None = None
    ok_depth_missing_pct: float | None = None
    deg_depth_missing_pct: float | None = None

    downgrade_window_sec: float = 10.0
    upgrade_window_sec: float = 60.0
    min_hold_sec: float = 30.0
    ws_down_age_sec: float = 15.0

    flap_window_sec: float = 300.0
    flap_max_transitions: int = 3
    flap_lock_sec: float = 300.0
