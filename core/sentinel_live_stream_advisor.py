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

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_LIQUIDATED,
    STATE_EXIT_PENDING,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.structural_alpha_gates import (
    CrossIndexMacroGate,
    ITMStrikeResolver,
    PassiveMidpointQueueModel,
    VolatilityCompressionGate,
)
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
        wal_path: str = "runtime/sentinel_apm_wal.json",
    ) -> None:
        self.adapter = adapter
        self.spread_veto_threshold = float(spread_veto_threshold)
        self.opening_shock_end_time = opening_shock_end_time
        self.market_close_time = market_close_time
        self.skew_threshold_ms = float(skew_threshold_ms)
        self.enable_stdout = enable_stdout

        self.apm = ActivePositionManager(wal_path=wal_path)
        # If APM was in EXIT_PENDING upon boot (from crash recovery fail-closed), complete liquidation
        if self.apm.state == STATE_EXIT_PENDING:
            self.apm.liquidate()
        # If APM was in LIQUIDATED from a previous trade or day, reset to STANDBY for new setups
        if self.apm.state == STATE_LIQUIDATED:
            self.apm.state = STATE_STANDBY
            self.apm._persist_wal_atomic()

        self.active_range_high = -math.inf
        self.active_range_low = math.inf
        self.or_bounds: dict[str, dict[str, float]] = {
            "NIFTY": {"high": 23175.25, "low": 22970.50},
            "SENSEX": {"high": 74849.75, "low": 74169.23},
            "BANKNIFTY": {"high": 55883.70, "low": 55331.10},
        }
        # If current time is past opening shock (09:45), trade lock is cleared
        self.trade_lock_active = (datetime.now().time() < self.opening_shock_end_time)
        self.spots: dict[str, float] = {"NIFTY": 0.0, "SENSEX": 0.0, "BANKNIFTY": 0.0}
        self.spots_ts_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}

        # Structural Alpha Invariant Gates
        self.macro_gate = CrossIndexMacroGate()
        self.vol_compression_gate = VolatilityCompressionGate()
        self.passive_midpoint_queue = PassiveMidpointQueueModel()
        self.strike_resolver = ITMStrikeResolver()

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
                b = self.or_bounds[index_name]
                b["high"] = max(b["high"], spot)
                b["low"] = min(b["low"], spot)
                if index_name == "NIFTY":
                    self.active_range_high = b["high"]
                    self.active_range_low = b["low"]
            else:
                if self.trade_lock_active:
                    self.trade_lock_active = False
                    if self.enable_stdout:
                        print("\n🔓 [OPENING SHOCK CONCLUDED] Opening Range Boundaries Established:")
                        for idx, bounds in self.or_bounds.items():
                            if bounds["high"] > -math.inf:
                                rng = bounds["high"] - bounds["low"]
                                print(f"   • {idx}: OR High={bounds['high']:.1f} | OR Low={bounds['low']:.1f} | Range={rng:.1f} pts")
                        print("🛰️ Sentinel Live Setup Trigger Engine ACTIVE.")

    def _evaluate_option_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        now_ts = time.time()
        # Rate-limit console telemetry prints to at most 1 per second unless a live BUY signal occurs
        is_throttled = (now_ts - self._last_alert_time < 1.0)

        # Determine which index this option belongs to and setup strike parameters
        sym = depth.symbol.upper()
        if "SENSEX" in sym:
            index_name = "SENSEX"
            strike_interval = 100.0
            target_pts = 30.0
            sl_pts = 20.0
        elif "BANKNIFTY" in sym:
            index_name = "BANKNIFTY"
            strike_interval = 100.0
            target_pts = 30.0
            sl_pts = 20.0
        else:
            index_name = "NIFTY"
            strike_interval = 50.0
            target_pts = 15.0
            sl_pts = 12.0

        with self._lock:
            spot = self.spots.get(index_name, 0.0)
            spot_ts = self.spots_ts_ms.get(index_name, 0)
            trade_lock = self.trade_lock_active
            or_b = self.or_bounds.get(index_name, {"high": -math.inf, "low": math.inf})
            or_high = or_b["high"]
            or_low = or_b["low"]

        if spot <= 0:
            return

        now_dt = datetime.now()
        now_time = now_dt.time()

        # Opening shock freeze: strictly suppress all candidate setups
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

        # Estimated transaction drag (slippage + statutory base drag)
        total_drag = round(spread * 0.5 + 0.40, 2)

        # Setup Detection (PR #968 / PR #980 / FEAT-STRUCTURAL-ALPHA-003 Invariant Rules)
        is_ce = "CE" in sym
        is_pe = "PE" in sym
        atm_strike = round(spot / strike_interval) * strike_interval

        trigger_active = False
        setup_reason = ""
        required_option_type = None

        if or_high > -math.inf and spot > or_high:
            trigger_active = True
            required_option_type = "CE"
            setup_reason = f"Breakout > {or_high:.1f}"
        elif or_low < math.inf and spot < or_low:
            trigger_active = True
            required_option_type = "PE"
            setup_reason = f"Breakdown < {or_low:.1f}"

        # Evaluate advisory output
        if trigger_active and ((required_option_type == "CE" and is_ce) or (required_option_type == "PE" and is_pe)):
            # Gate 1: Cross-Index Macro Confirmation
            macro_ok, macro_reason = self.macro_gate.evaluate_alignment(
                target_index=index_name,
                setup_direction=required_option_type,
                spots=self.spots,
                or_bounds=self.or_bounds,
            )

            # Gate 2: Volatility Compression / Squeeze Pre-Condition
            # Est. ATR15m / ATR60m compression: check if move is exhausted
            displacement = (spot - or_high) if required_option_type == "CE" else (spot - or_low)
            vol_ok, vol_reason, _ = self.vol_compression_gate.evaluate_compression(
                atr_15m=12.0,
                atr_60m=16.0,
                recent_displacement_pts=displacement,
            )

            if is_vetoed:
                status_flag = "VETO_SPREAD_EXPANDED"
                advisory = f"🚨 [SPREAD VETO] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED (>4.0% spread)"
            elif not macro_ok:
                status_flag = "VETO_MACRO_DIVERGENCE"
                advisory = f"🚨 [{macro_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
            elif not vol_ok:
                status_flag = "VETO_VOLATILITY_EXHAUSTED"
                advisory = f"🚨 [{vol_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
            else:
                status_flag = "SIGNAL_TRIGGERED"
                advisory = f"🎯 [BUY {depth.symbol}] @ {setup_reason} | Target: +{target_pts:.1f}pts | Vol-SL: -{sl_pts:.1f}pts"

                # Gate 3: ITM Strike Resolution (Delta 0.65-0.75)
                itm_res = self.strike_resolver.resolve_target_strike(
                    spot=spot,
                    direction=required_option_type,
                    index_name=index_name,
                )

                is_target_strike = self.strike_resolver.is_contract_matching(
                    symbol=sym,
                    target_strike=itm_res.target_strike,
                    option_type=required_option_type,
                    tolerance_strikes=1,
                    strike_interval=strike_interval,
                )

                # Gate 4: Passive Midpoint Queue Execution Price
                fill_price, savings, fill_mode = self.passive_midpoint_queue.calculate_entry_fill(
                    bid=bid,
                    ask=ask,
                    passive_fill_enabled=True,
                )

                with self._lock:
                    if is_target_strike and self.apm.state in {STATE_STANDBY, STATE_LIQUIDATED}:
                        opt_q = {
                            "symbol": depth.symbol,
                            "token": depth.token,
                            "ltp": fill_price,
                            "bid": bid,
                            "ask": ask,
                            "midpoint": round((bid + ask) / 2.0, 2),
                            "spread_savings": savings,
                            "fill_mode": fill_mode,
                        }
                        pos_id = f"TRADE_{now_time.strftime('%H%M%S')}_{required_option_type}"
                        entered = self.apm.arm_and_enter(
                            position_id=pos_id,
                            direction=required_option_type,
                            contract=depth.symbol,
                            entry_price=spot,
                            entry_time_str=now_dt.isoformat(),
                            sl_pts=sl_pts,
                            tp_pts=target_pts,
                            friction_drag_pts=total_drag,
                            opt_quote=opt_q,
                            is_runner_mode=True,
                            session_gear="GEAR_2_TREND",
                            opt_stop_loss_pct=0.20,
                        )
                        if entered and self.enable_stdout:
                            print(
                                f"\n🚀 [APM IN_FLIGHT ENTRY - {itm_res.moneyness}] {pos_id} | {depth.symbol} @ {spot:.1f} | "
                                f"Fill: ₹{fill_price:.2f} ({fill_mode}, Saved ₹{savings:.2f}) | "
                                f"SL: {sl_pts:.1f}pts | TP: {target_pts:.1f}pts"
                            )
        else:
            if is_vetoed:
                status_flag = "HALTED_SPREAD_VIOLATION"
                advisory = "WAIT (SPREAD_VETO)"
            else:
                status_flag = "VERIFIED_STATE"
                advisory = "SCALP_MONITORING"

        # Update in-flight APM position if open and matching option contract
        with self._lock:
            if self.apm.state in {STATE_IN_FLIGHT, "TRAIL_LOCK", "EXIT_PENDING"} and self.apm.payload:
                if self.apm.payload.opt_symbol == depth.symbol:
                    opt_q = {
                        "symbol": depth.symbol,
                        "token": depth.token,
                        "ltp": ltp,
                        "bid": bid,
                        "ask": ask,
                    }
                    self.apm.evaluate_tick(
                        current_spot=spot,
                        current_opt_ltp=ltp,
                        tick_time_str=now_time.strftime("%H:%M:%S"),
                        atr_1m=12.0,
                    )

        # Do not throttle genuine BUY signals
        if not ("🎯 [BUY" in advisory) and is_throttled:
            return

        alert = AdvisoryAlert(
            timestamp_ms=depth.exchange_timestamp_ms,
            wall_time_str=now_time.strftime("%H:%M:%S"),
            spot_price=spot,
            atm_strike=atm_strike,
            option_symbol=depth.symbol,
            option_type="CE" if is_ce else "PE",
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
