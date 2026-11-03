from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from core.upstox_stream_broadcaster import (
    StreamSubscriber,
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class LegSyncResult:
    is_valid: bool
    legs_map: dict[str, UpstoxLevel5DepthRecord]
    rejection_reason: str
    skew_ms: float
    max_exchange_ts_ms: int
    min_exchange_ts_ms: int


class InMemorySentinelAdapter(StreamSubscriber):
    """Bounded circular / latest-state coalescing maps per token with causal
    cross-strike skew gating.
    
    Decision Latency target: < 25ms p99.
    """

    def __init__(
        self,
        skew_threshold_ms: float = 250.0,
        staleness_timeout_ms: float = 1000.0,
    ) -> None:
        self.skew_threshold_ms = float(skew_threshold_ms)
        self.staleness_timeout_ms = float(staleness_timeout_ms)

        self._latest_depth: dict[str, UpstoxLevel5DepthRecord] = {}
        self._latest_ticks: dict[str, UpstoxTickRecord] = {}
        self._lock = threading.Lock()

        # Non-negotiable Trading Safety Invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    def on_tick(self, tick: UpstoxTickRecord) -> None:
        """O(1) update into tick state map."""
        with self._lock:
            self._latest_ticks[tick.token] = tick

    def on_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        """O(1) update into depth state map."""
        with self._lock:
            self._latest_depth[depth.token] = depth

    def on_stream_status(self, status: Any) -> None:
        pass

    def get_latest_tick(self, token: str) -> UpstoxTickRecord | None:
        with self._lock:
            return self._latest_ticks.get(token)

    def get_latest_depth(self, token: str) -> UpstoxLevel5DepthRecord | None:
        with self._lock:
            return self._latest_depth.get(token)

    def get_all_ticks(self) -> dict[str, UpstoxTickRecord]:
        with self._lock:
            return dict(self._latest_ticks)

    def get_all_depth(self) -> dict[str, UpstoxLevel5DepthRecord]:
        with self._lock:
            return dict(self._latest_depth)

    def get_synchronized_legs(
        self,
        tokens: list[str],
        now_monotonic_ns: int | None = None,
    ) -> tuple[bool, dict[str, UpstoxLevel5DepthRecord], str]:
        """Validates cross-strike skew and staleness across constituent legs.
        
        Returns:
            (is_valid, legs_map, rejection_reason)
        """
        if not tokens:
            return False, {}, "EMPTY_TOKENS_LIST"

        curr_mono = time.monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns
        legs_map: dict[str, UpstoxLevel5DepthRecord] = {}

        with self._lock:
            for token in tokens:
                depth = self._latest_depth.get(token)
                if depth is None:
                    return False, {}, f"MISSING_TOKEN_DATA_{token}"
                legs_map[token] = depth

        # Staleness check based on local monotonic ingress clock
        # GM-GATE-004 & Section 6.5
        for token, depth in legs_map.items():
            age_ms = (curr_mono - depth.ingress_monotonic_ns) / 1_000_000.0
            if age_ms > self.staleness_timeout_ms:
                return (
                    False,
                    legs_map,
                    f"STALE_LEG_DATA_{token}_AGE_{age_ms:.1f}MS_EXCEEDS_{self.staleness_timeout_ms}MS",
                )

        # Cross-strike skew calculation using authoritative exchange timestamps
        # Delta t_skew = max(t_ex) - min(t_ex)
        ex_timestamps = [d.exchange_timestamp_ms for d in legs_map.values()]
        min_ts = min(ex_timestamps)
        max_ts = max(ex_timestamps)
        skew_ms = float(max_ts - min_ts)

        if skew_ms > self.skew_threshold_ms:
            return (
                False,
                legs_map,
                "STALE_DATA_CROSS_STRIKE_SKEW_EXCEEDED",
            )

        return True, legs_map, "OK"
