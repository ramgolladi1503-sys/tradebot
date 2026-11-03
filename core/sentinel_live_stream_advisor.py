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
    STATE_PULLBACK_WAIT,
)
from core.expiry_calendar_resolver import ExpiryCalendarResolver
from core.liquidity_sweep_engine import LiquiditySweepEngine
from core.intraday_reversal_engine import (
    IntradayReversalEngine,
    ReversalDirection,
    ReversalSetupType,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.structural_alpha_gates import (
    CrossIndexMacroGate,
    ITMStrikeResolver,
    PassiveMidpointQueueModel,
    VolatilityCompressionGate,
)
from core.option_confidence_scorer import (
    OptionConfidenceScorer,
    ConfidenceEvaluation,
)
from core.sentinel_regime_router import (
    SentinelRegimeRouter,
    RegimePosteriorState,
)
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    SentinelWallState,
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
    confidence_score: int = 0
    confidence_grade: str = "GRADE_C_SUPPRESSED"
    probable_win_rate_pct: float = 0.0
    sizing_recommendation: str = "ZERO_SUPPRESS"


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

        # Decoupled Multi-Index APM Instances: Each index runs an isolated position manager & WAL
        wal_base = Path(wal_path).parent
        self.apms: dict[str, ActivePositionManager] = {
            "NIFTY": ActivePositionManager(wal_path=str(wal_base / "sentinel_apm_wal.json")),
            "SENSEX": ActivePositionManager(wal_path=str(wal_base / "sentinel_apm_wal_sensex.json")),
            "BANKNIFTY": ActivePositionManager(wal_path=str(wal_base / "sentinel_apm_wal_banknifty.json")),
        }
        # Backward compatibility reference (default to NIFTY)
        self.apm = self.apms["NIFTY"]

        for idx_key, mgr in self.apms.items():
            # If APM was in EXIT_PENDING upon boot (from crash recovery fail-closed), complete liquidation
            if mgr.state == STATE_EXIT_PENDING:
                mgr.liquidate()
            # If APM was in LIQUIDATED from a previous trade or day, reset to STANDBY for new setups
            if mgr.state == STATE_LIQUIDATED:
                mgr.state = STATE_STANDBY
                mgr._persist_wal_atomic()

        self.active_range_high = -math.inf
        self.active_range_low = math.inf
        # Dynamic Opening Range Bounds: Clean infinity initialization to strictly capture today's session
        self.or_bounds: dict[str, dict[str, float]] = {
            "NIFTY": {"high": -math.inf, "low": math.inf},
            "SENSEX": {"high": -math.inf, "low": math.inf},
            "BANKNIFTY": {"high": -math.inf, "low": math.inf},
        }
        # If launched post-09:45, seed exact Opening Range from Upstox Intraday API
        self._seed_or_bounds_from_api_if_late_boot()

        # If current time is past opening shock (09:45), trade lock is cleared
        self.trade_lock_active = (datetime.now().time() < self.opening_shock_end_time)
        self.spots: dict[str, float] = {"NIFTY": 0.0, "SENSEX": 0.0, "BANKNIFTY": 0.0}
        self.spots_ts_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}

        # Structural Alpha Invariant Gates
        self.macro_gate = CrossIndexMacroGate()
        self.vol_compression_gate = VolatilityCompressionGate()
        self.passive_midpoint_queue = PassiveMidpointQueueModel()
        self.strike_resolver = ITMStrikeResolver()

        # Strategy A & Hypothesis 2: Expiry Calendar and Liquidity Sweep Reversal Engine
        self.expiry_resolver = ExpiryCalendarResolver()
        self.sweep_engine = LiquiditySweepEngine()
        self.expiry_info = self.expiry_resolver.classify_session(datetime.now().date())

        # FEAT-SENTINEL-INTRADAY-REVERSAL-001: Decoupled Intraday Reversal Engines per index
        self.reversal_engines: dict[str, IntradayReversalEngine] = {
            "NIFTY": IntradayReversalEngine(index_name="NIFTY"),
            "SENSEX": IntradayReversalEngine(index_name="SENSEX"),
            "BANKNIFTY": IntradayReversalEngine(index_name="BANKNIFTY"),
        }
        self.reversal_engine = self.reversal_engines["NIFTY"]
        # Previous Day Reference Levels (PDH / PDL / PDC)
        self.prior_day_levels: dict[str, dict[str, float]] = {
            "NIFTY": {"pdh": 23149.80, "pdl": 22913.80, "pdc": 23146.20},
            "SENSEX": {"pdh": 74849.75, "pdl": 74169.23, "pdc": 74800.00},
            "BANKNIFTY": {"pdh": 55883.70, "pdl": 55331.10, "pdc": 55750.00},
        }

        # Multi-Factor Option Confidence Scorer
        self.confidence_scorer = OptionConfidenceScorer(min_actionable_score=60)

        # FEAT-SENTINEL-REGIME-ROUTER-001: Upstream Supervisory Regime Router
        self.regime_routers: dict[str, SentinelRegimeRouter] = {
            "NIFTY": SentinelRegimeRouter(),
            "SENSEX": SentinelRegimeRouter(),
            "BANKNIFTY": SentinelRegimeRouter(),
        }
        self.regime_router = self.regime_routers["NIFTY"]

        # FEAT-SENTINEL-WALL-OBSERVER-001: In-Memory Strike Wall Observers per index
        self.wall_observers: dict[str, SentinelWallObserver] = {
            "NIFTY": SentinelWallObserver(underlying_symbol="NIFTY"),
            "SENSEX": SentinelWallObserver(underlying_symbol="SENSEX"),
            "BANKNIFTY": SentinelWallObserver(underlying_symbol="BANKNIFTY"),
        }
        self.wall_observer = self.wall_observers["NIFTY"]

        self.alerts_history: list[AdvisoryAlert] = []
        self._lock = threading.Lock()
        self._last_alert_time = 0.0
        self._last_wall_persist_time = 0.0
        self.session_gear = "GEAR_1_RANGE"  # "GEAR_1_RANGE" or "GEAR_2_TREND"

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
        idx_key = None
        if "Nifty 50" in token:
            idx_key = "NIFTY"
        elif "SENSEX" in token:
            idx_key = "SENSEX"
        elif "Nifty Bank" in token:
            idx_key = "BANKNIFTY"

        if idx_key is not None:
            self._update_spot(idx_key, tick.ltp, tick.exchange_timestamp_ms)
            # Update upstream regime router ring buffer and state
            router = self.regime_routers.get(idx_key)
            if router is not None:
                now_dt = datetime.fromtimestamp(tick.exchange_timestamp_ms / 1000.0) if tick.exchange_timestamp_ms > 0 else datetime.now()
                router.on_bar_close(
                    bar_close=tick.ltp,
                    bar_volume=float(tick.volume),
                    cvd_delta=0.0,
                    timestamp_ms=tick.exchange_timestamp_ms,
                    bar_time=now_dt.time(),
                )

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

    def _seed_or_bounds_from_api_if_late_boot(self) -> None:
        """Seeds Opening Range (09:15-09:45) from Upstox Intraday API if process starts/restarts post-09:45."""
        now_t = datetime.now().time()
        if now_t <= self.opening_shock_end_time:
            return

        import os, requests
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
        if not token:
            return

        headers = {"accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
        indices = [
            ("NIFTY", "NSE_INDEX%7CNifty%2050"),
            ("BANKNIFTY", "NSE_INDEX%7CNifty%20Bank"),
            ("SENSEX", "BSE_INDEX%7CSENSEX"),
        ]
        for idx, sym in indices:
            try:
                url = f"https://api.upstox.com/v2/historical-candle/intraday/{sym}/1minute"
                r = requests.get(url, headers=headers, timeout=4)
                if r.status_code == 200:
                    candles = r.json().get("data", {}).get("candles", [])
                    or_candles = [c for c in candles if "09:15:00" <= c[0][11:19] <= "09:45:00"]
                    if or_candles:
                        h = float(max(c[2] for c in or_candles))
                        l = float(min(c[3] for c in or_candles))
                        self.or_bounds[idx]["high"] = h
                        self.or_bounds[idx]["low"] = l
                        if idx == "NIFTY":
                            self.active_range_high = h
                            self.active_range_low = l
                        if self.enable_stdout:
                            print(f"📥 [OR RECOVERY] {idx}: Seeded Opening Range from Upstox API -> High={h:.2f}, Low={l:.2f} (Range={h-l:.2f} pts)")
            except Exception as e:
                logger.warning(f"Failed to fetch OR candles for {idx}: {e}")

    def on_stream_status(self, status: Any) -> None:
        pass

    def _update_spot(self, index_name: str, spot: float, ts_ms: int) -> None:
        if spot <= 0:
            return
        wall_obs = self.wall_observers.get(index_name)
        if wall_obs is not None:
            wall_obs.on_spot_tick(spot_price=spot, timestamp_ms=ts_ms)
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
            target_pts = 60.0
            sl_pts = 40.0
            eff_atr_15m = 100.0
            eff_atr_60m = 140.0
        elif "BANKNIFTY" in sym:
            index_name = "BANKNIFTY"
            strike_interval = 100.0
            target_pts = 50.0
            sl_pts = 35.0
            eff_atr_15m = 45.0
            eff_atr_60m = 65.0
        else:
            index_name = "NIFTY"
            strike_interval = 50.0
            target_pts = 15.0
            sl_pts = 12.0
            eff_atr_15m = 12.0
            eff_atr_60m = 16.0

        # Feed option depth tick to SentinelWallObserver
        wall_obs = self.wall_observers.get(index_name)
        if wall_obs is not None:
            bid_d = float(depth.bid_q1 + depth.bid_q2 + depth.bid_q3 + depth.bid_q4 + depth.bid_q5)
            ask_d = float(depth.ask_q1 + depth.ask_q2 + depth.ask_q3 + depth.ask_q4 + depth.ask_q5)
            wall_obs.on_option_tick(
                symbol=depth.symbol,
                ltp=depth.ltp or depth.bid_p1,
                volume=float(depth.volume),
                oi=float(depth.open_interest),
                bid_depth=bid_d,
                ask_depth=ask_d,
                timestamp_ms=depth.exchange_timestamp_ms,
            )
            # Throttle wall state snapshot persistence to disk (e.g. once every 2 seconds)
            if now_ts - self._last_wall_persist_time >= 2.0:
                self._last_wall_persist_time = now_ts
                try:
                    fn = f"runtime/sentinel_wall_state_{index_name.lower()}.json"
                    wall_obs.persist_state_atomic(fn)
                except Exception:
                    pass

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

        # Setup Detection (PR #968 / PR #980 / FEAT-STRUCTURAL-ALPHA-003 / FEAT-LIQUIDITY-SWEEP-EXPIRY-004)
        is_ce = "CE" in sym
        is_pe = "PE" in sym
        atm_strike = round(spot / strike_interval) * strike_interval

        trigger_active = False
        setup_reason = ""
        required_option_type = None

        # -------------------------------------------------------------
        # Mode 1: Strategy A & Hypothesis 2 - Prior-Day Liquidity Sweep Reversal
        # Evaluates 09:30 - 12:00. Strictly gated to GEAR_1_RANGE (Chop/Expiry Pinning).
        # Fading breakouts in Gear 2 Trend is strictly suppressed fail-closed.
        # -------------------------------------------------------------
        pd_bounds = self.prior_day_levels.get(index_name, {"pdh": 0.0, "pdl": 0.0})
        pdh = pd_bounds.get("pdh", 0.0)
        pdl = pd_bounds.get("pdl", 0.0)
        is_exp = (self.expiry_info.active_expiry_index == index_name)

        sweep_sig = None
        # Regime Gate: Only allow sweep reversal when market is in Gear 1 Chop or Expiry Straddle Pinning
        if self.session_gear == "GEAR_1_RANGE" or is_exp:
            sweep_sig = self.sweep_engine.evaluate_bar(
            index_name=index_name,
            bar_open=spot,
            bar_high=spot,
            bar_low=spot,
            bar_close=spot,
            pdh=pdh,
            pdl=pdl,
            timestamp_ms=depth.exchange_timestamp_ms,
            is_expiry_session=is_exp,
            bar_time=now_time,
        )

        if sweep_sig is not None:
            trigger_active = True
            required_option_type = sweep_sig.direction
            setup_reason = f"[{sweep_sig.sweep_type}] {sweep_sig.setup_reason}"
            target_pts = sweep_sig.target_pts
            sl_pts = sweep_sig.sl_pts

        # -------------------------------------------------------------
        # Mode 1.5: FEAT-SENTINEL-INTRADAY-REVERSAL-001 - Intraday Reversal Engine
        # Evaluates FAH (Failure-at-High) and FAL (Failure-at-Low) extreme snapbacks to VWAP
        # -------------------------------------------------------------
        elif (rev_engine := self.reversal_engines.get(index_name)) is not None and (
            rev_sig := rev_engine.evaluate_bar(
                bar_open=spot,
                bar_high=spot,
                bar_low=spot,
                bar_close=spot,
                volume=10000,
                timestamp_ms=depth.exchange_timestamp_ms,
            )
        ) is not None:
            trigger_active = True
            required_option_type = rev_sig.direction.value
            setup_reason = f"[{rev_sig.setup_type.value}] {rev_sig.setup_reason}"
            target_pts = rev_sig.reward_pts
            sl_pts = rev_sig.risk_pts

        # -------------------------------------------------------------
        # Mode 2: Existing Opening Range Breakout (ORB) Engine
        # Evaluates clean trend expansion when no sweep or reversal trap is active
        # -------------------------------------------------------------
        elif or_high > -math.inf and spot > or_high:
            trigger_active = True
            required_option_type = "CE"
            setup_reason = f"Breakout > {or_high:.1f}"
        elif or_low < math.inf and spot < or_low:
            trigger_active = True
            required_option_type = "PE"
            setup_reason = f"Breakdown < {or_low:.1f}"

        # Compute Multi-Factor Confidence Score
        conf_eval = None
        if trigger_active and ((required_option_type == "CE" and is_ce) or (required_option_type == "PE" and is_pe)):
            depth_bids = depth.bid_q1 + depth.bid_q2 + depth.bid_q3 + depth.bid_q4 + depth.bid_q5
            depth_asks = depth.ask_q1 + depth.ask_q2 + depth.ask_q3 + depth.ask_q4 + depth.ask_q5
            displacement = (spot - or_high) if required_option_type == "CE" else (spot - or_low)
            
            # Strike matching check for ITM
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

            macro_ok, macro_reason = self.macro_gate.evaluate_alignment(
                target_index=index_name,
                setup_direction=required_option_type,
                spots=self.spots,
                or_bounds=self.or_bounds,
            )

            conf_eval = self.confidence_scorer.evaluate_confidence(
                macro_aligned=macro_ok,
                macro_reason=macro_reason,
                writer_alignment="BEARS_IN_CONTROL" if required_option_type == "PE" else "BULLS_IN_CONTROL",
                writer_conviction=0.75,
                setup_direction=required_option_type,
                depth_bid_q_sum=depth_bids,
                depth_ask_q_sum=depth_asks,
                displacement_pts=displacement,
                eff_atr=eff_atr_15m,
                is_target_itm=is_target_strike,
                spread_ratio=spread_ratio,
                is_expiry_session=is_exp,
            )

            vol_ok, vol_reason, _ = self.vol_compression_gate.evaluate_compression(
                atr_15m=eff_atr_15m,
                atr_60m=eff_atr_60m,
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
            elif not conf_eval.is_actionable:
                status_flag = "VETO_LOW_CONFIDENCE"
                advisory = f"🚨 [LOW CONVICTION: {conf_eval.total_score}/100 {conf_eval.grade}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
            else:
                status_flag = "SIGNAL_TRIGGERED"
                advisory = (
                    f"🎯 [BUY {depth.symbol}] @ {setup_reason} | "
                    f"Conviction: {conf_eval.total_score}/100 ({conf_eval.grade}, WinRate ~{conf_eval.probable_win_rate_pct:.0f}%, {conf_eval.sizing_recommendation}) | "
                    f"Target: +{target_pts:.1f}pts | Vol-SL: -{sl_pts:.1f}pts"
                )

                # Gate 4: Passive Midpoint Queue Execution Price
                fill_price, savings, fill_mode = self.passive_midpoint_queue.calculate_entry_fill(
                    bid=bid,
                    ask=ask,
                    passive_fill_enabled=True,
                )

                with self._lock:
                    idx_apm = self.apms.get(index_name, self.apm)
                    # Allow entry if APM is in STANDBY, LIQUIDATED, or PULLBACK_WAIT
                    if is_target_strike and idx_apm.state in {STATE_STANDBY, STATE_LIQUIDATED, STATE_PULLBACK_WAIT}:
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
                        pos_id = f"TRADE_{index_name}_{now_time.strftime('%H%M%S')}_{required_option_type}"
                        entered = idx_apm.arm_and_enter(
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
                                f"\n🚀 [APM IN_FLIGHT ENTRY ({index_name}) - {itm_res.moneyness}] {pos_id} | {depth.symbol} @ {spot:.1f} | "
                                f"Conviction: {conf_eval.total_score}/100 ({conf_eval.grade}) | "
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
            idx_apm = self.apms.get(index_name, self.apm)
            if idx_apm.state in {STATE_IN_FLIGHT, "TRAIL_LOCK", "EXIT_PENDING"} and idx_apm.payload:
                if idx_apm.payload.opt_symbol == depth.symbol:
                    idx_apm.evaluate_tick(
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
            confidence_score=conf_eval.total_score if conf_eval else 0,
            confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
            probable_win_rate_pct=conf_eval.probable_win_rate_pct if conf_eval else 0.0,
            sizing_recommendation=conf_eval.sizing_recommendation if conf_eval else "ZERO_SUPPRESS",
        )

        with self._lock:
            self.alerts_history.append(alert)
            self._last_alert_time = now_ts

        if self.enable_stdout:
            print(
                f"🛰️ [{alert.wall_time_str}] {index_name}: {spot:.1f} | {depth.symbol} LTP: {ltp:.2f} | "
                f"Conviction: {alert.confidence_score}/100 ({alert.confidence_grade}) | "
                f"Spread: {spread:.2f} ({spread_ratio * 100:.1f}%) | "
                f"Status: {status_flag} | Advisory: {advisory}"
            )
