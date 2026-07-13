from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.time_utils import IST_TZ

logger = logging.getLogger(__name__)


class SessionVwapAccumulator:
    """
    Authoritative state owner for Volume Weighted Average Price (VWAP) calculation.
    Maintains intraday VWAP accumulation per trading session.
    """

    def __init__(self):
        self._session_date: str | None = None
        self._cumulative_price_volume: float = 0.0
        self._cumulative_volume: float = 0.0
        self._sample_count: int = 0
        self._last_ts_epoch: float | None = None
        self._last_vwap: float | None = None
        self._last_cumulative_volume: float = 0.0

    def _get_date_str(self, ts_epoch: float) -> str:
        """Convert UTC epoch to IST date string."""
        return datetime.fromtimestamp(ts_epoch, tz=timezone.utc).astimezone(IST_TZ).strftime("%Y-%m-%d")

    def _check_and_reset_session(self, ts_epoch: float):
        current_date = self._get_date_str(ts_epoch)
        if self._session_date is None or self._session_date != current_date:
            self.reset_session(current_date)

    def reset_session(self, session_date: str | None = None):
        """Reset accumulator state, typically at the start of a new trading session."""
        self._session_date = session_date
        self._cumulative_price_volume = 0.0
        self._cumulative_volume = 0.0
        self._sample_count = 0
        self._last_ts_epoch = None
        self._last_vwap = None
        self._last_cumulative_volume = 0.0
        if session_date is not None:
            logger.info(f"VWAP accumulator session reset for date: {session_date}")
        else:
            logger.info("VWAP accumulator session reset (cleared)")



    def observe_tick(self, ts_epoch: float, ltp: float, cumulative_volume: float):
        """
        Observe a tick to accumulate VWAP using cumulative session volume.
        Guarantees:
        - Out-of-order ticks are rejected
        - Negative or zero delta volume produces no VWAP change
        """
        if cumulative_volume < 0:
            return
        if self._last_ts_epoch is not None and ts_epoch < self._last_ts_epoch:
            logger.warning(f"VWAP accumulator rejecting out-of-order tick ts: {ts_epoch} < {self._last_ts_epoch}")
            return

        self._check_and_reset_session(ts_epoch)
        self._last_ts_epoch = ts_epoch

        # Calculate incremental volume
        incremental = cumulative_volume - self._last_cumulative_volume
        if incremental < 0:
            # Maybe session reset or bad data, but we assume it's bad data and ignore delta
            incremental = 0.0

        if incremental > 0:
            typical_price = ltp
            self._cumulative_price_volume += (typical_price * incremental)
            self._cumulative_volume += incremental
            self._last_vwap = self._cumulative_price_volume / self._cumulative_volume

        self._last_cumulative_volume = cumulative_volume
        self._sample_count += 1

    def get_snapshot(self, source: str = "LIVE_INCREMENTAL") -> dict[str, Any]:
        """Expose an immutable snapshot of the current VWAP state."""
        return {
            "value": self._last_vwap,
            "source": source if self._last_vwap is not None else "UNAVAILABLE",
            "as_of": self._last_ts_epoch,
            "session_date": self._session_date,
            "sample_count": self._sample_count,
            "cumulative_volume": self._cumulative_volume
        }

from collections import defaultdict

_GLOBAL_VWAP_ACCUMULATORS: dict[int, SessionVwapAccumulator] = defaultdict(SessionVwapAccumulator)

def get_global_vwap_accumulator(token: int) -> SessionVwapAccumulator:
    return _GLOBAL_VWAP_ACCUMULATORS[token]



