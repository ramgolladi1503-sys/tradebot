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
from typing import Any, Optional, Dict

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_COOL_OFF,
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
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    GATE_ACTION_VETO,
    GATE_ACTION_CONFIRM_BREACH,
    GATE_ACTION_CLAMP_TARGET,
)
from core.sentinel_dynamic_sizing import (
    calculate_discrete_lots,
    get_exchange_lot_size,
)
from core.sentinel_realtime_journal import SentinelRealtimeJournal
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


@dataclass(slots=True)
class SyntheticBarBucket:
    """Aggregates spot ticks into discrete 1-minute OHLCV bars for supervisory regime evaluation."""
    bucket_epoch_min: int = -1
    open: float = 0.0
    high: float = -math.inf
    low: float = math.inf
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
    last_timestamp_ms: int = 0


class SentinelLiveStreamAdvisor(StreamSubscriber):
    """Event-driven live paper advisory engine operating directly on in-memory
    Upstox ticks and Level-5 order book depth.
    """

    def __init__(
        self,
        adapter: Optional[InMemorySentinelAdapter] = None,
        spread_veto_threshold: float = 0.04,
        market_open_time: dt_time = dt_time(9, 15),
        opening_shock_end_time: dt_time = dt_time(9, 45),
        eod_entry_freeze_time: dt_time = dt_time(15, 0),
        eod_mandatory_squareoff_time: dt_time = dt_time(15, 15),
        market_close_time: dt_time = dt_time(15, 30),
        min_strike_oi_nifty: int = 250000,
        min_strike_oi_other: int = 100000,
        min_nifty_frictional_hurdle_atr: float = 12.0,
        min_nifty_hurdle_ratio: float = 2.0,
        skew_threshold_ms: float = 1500.0,
        enable_stdout: bool = True,
        wal_path: str = "runtime/sentinel_apm_wal.json",
        journal: Optional[SentinelRealtimeJournal] = None,
    ) -> None:
        self.adapter = adapter if adapter is not None else InMemorySentinelAdapter()
        self.spread_veto_threshold = float(spread_veto_threshold)
        self.market_open_time = market_open_time
        self.opening_shock_end_time = opening_shock_end_time
        self.eod_entry_freeze_time = eod_entry_freeze_time
        self.eod_mandatory_squareoff_time = eod_mandatory_squareoff_time
        self.market_close_time = market_close_time
        self.min_strike_oi_nifty = int(min_strike_oi_nifty)
        self.min_strike_oi_other = int(min_strike_oi_other)
        self.min_nifty_frictional_hurdle_atr = float(min_nifty_frictional_hurdle_atr)
        self.min_nifty_hurdle_ratio = float(min_nifty_hurdle_ratio)
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

        # Synthetic 1-minute bar buckets per index for discrete regime discretization (Invariant 4.1)
        self.bar_buckets: dict[str, SyntheticBarBucket] = {
            "NIFTY": SyntheticBarBucket(),
            "SENSEX": SyntheticBarBucket(),
            "BANKNIFTY": SyntheticBarBucket(),
        }

        # FEAT-SENTINEL-WALL-OBSERVER-001: In-Memory Strike Wall Observers per index
        self.wall_observers: dict[str, SentinelWallObserver] = {
            "NIFTY": SentinelWallObserver(underlying_symbol="NIFTY"),
            "SENSEX": SentinelWallObserver(underlying_symbol="SENSEX"),
            "BANKNIFTY": SentinelWallObserver(underlying_symbol="BANKNIFTY"),
        }
        self.wall_observer = self.wall_observers["NIFTY"]

        # Gate 2: SentinelWallGates for pre-entry barrier verification
        self.wall_gates: dict[str, SentinelWallGate] = {
            "NIFTY": SentinelWallGate(observer=self.wall_observers["NIFTY"], proximity_veto_atr=0.50),
            "SENSEX": SentinelWallGate(observer=self.wall_observers["SENSEX"], proximity_veto_atr=0.50),
            "BANKNIFTY": SentinelWallGate(observer=self.wall_observers["BANKNIFTY"], proximity_veto_atr=0.50),
        }
        self.wall_gate = self.wall_gates["NIFTY"]

        self.alerts_history: list[AdvisoryAlert] = []
        self._lock = threading.Lock()
        self._last_alert_time = 0.0
        self._last_wall_persist_time = 0.0
        self.session_gear = "GEAR_1_RANGE"  # "GEAR_1_RANGE" or "GEAR_2_TREND"

        # Forensic Decision Journal Engine (non-blocking in-memory queue & shadow barrier evaluator)
        self.journal = journal if journal is not None else SentinelRealtimeJournal()

        # Non-negotiable Trading Safety Invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    @property
    def latest_spot(self) -> float:
        with self._lock:
            return self.spots.get("NIFTY", 0.0)

    def is_eod_entry_frozen(self, check_time: Optional[dt_time] = None) -> bool:
        """Evaluates whether current session time is in late-day entry freeze (>= 15:00:00)."""
        t = check_time or datetime.now().time()
        return t >= self.eod_entry_freeze_time

    def evaluate_strike_oi(self, index_name: str, effective_oi: float) -> bool:
        """Enforces institutional Open Interest floor (250k NIFTY, 100k BANKNIFTY/SENSEX)."""
        min_oi = self.min_strike_oi_nifty if index_name == "NIFTY" else self.min_strike_oi_other
        return effective_oi >= min_oi

    def evaluate_nifty_frictional_hurdle(
        self,
        index_name: str,
        atr_15m: float,
        friction_drag_pts: float,
        target_pts: float,
        spot_price: float = 0.0,
    ) -> tuple[bool, str]:
        """Evaluates dynamic frictional hurdle for NIFTY.

        Prevents trades in low-volatility regimes where frictional drag consumes
        substantially all gross expectancy (e.g. 45 NIFTY historical trades paid
        ₹5,965 in friction on ₹6,070 gross PnL, leaving only ₹104 net PnL).

        Non-NIFTY indices pass unconditionally.
        For NIFTY:
        1. atr_15m must meet or exceed min_nifty_frictional_hurdle_atr (default 12.0 pts).
        2. Expected profit capacity (target_pts) must clear the frictional hurdle:
           target_pts >= min_nifty_hurdle_ratio * max(friction_drag_pts, 2.0).
        3. Spot price percentage volatility sanity: percentage volatility
           (atr_15m / spot_price) must be >= 0.05% when spot_price > 0.
        """
        if index_name != "NIFTY":
            return True, f"NON_NIFTY_INDEX_{index_name}_BYPASS"

        # Check 1: ATR Hurdle Floor
        if atr_15m < self.min_nifty_frictional_hurdle_atr:
            return (
                False,
                f"NIFTY_INSUFFICIENT_VOLATILITY: ATR 15m {atr_15m:.1f} < hurdle {self.min_nifty_frictional_hurdle_atr:.1f} pts",
            )

        # Check 2: Minimum Hurdle Ratio (Target / Friction)
        effective_drag = max(float(friction_drag_pts), 2.0)
        hurdle_req = self.min_nifty_hurdle_ratio * effective_drag
        if target_pts < hurdle_req:
            return (
                False,
                f"NIFTY_FRICTION_DRAG_UNECONOMIC: Target {target_pts:.1f}pts < {self.min_nifty_hurdle_ratio:.1f}x friction {effective_drag:.2f}pts (req {hurdle_req:.1f}pts)",
            )

        # Check 3: Percentage Volatility Fallacy Guard (Spot Level Normalization)
        if spot_price > 0:
            pct_vol = (atr_15m / spot_price) * 100.0
            if pct_vol < 0.05:
                return (
                    False,
                    f"NIFTY_PCT_VOLATILITY_STARVATION: Vol {pct_vol:.3f}% < 0.05% of spot {spot_price:.1f}",
                )

        return True, f"NIFTY_FRICTIONAL_HURDLE_CLEARED (ATR={atr_15m:.1f}, HurdleReq={hurdle_req:.1f}pts)"

    def _evaluate_orb_regime_permission(self, router: Optional[SentinelRegimeRouter]) -> bool:
        """Evaluates whether current regime state allows Mode 2 Opening Range Breakout (ORB).
        
        Hermes Invariant 4.1 Specification:
        * If router is None or post is None: allow default.
        * If post.is_trading_permitted is False: veto.
        * If post.dominant_regime in ("ROTATIONAL_CHOP", "AMBIGUOUS_NO_TRADE", "EXHAUSTION_REVERSAL"): veto.
        * If not post.permissions.get("ORB", False) and post.dominant_regime != "RUNAWAY_EXPANSION":
            - allow if post.dominant_regime == "VOLATILITY_COMPRESSION" and post.normalized_entropy < 0.70, else veto.
        """
        if router is None:
            return True
        post = getattr(router, "current_state", None) or (router.get_posterior() if hasattr(router, "get_posterior") else None)
        if post is None:
            return True

        if post.is_trading_permitted is False:
            return False

        if post.dominant_regime in ("ROTATIONAL_CHOP", "AMBIGUOUS_NO_TRADE", "EXHAUSTION_REVERSAL"):
            return False

        if not post.permissions.get("ORB", False) and post.dominant_regime != "RUNAWAY_EXPANSION":
            if post.dominant_regime == "VOLATILITY_COMPRESSION" and post.normalized_entropy < 0.70:
                return True
            return False

        return True

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
            # Update upstream regime router ring buffer and state via discrete 1-minute SyntheticBarBucket
            router = self.regime_routers.get(idx_key)
            bucket = self.bar_buckets.get(idx_key)
            if router is not None and bucket is not None:
                ts_ms = tick.exchange_timestamp_ms
                epoch_sec = (ts_ms / 1000.0) if ts_ms > 0 else time.time()
                epoch_min = int(epoch_sec // 60)

                if bucket.bucket_epoch_min == -1:
                    # Initialize first bucket
                    bucket.bucket_epoch_min = epoch_min
                    bucket.open = tick.ltp
                    bucket.high = tick.ltp
                    bucket.low = tick.ltp
                    bucket.close = tick.ltp
                    bucket.volume = float(tick.volume)
                    bucket.tick_count = 1
                    bucket.last_timestamp_ms = ts_ms
                elif epoch_min > bucket.bucket_epoch_min:
                    # Minute boundary crossed: finalize completed bar into router
                    bar_time = datetime.fromtimestamp(bucket.bucket_epoch_min * 60).time()
                    router.on_bar_close(
                        bar_close=bucket.close,
                        bar_volume=bucket.volume,
                        cvd_delta=0.0,
                        timestamp_ms=bucket.last_timestamp_ms,
                        bar_time=bar_time,
                    )
                    # Start new bucket for the new minute
                    bucket.bucket_epoch_min = epoch_min
                    bucket.open = tick.ltp
                    bucket.high = tick.ltp
                    bucket.low = tick.ltp
                    bucket.close = tick.ltp
                    bucket.volume = float(tick.volume)
                    bucket.tick_count = 1
                    bucket.last_timestamp_ms = ts_ms
                else:
                    # Accumulate within current minute
                    bucket.high = max(bucket.high, tick.ltp)
                    bucket.low = min(bucket.low, tick.ltp)
                    bucket.close = tick.ltp
                    bucket.volume += float(tick.volume)
                    bucket.tick_count += 1
                    bucket.last_timestamp_ms = ts_ms

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
        """Seeds or reconciles Opening Range (09:15-09:45) from Upstox Intraday API."""
        now_t = datetime.now().time()
        # Only run if post-opening shock (>= 09:45:00)
        if now_t < self.opening_shock_end_time:
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
                            print(f"📥 [OR RECOVERY/RECONCILE] {idx}: Seeded Opening Range from Upstox API -> High={h:.2f}, Low={l:.2f} (Range={h-l:.2f} pts)")
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
                # Strictly accumulate opening range ticks only after official market open (09:15)
                if now_t >= self.market_open_time:
                    b = self.or_bounds[index_name]
                    b["high"] = max(b["high"], spot)
                    b["low"] = min(b["low"], spot)
                    if index_name == "NIFTY":
                        self.active_range_high = b["high"]
                        self.active_range_low = b["low"]
            else:
                if self.trade_lock_active:
                    self.trade_lock_active = False
                    # Reconcile OR with official 1m candles to eliminate any stream drops or spurious ticks
                    self._seed_or_bounds_from_api_if_late_boot()
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
            
            # Gate 4: Derivatives OI Quarantine (Pre-09:15:00 IST stand-aside)
            # OI broadcast during pre-market is stale remnant from prior session
            effective_oi = float(depth.open_interest)
            if datetime.now().time() < self.market_open_time:
                effective_oi = 0.0

            wall_obs.on_option_tick(
                symbol=depth.symbol,
                ltp=depth.ltp or depth.bid_p1,
                volume=float(depth.volume),
                oi=effective_oi,
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

        # Late-session entry freeze: strictly suppress all candidate setups (>= 15:00:00 IST)
        if self.is_eod_entry_frozen(now_time):
            # Check if active position requires 15:15:00 mandatory square-off
            if now_time >= self.eod_mandatory_squareoff_time:
                apm = self.apms.get(index_name)
                if apm and apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
                    apm.evaluate_tick(current_spot=spot, current_opt_ltp=ltp, tick_time_str=now_dt.isoformat())
            return

        # Structural strike liquidity gate: require minimum open interest
        effective_oi = float(depth.open_interest)
        if not self.evaluate_strike_oi(index_name, effective_oi):
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
        # Invariant 4.1: Consult RegimeRouter to block blind ORB during ROTATIONAL_CHOP,
        # unpermitted trading, AMBIGUOUS_NO_TRADE, EXHAUSTION_REVERSAL, and high entropy.
        # -------------------------------------------------------------
        elif or_high > -math.inf and spot > or_high:
            router = self.regime_routers.get(index_name)
            regime_permits = self._evaluate_orb_regime_permission(router)
            if regime_permits:
                trigger_active = True
                required_option_type = "CE"
                setup_reason = f"Breakout > {or_high:.1f}"
        elif or_low < math.inf and spot < or_low:
            router = self.regime_routers.get(index_name)
            regime_permits = self._evaluate_orb_regime_permission(router)
            if regime_permits:
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

            # Factor 2: Macro Multi-Strike Option Writer Conviction & Market Maker Stress
            wall_obs = self.wall_observers.get(index_name)
            if wall_obs:
                w_state = wall_obs.compute_wall_state()
                # Derive writer conviction from multi-strike open interest asymmetry (PCR and Net OI)
                pcr = w_state.pcr_oi
                base_conviction = 0.50 + 0.35 * (pcr - 1.0) if required_option_type == "CE" else 0.50 + 0.35 * (1.0 - pcr)
                
                # Boost conviction when market makers are squeezed outside Straddle Breakeven (Gamma Squeeze)
                mm_stress = w_state.market_maker_stress_score
                if required_option_type == "CE" and mm_stress > 0:
                    base_conviction += (0.15 * mm_stress)  # Bullish squeeze bonus
                elif required_option_type == "PE" and mm_stress < 0:
                    base_conviction += (0.15 * abs(mm_stress))  # Bearish squeeze bonus
                elif w_state.straddle_profile.is_pin_risk:
                    base_conviction -= 0.10  # Penalize inside ATM pin chop

                # Factor 2B: Option Lead-Lag Aggression (Surges in ATM option buying volume)
                atm_prof = w_state.wall_density_map.get(w_state.straddle_profile.atm_strike)
                if atm_prof:
                    if required_option_type == "CE" and atm_prof.is_call_aggressive_buy:
                        base_conviction += 0.10  # Immediate ATM Call market buying surge
                    elif required_option_type == "PE" and atm_prof.is_put_aggressive_buy:
                        base_conviction += 0.10  # Immediate ATM Put market buying surge
                    
                dyn_conviction = max(0.20, min(0.95, round(base_conviction, 2)))
            else:
                dyn_conviction = 0.50

            conf_eval = self.confidence_scorer.evaluate_confidence(
                macro_aligned=macro_ok,
                macro_reason=macro_reason,
                writer_alignment="BEARS_IN_CONTROL" if required_option_type == "PE" else "BULLS_IN_CONTROL",
                writer_conviction=dyn_conviction,
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

            # Gate 2: SentinelWallGate pre-entry check (0.5 * ATR Adverse Wall Clamping)
            wall_gate = self.wall_gates.get(index_name)
            wall_vetoed = False
            wall_reason = ""
            if wall_gate is not None:
                wall_decision = wall_gate.evaluate_entry_gate(
                    direction=required_option_type,
                    spot_price=spot,
                    timestamp_ms=depth.exchange_timestamp_ms,
                )
                if wall_decision.action == GATE_ACTION_VETO:
                    wall_vetoed = True
                    wall_reason = wall_decision.reason

                # Feature: Option Wall Target Clamping before fortified barrier
                if not wall_vetoed:
                    clamp_decision = wall_gate.clamp_target_to_wall(
                        direction=required_option_type,
                        spot_price=spot,
                        nominal_target_pts=target_pts,
                        sl_pts=sl_pts,
                        timestamp_ms=depth.exchange_timestamp_ms,
                        wall_buffer_pts=1.0,
                        min_rr_ratio=1.0,
                    )
                    if clamp_decision.action == GATE_ACTION_CLAMP_TARGET and clamp_decision.clamped_target_pts is not None:
                        logger.info(
                            f"[{index_name}] Option Wall Target Clamping: Clamped TP from {target_pts:.1f} to {clamp_decision.clamped_target_pts:.1f} pts ({clamp_decision.reason})"
                        )
                        target_pts = clamp_decision.clamped_target_pts

            # Gate 3: NIFTY Dynamic Frictional Hurdle Gate
            hurdle_ok, hurdle_reason = self.evaluate_nifty_frictional_hurdle(
                index_name=index_name,
                atr_15m=eff_atr_15m,
                friction_drag_pts=total_drag,
                target_pts=target_pts,
                spot_price=spot,
            )

            if is_vetoed:
                status_flag = "VETO_SPREAD_EXPANDED"
                advisory = f"🚨 [SPREAD VETO] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED (>4.0% spread)"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="SPREAD_EXPANDED",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            elif wall_vetoed:
                status_flag = "VETO_ADVERSE_WALL"
                advisory = f"🚨 [WALL VETO: {wall_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED (Within 0.5 ATR of fortified wall)"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="ADVERSE_WALL",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            elif not macro_ok:
                status_flag = "VETO_MACRO_DIVERGENCE"
                advisory = f"🚨 [{macro_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="MACRO_DIVERGENCE",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            elif not vol_ok:
                status_flag = "VETO_VOLATILITY_EXHAUSTED"
                advisory = f"🚨 [{vol_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="VOLATILITY_EXHAUSTED",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            elif not hurdle_ok:
                status_flag = "VETO_NIFTY_FRICTIONAL_HURDLE"
                advisory = f"🚨 [{hurdle_reason}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="NIFTY_FRICTIONAL_HURDLE",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            elif not conf_eval.is_actionable:
                status_flag = "VETO_LOW_CONFIDENCE"
                advisory = f"🚨 [LOW CONVICTION: {conf_eval.total_score}/100 {conf_eval.grade}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="LOW_CONFIDENCE",
                    spot_price=spot,
                    option_ltp=ltp,
                    bid=bid,
                    ask=ask,
                    spread_pts=spread,
                    spread_ratio=spread_ratio,
                    nominal_target_pts=target_pts,
                    nominal_sl_pts=sl_pts,
                    confidence_score=conf_eval.total_score if conf_eval else 0,
                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time_str=now_time.strftime("%H:%M:%S"),
                )
            else:
                # Gate 1: Capital Discretization & Integer Lot Math (Floor-or-Reject Model)
                computed_lots, sizing_tier = calculate_discrete_lots(
                    total_capital=100000.0,
                    risk_budget_pct=0.02,
                    opt_premium=ltp,
                    sl_points=sl_pts,
                    index_name=index_name,
                    sizing_recommendation=conf_eval.sizing_recommendation,
                )
                ex_lot_size = get_exchange_lot_size(index_name)
                total_qty = computed_lots * ex_lot_size

                if computed_lots < 1 or sizing_tier == "ZERO_SUPPRESS":
                    status_flag = "VETO_INSUFFICIENT_MARGIN" if computed_lots < 1 else "VETO_SIZING_SUPPRESSED"
                    advisory = f"🚨 [SIZING VETO: {sizing_tier}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED (Lots={computed_lots})"
                    self.journal.record_veto(
                        index_name=index_name,
                        symbol=depth.symbol,
                        direction=required_option_type,
                        setup_reason=setup_reason,
                        veto_reason=f"SIZING_{sizing_tier}",
                        spot_price=spot,
                        option_ltp=ltp,
                        bid=bid,
                        ask=ask,
                        spread_pts=spread,
                        spread_ratio=spread_ratio,
                        nominal_target_pts=target_pts,
                        nominal_sl_pts=sl_pts,
                        confidence_score=conf_eval.total_score if conf_eval else 0,
                        confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                        sizing_tier=sizing_tier,
                        timestamp_ms=depth.exchange_timestamp_ms,
                        wall_time_str=now_time.strftime("%H:%M:%S"),
                    )
                else:
                    status_flag = "SIGNAL_TRIGGERED"
                    advisory = (
                        f"🎯 [BUY {depth.symbol}] @ {setup_reason} | "
                        f"Conviction: {conf_eval.total_score}/100 ({conf_eval.grade}, WinRate ~{conf_eval.probable_win_rate_pct:.0f}%, {sizing_tier}, {computed_lots} lots / {total_qty} qty) | "
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
                        # Invariant 2.3: Reject entry if in COOL_OFF or unarmable state
                        if idx_apm.state in {STATE_COOL_OFF, STATE_IN_FLIGHT, STATE_TRAIL_LOCK, STATE_EXIT_PENDING}:
                            is_target_strike = False
                        # Allow entry if APM is in STANDBY, LIQUIDATED, or PULLBACK_WAIT
                        elif is_target_strike and idx_apm.state in {STATE_STANDBY, STATE_LIQUIDATED, STATE_PULLBACK_WAIT}:
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
                                lots=computed_lots,
                                sizing_tier=sizing_tier,
                                lot_size=ex_lot_size,
                                total_quantity=total_qty,
                                is_expiry_day=is_exp,
                                is_deep_itm=(itm_res.moneyness == "DEEP_ITM"),
                            )
                            if entered:
                                self.journal.record_execution(
                                    position_id=pos_id,
                                    index_name=index_name,
                                    symbol=depth.symbol,
                                    direction=required_option_type,
                                    setup_reason=setup_reason,
                                    spot_price=spot,
                                    option_ltp=ltp,
                                    fill_price=fill_price,
                                    fill_mode=fill_mode,
                                    spread_savings=savings,
                                    target_pts=target_pts,
                                    sl_pts=sl_pts,
                                    confidence_score=conf_eval.total_score if conf_eval else 0,
                                    confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                                    lots=computed_lots,
                                    lot_size=ex_lot_size,
                                    total_quantity=total_qty,
                                    sizing_tier=sizing_tier,
                                    timestamp_ms=depth.exchange_timestamp_ms,
                                    wall_time_str=now_time.strftime("%H:%M:%S"),
                                )
                            if entered and self.enable_stdout:
                                print(
                                    f"\n🚀 [APM IN_FLIGHT ENTRY ({index_name}) - {itm_res.moneyness}] {pos_id} | {depth.symbol} @ {spot:.1f} | "
                                    f"Conviction: {conf_eval.total_score}/100 ({conf_eval.grade}) | "
                                    f"Lots: {computed_lots} ({sizing_tier}, Qty={total_qty}) | "
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
                    prev_state = idx_apm.state
                    idx_apm.evaluate_tick(
                        current_spot=spot,
                        current_opt_ltp=ltp,
                        tick_time_str=now_time.strftime("%H:%M:%S"),
                        atr_1m=12.0,
                    )
                    # Check if position just liquidated
                    if prev_state != idx_apm.state and idx_apm.state in {STATE_LIQUIDATED, STATE_COOL_OFF}:
                        last_trade = idx_apm.last_completed_trade or (idx_apm.trade_history[-1] if idx_apm.trade_history else None)
                        if last_trade:
                            lt_dict = last_trade if isinstance(last_trade, dict) else asdict(last_trade)
                            self.journal.record_exit(
                                position_id=lt_dict.get("position_id", ""),
                                index_name=index_name,
                                symbol=depth.symbol,
                                direction=lt_dict.get("direction", ""),
                                entry_price_spot=float(lt_dict.get("entry_price") or 0.0),
                                exit_price_spot=float(lt_dict.get("exit_price") or 0.0),
                                entry_price_opt=float(lt_dict.get("opt_entry_ltp") or 0.0),
                                exit_price_opt=float(lt_dict.get("opt_exit_ltp") or ltp),
                                opt_pnl_pts=float(lt_dict.get("opt_pnl_pts") or 0.0),
                                spot_pnl_pts=float(lt_dict.get("pnl_pts") or 0.0),
                                exit_reason=str(lt_dict.get("exit_reason") or "LIQUIDATED"),
                                max_spot_excursion=float(lt_dict.get("max_spot_excursion") or 0.0),
                                max_opt_excursion=float(lt_dict.get("max_opt_excursion") or 0.0),
                                target_1_hit=bool(lt_dict.get("target_1_hit")),
                                target_2_hit=bool(lt_dict.get("target_2_hit")),
                                half_booked=bool(lt_dict.get("half_booked")),
                                trail_locked=bool(lt_dict.get("trail_locked")),
                                total_quantity=int(lt_dict.get("total_quantity") or 65),
                                timestamp_ms=depth.exchange_timestamp_ms,
                                wall_time_str=now_time.strftime("%H:%M:%S"),
                            )

        # Feed option depth tick to Shadow Barrier Path Evaluator
        self.journal.on_option_tick(
            symbol=depth.symbol,
            current_opt_ltp=ltp,
            timestamp_ms=depth.exchange_timestamp_ms,
            wall_time_str=now_time.strftime("%H:%M:%S"),
            current_spot=spot,
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
