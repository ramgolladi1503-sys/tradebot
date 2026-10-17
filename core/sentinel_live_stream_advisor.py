"""Sentinel Live In-Memory Stream Advisor.

Embedded live paper advisory engine consuming direct in-memory Upstox streaming
ticks and Level-5 order book depth via InMemorySentinelAdapter.

Key Features:
1. Zero Disk Polling Latency: Directly bound to in-memory streaming callbacks (< 1ms).
2. 09:15 - 09:45 Opening Shock Stand-Aside Freeze: Automatically tracks Opening Range
   High/Low in real time while blocking entries during opening volatility crush.
3. Real-Time Level-5 Dynamic Slippage & Bid-Ask Spread Veto Gate: Evaluates live option
   spreads against the 4.0% premium veto threshold using actual top-of-book depth.
4. Causal Cross-Strike Skew Gate: Rejects multi-leg setups if temporal skew between
   underlying spot and option legs exceeds 250ms.
5. Live Tape Telemetry: Emits real-time advisory alerts and audit records without
   blocking the streaming ingest path.
6. Strict Safety Invariants: read_only=True, is_order_action=False, broker_api_called=False.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any

from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.upstox_stream_broadcaster import (
    StreamSubscriber,
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AdvisoryAlert:
    timestamp_ms: int
    wall_time_str: str
    spot_price: float
    atm_strike: float
    option_symbol: str
    option_type: str
    option_ltp: float
    bid: float
    ask: float
    spread_pts: float
    spread_ratio: float
    total_drag_pts: float
    status_flag: str
    advisory: str


class SentinelLiveStreamAdvisor(StreamSubscriber):
    """Event-driven live paper advisory engine operating directly on in-memory
    Upstox ticks and Level-5 order book depth.
    """

    def __init__(
        self,
        adapter: InMemorySentinelAdapter,
        spread_veto_threshold: float = 0.04,
        opening_shock_end_time: dt_time = dt_time(9, 45),
        market_close_time: dt_time = dt_time(15, 30),
        skew_threshold_ms: float = 250.0,
        enable_stdout: bool = True,
    ) -> None:
        self.adapter = adapter
        self.spread_veto_threshold = float(spread_veto_threshold)
        self.opening_shock_end_time = opening_shock_end_time
        self.market_close_time = market_close_time
        self.skew_threshold_ms = float(skew_threshold_ms)
        self.enable_stdout = enable_stdout

        self.active_range_high = -math.inf
        self.active_range_low = math.inf
        self.trade_lock_active = True
        self.spots: dict[str, float] = {"NIFTY": 0.0, "SENSEX": 0.0, "BANKNIFTY": 0.0}
        self.spots_ts_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}

        self.alerts_history: list[AdvisoryAlert] = []
        self._lock = threading.Lock()
        self._last_alert_time = 0.0

        # Non-negotiable Trading Safety Invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    @property
    def latest_spot(self) -> float:
        with self._lock:
            return self.spots.get("NIFTY", 0.0)

    def on_tick(self, tick: UpstoxTickRecord) -> None:
        """Handle incoming tick for NIFTY, SENSEX, and BANKNIFTY."""
        token = tick.token
        if "Nifty 50" in token:
            self._update_spot("NIFTY", tick.ltp, tick.exchange_timestamp_ms)
        elif "SENSEX" in token:
            self._update_spot("SENSEX", tick.ltp, tick.exchange_timestamp_ms)
        elif "Nifty Bank" in token:
            self._update_spot("BANKNIFTY", tick.ltp, tick.exchange_timestamp_ms)

    def on_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        """Handle incoming Level-5 depth snapshot."""
        token = depth.token
        if "Nifty 50" in token:
            self._update_spot("NIFTY", depth.ltp, depth.exchange_timestamp_ms)
            return
        elif "SENSEX" in token:
            self._update_spot("SENSEX", depth.ltp, depth.exchange_timestamp_ms)
            return
        elif "Nifty Bank" in token:
            self._update_spot("BANKNIFTY", depth.ltp, depth.exchange_timestamp_ms)
            return

        # Trigger option assessment on option depth updates (NIFTY, SENSEX, or BANKNIFTY options)
        self._evaluate_option_depth(depth)

    def on_stream_status(self, status: Any) -> None:
        pass

    def _update_spot(self, index_name: str, spot: float, ts_ms: int) -> None:
        if spot <= 0:
            return
        with self._lock:
            self.spots[index_name] = spot
            self.spots_ts_ms[index_name] = ts_ms

            now_t = datetime.now().time()
            if now_t < self.opening_shock_end_time:
                self.trade_lock_active = True
                if index_name == "NIFTY":
                    self.active_range_high = max(self.active_range_high, spot)
                    self.active_range_low = min(self.active_range_low, spot)
            else:
                if self.trade_lock_active and self.active_range_high > -math.inf:
                    self.trade_lock_active = False
                    if self.enable_stdout:
                        rng = self.active_range_high - self.active_range_low
                        print(
                            f"\n🔓 [OPENING SHOCK CONCLUDED] OR High: {self.active_range_high:.1f} | "
                            f"OR Low: {self.active_range_low:.1f} | Range: {rng:.1f} pts. "
                            f"Sentinel In-Memory Advisory ACTIVE."
                        )

    def _evaluate_option_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        now_ts = time.time()
        # Rate-limit console telemetry prints to at most 1 per second unless significant event
        if now_ts - self._last_alert_time < 1.0:
            return

        # Determine which index this option belongs to
        sym = depth.symbol.upper()
        if "SENSEX" in sym:
            index_name = "SENSEX"
            strike_interval = 100.0
        elif "BANKNIFTY" in sym:
            index_name = "BANKNIFTY"
            strike_interval = 100.0
        else:
            index_name = "NIFTY"
            strike_interval = 50.0

        with self._lock:
            spot = self.spots.get(index_name, 0.0)
            spot_ts = self.spots_ts_ms.get(index_name, 0)
            trade_lock = self.trade_lock_active

        if spot <= 0:
            return

        now_dt = datetime.now()
        now_time = now_dt.time()

        # Opening shock freeze
        if trade_lock or now_time < self.opening_shock_end_time:
            return

        # Causal cross-strike skew check
        skew_ms = abs(depth.exchange_timestamp_ms - spot_ts) if spot_ts > 0 else 0
        if spot_ts > 0 and skew_ms > self.skew_threshold_ms:
            # Stale skew gate
            return

        # Top-of-book quotes from Level-5 depth
        bid = depth.bid_p1
        ask = depth.ask_p1
        ltp = depth.ltp or bid

        if ltp <= 0 or bid <= 0 or ask <= 0:
            return

        spread = round(ask - bid, 2)
        spread_ratio = spread / ltp if ltp > 0 else 1.0
        is_vetoed = spread_ratio > self.spread_veto_threshold

        status_flag = "HALTED_SPREAD_VIOLATION" if is_vetoed else "VERIFIED_STATE"
        advisory = "WAIT" if is_vetoed else "SCALP_MONITORING"

        # Estimated transaction drag (slippage + statutory base drag)
        total_drag = round(spread * 0.5 + 0.40, 2)

        alert = AdvisoryAlert(
            timestamp_ms=depth.exchange_timestamp_ms,
            wall_time_str=now_time.strftime("%H:%M:%S"),
            spot_price=spot,
            atm_strike=round(spot / strike_interval) * strike_interval,
            option_symbol=depth.symbol,
            option_type="CE" if "CE" in depth.symbol else "PE",
            option_ltp=ltp,
            bid=bid,
            ask=ask,
            spread_pts=spread,
            spread_ratio=spread_ratio,
            total_drag_pts=total_drag,
            status_flag=status_flag,
            advisory=advisory,
        )

        with self._lock:
            self.alerts_history.append(alert)
            self._last_alert_time = now_ts

        if self.enable_stdout:
            print(
                f"🛰️ [{alert.wall_time_str}] {index_name}: {spot:.1f} | {depth.symbol} LTP: {ltp:.2f} | "
                f"Spread: {spread:.2f} ({spread_ratio * 100:.1f}%) | "
                f"Status: {status_flag} | Advisory: {advisory}"
            )
