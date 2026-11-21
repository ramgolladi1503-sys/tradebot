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

import copy
import atexit
import fcntl
import hashlib
import json
import logging
import math
import os
import queue
import stat
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Optional, Dict
from zoneinfo import ZoneInfo

from config import config as app_config

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
from core.intraday_reversal_engine import (
    IntradayReversalEngine,
    ReversalDirection,
    ReversalSetupType,
)
from core.midday_momentum_extension_engine import (
    MiddayMomentumExtensionEngine,
    MiddayDirection,
    MiddayMomentumSignal,
)
from strategies.optionmate_rbfn_strategy import (
    OptionMateRBFNStrategy,
    OptionMateGrid,
    OptionMateSignal,
)
from core.sentinel_execution_router import SentinelExecutionRouter
from core.sentinel_automated_order_dispatcher import SentinelAutomatedOrderDispatcher
from core.orders.gtt_stop_dispatcher import GTTStopDispatcher
from strategies.sensex_optionmate_rbfn_strategy import (
    SensexOptionMateRBFNStrategy,
    SensexOptionMateGrid,
    SensexOptionMateSignal,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.structural_alpha_gates import (
    CrossIndexMacroGate,
    ITMStrikeResolver,
    PassiveMidpointQueueModel,
    VolatilityCompressionGate,
)
from core.sentinel_option_strike_resolver import (
    SentinelOptionStrikeResolver,
    Mode5StrikeSelection,
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


@dataclass(slots=True)
class Synthetic5mBarBucket:
    """Aggregates spot ticks into discrete 5-minute OHLCV bars for RBFN auction evaluation."""
    bucket_epoch_5min: int = -1
    open: float = 0.0
    high: float = -math.inf
    low: float = math.inf
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
    last_timestamp_ms: int = 0
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(slots=True, frozen=True)
class CachedRBFNAuctionSignal:
    """Cached precomputed RBFN Slingshot/Auction signal evaluated on 5-minute bar close.
    
    Provides sub-250ns execution in Level-5 depth evaluation loop with zero float math overhead.
    """
    timestamp_ms: int
    index_name: str
    action: str  # 'BUY_CALL', 'BUY_PUT', or 'ABSTAIN'
    direction: str  # 'CE', 'PE', or ''
    target_strike: float
    target_pts: float
    sl_pts: float
    setup_reason: str
    trade_phase: str  # 'OPENING_DRIVE' or 'MIDDAY_REVERSAL'
    bar_time: dt_time
    sustainable_anchor_price: float = 0.0
    triggering_reference_price: Optional[float] = None
    is_active: bool = True
    is_vetoed: bool = False
    veto_reason: str = ""
    valid_until_epoch_sec: float = 0.0
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(slots=True, frozen=True)
class CachedRBFNCandidateMetadata:
    """Process-local decision availability metadata paired with one cached bar signal."""

    generation: int
    issued_monotonic_ns: int
    boundary_timestamp_ms: int
    session_day: date
    status: str = "AVAILABLE"


@dataclass(frozen=True, slots=True)
class Mode5TraceQueueItem:
    """Bounded immutable JSONL payload reserved by a quote/decision callback."""

    serialized_record: str
    trace_sequence: int
    dedup_key: Optional[tuple[str, str, Optional[int], str]]
    reservation_id: int
    suppression_record: bool


# ARCH-SENTINEL-OPTIONMATE-HARDENING-001: Mode 5 Setup Classification for Wall-Gate Exemptions
MODE_5_STRUCTURAL_BREAKOUTS: set[str] = {
    "RP1_UPPER_10M_EXPANSION_BREAKOUT",
    "RP1_LOWER_10M_EXPANSION_BREAKDOWN",
    "RP1_UPPER_AGGRESSIVE_DRIVE",
    "RP1_LOWER_AGGRESSIVE_DRIVE",
}

MODE_5_EXHAUSTION_FADES: set[str] = {
    "RP2_UPPER_10M_CEILING_FADE",
    "RP2_LOWER_10M_FLOOR_BOUNCE",
    "RP2_UPPER_FAST_REJECTION",
    "RP2_LOWER_FAST_BOUNCE",
    "RP1_UPPER_REVERSAL_CONFIRMED",
    "RP1_LOWER_REVERSAL_CONFIRMED",
}

MODE_5_RP1_EXPANSIONS: set[str] = {
    "RP1_UPPER_10M_EXPANSION_BREAKOUT",
    "RP1_LOWER_10M_EXPANSION_BREAKDOWN",
}

def mode5_rp_exhaustion_displacement(
    setup_reason: str,
    triggering_reference_price: Optional[float],
    spot: float,
    fallback_displacement: float,
) -> tuple[float, Optional[str]]:
    """Resolve gate-local displacement for explicitly mapped frozen RP setups.

    Returns the existing displacement unchanged for unrelated setup families.
    Unknown RP1/RP2 reversal/fade names and missing/invalid snapshots fail closed.
    """
    if setup_reason in MODE_5_RP1_EXPANSIONS:
        try:
            reference = float(triggering_reference_price)
            current_spot = float(spot)
        except (TypeError, ValueError, OverflowError):
            return fallback_displacement, "MISSING_RP_BOUNDARY_REFERENCE"
        if (
            not math.isfinite(reference)
            or reference <= 0.0
            or not math.isfinite(current_spot)
            or current_spot <= 0.0
        ):
            return fallback_displacement, "MISSING_RP_BOUNDARY_REFERENCE"
        return abs(current_spot - reference), None

    if setup_reason not in MODE_5_EXHAUSTION_FADES:
        is_unmapped_rp_fade = (
            setup_reason.startswith(("RP1_", "RP2_"))
            and any(token in setup_reason for token in ("REVERSAL", "FADE", "BOUNCE", "FLOOR", "CEILING", "REJECTION"))
        )
        if is_unmapped_rp_fade:
            return fallback_displacement, "UNKNOWN_RP_BOUNDARY_SETUP"
        return fallback_displacement, None

    try:
        reference = float(triggering_reference_price)
        current_spot = float(spot)
    except (TypeError, ValueError, OverflowError):
        return fallback_displacement, "MISSING_RP_BOUNDARY_REFERENCE"
    if not math.isfinite(reference) or reference <= 0.0 or not math.isfinite(current_spot) or current_spot <= 0.0:
        return fallback_displacement, "MISSING_RP_BOUNDARY_REFERENCE"
    return abs(current_spot - reference), None


def is_mode_5_structural_breakout(reason: str) -> bool:
    """Predicate checking if setup is a confirmed Mode 5 structural breakout."""
    return any(k in reason for k in MODE_5_STRUCTURAL_BREAKOUTS)


def is_mode_5_exhaustion_fade(reason: str) -> bool:
    """Predicate checking if setup is a confirmed Mode 5 exhaustion fade."""
    return any(k in reason for k in MODE_5_EXHAUSTION_FADES)


@dataclass(slots=True)
class PriorDayReferenceLevels:
    """Dynamic reference levels (PDH, PDL, PDC) with explicit verification and validation state."""
    index_name: str
    pdh: float = 0.0
    pdl: float = 0.0
    pdc: float = 0.0
    session_date: Optional[date] = None
    atr_20: Optional[float] = None
    verified: bool = False

    def validate(self) -> bool:
        """Validates prior day levels: fail-closed if pdh <= pdl or pdl <= 0."""
        return self.pdh > self.pdl and self.pdl > 0.0

    def get(self, key: str, default: float = 0.0) -> float:
        """Compatibility helper for dictionary-like access."""
        if key == "pdh":
            return self.pdh
        elif key == "pdl":
            return self.pdl
        elif key == "pdc":
            return self.pdc
        return default


class SentinelLiveStreamAdvisor(StreamSubscriber):
    """Event-driven live paper advisory engine operating directly on in-memory
    Upstox ticks and Level-5 order book depth.
    """

    INDEX_ATR_BOUNDS: dict[str, tuple[float, float]] = {
        "SENSEX": (450.0, 900.0),
        "BANKNIFTY": (300.0, 650.0),
        "NIFTY": (130.0, 300.0),
    }

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
        advisory_capital: float = 30000.0,
        enable_automated_dispatch: bool = False,
        enable_nifty_live: bool = False,
        broker_adapter: Optional[any] = None,
        mode5_trace_queue_capacity: int = 1536,
        mode5_trace_max_record_bytes: int = 16384,
        or_reconciliation_state_path: Optional[str] = None,
    ) -> None:
        if isinstance(mode5_trace_queue_capacity, bool) or not isinstance(mode5_trace_queue_capacity, int) or mode5_trace_queue_capacity < 1:
            raise ValueError("mode5_trace_queue_capacity must be a positive integer")
        if isinstance(mode5_trace_max_record_bytes, bool) or not isinstance(mode5_trace_max_record_bytes, int) or mode5_trace_max_record_bytes < 256:
            raise ValueError("mode5_trace_max_record_bytes must be an integer of at least 256")
        self.adapter = adapter if adapter is not None else InMemorySentinelAdapter()
        self.spread_veto_threshold = float(spread_veto_threshold)
        # Configurable capital: fallback to env or standard 30k allocation
        env_cap = os.getenv("ALLOCATED_TRADING_CAPITAL")
        self.advisory_capital = float(env_cap) if env_cap else float(advisory_capital)
        self.enable_automated_dispatch = enable_automated_dispatch
        self.enable_nifty_live = enable_nifty_live
        self.execution_router = SentinelExecutionRouter(enable_nifty_live=enable_nifty_live)
        self.gtt_stop_dispatcher = GTTStopDispatcher(
            broker_adapter=broker_adapter,
            enable_live_dispatch=enable_nifty_live,
        ) if enable_automated_dispatch else None
        self.automated_dispatcher = SentinelAutomatedOrderDispatcher(
            router=self.execution_router,
            broker_adapter=broker_adapter,
            gtt_stop_dispatcher=self.gtt_stop_dispatcher,
        ) if enable_automated_dispatch else None
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
        p_wal = Path(wal_path)
        wal_dir = p_wal.parent
        self.wal_dir = wal_dir
        stem = p_wal.stem
        ext = p_wal.suffix or ".json"
        self.apms: dict[str, ActivePositionManager] = {
            "NIFTY": ActivePositionManager(wal_path=str(wal_dir / f"{stem}{ext}")),
            "SENSEX": ActivePositionManager(wal_path=str(wal_dir / f"{stem}_sensex{ext}")),
            "BANKNIFTY": ActivePositionManager(wal_path=str(wal_dir / f"{stem}_banknifty{ext}")),
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
        self.or_evidence: dict[str, dict[str, Any]] = {
            index_name: self._empty_or_evidence()
            for index_name in self.or_bounds
        }

        # If current time is past opening shock (09:45), trade lock is cleared
        self.trade_lock_active = (datetime.now(ZoneInfo("Asia/Kolkata")).time() < self.opening_shock_end_time)
        self.or_reconciliation_frozen: bool = False
        self.or_last_reconcile_attempt_ms: dict[str, int] = {
            "NIFTY": 0,
            "BANKNIFTY": 0,
            "SENSEX": 0,
        }
        self.or_reconcile_retry_count: dict[str, int] = {
            "NIFTY": 0,
            "BANKNIFTY": 0,
            "SENSEX": 0,
        }
        self.OR_MAX_RETRY_ATTEMPTS: int = 10
        self.OR_MIN_RETRY_INTERVAL_MS: int = 60_000  # 60s throttle
        self.or_reconciliation_state_path = Path(
            or_reconciliation_state_path
            if or_reconciliation_state_path is not None
            else Path(__file__).resolve().parents[1] / "runtime" / "sentinel_or_reconciliation_state.json"
        ).resolve()
        self.or_reconciliation_lock_path = Path(
            f"{self.or_reconciliation_state_path}.lock"
        )
        self.or_reconciliation_initialized_path = (
            self.or_reconciliation_state_path.parent
            / f".{self.or_reconciliation_state_path.stem}.initialized"
        )
        self._or_reconcile_call_lock = threading.Lock()
        self._or_reconciliation_ledger_degraded = False
        self._or_reconciliation_loaded_session_day: Optional[date] = None
        self._or_ledger_retry_after_ms = 0
        self._or_last_ledger_check_ms: dict[str, int] = {
            "NIFTY": 0,
            "BANKNIFTY": 0,
            "SENSEX": 0,
        }
        self.spots: dict[str, float] = {"NIFTY": 0.0, "SENSEX": 0.0, "BANKNIFTY": 0.0}
        self.spots_ts_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}

        # Structural Alpha Invariant Gates
        self.macro_gate = CrossIndexMacroGate()
        self.vol_compression_gate = VolatilityCompressionGate()
        self.passive_midpoint_queue = PassiveMidpointQueueModel()
        self.strike_resolver = ITMStrikeResolver()
        self.max_premium_cap = 250.0  # Stream 1 Invariant: Enforce strike premium cap to eliminate deep-ITM tail drawdowns

        # Expiry calendar feeds session-aware confidence and shared schedule checks.
        self.expiry_resolver = ExpiryCalendarResolver()
        self.expiry_info = self.expiry_resolver.classify_session(datetime.now(ZoneInfo("Asia/Kolkata")).date())

        # FEAT-SENTINEL-INTRADAY-REVERSAL-001: Decoupled Intraday Reversal Engines per index
        self.reversal_engines: dict[str, IntradayReversalEngine] = {
            "NIFTY": IntradayReversalEngine(index_name="NIFTY"),
            "SENSEX": IntradayReversalEngine(index_name="SENSEX"),
            "BANKNIFTY": IntradayReversalEngine(index_name="BANKNIFTY"),
        }
        self.reversal_engine = self.reversal_engines["NIFTY"]

        # FEAT-SENTINEL-MIDDAY-MOMENTUM-001: Midday Momentum Extension Engines per index (12:30 IST)
        self.midday_engines: dict[str, MiddayMomentumExtensionEngine] = {
            "NIFTY": MiddayMomentumExtensionEngine(index_name="NIFTY", drift_threshold=0.0060, target_pts=40.0, stop_pts=40.0),
            "SENSEX": MiddayMomentumExtensionEngine(index_name="SENSEX", drift_threshold=0.0060, target_pts=150.0, stop_pts=150.0),
            "BANKNIFTY": MiddayMomentumExtensionEngine(index_name="BANKNIFTY", drift_threshold=0.0060, target_pts=100.0, stop_pts=100.0),
        }
        self.midday_engine = self.midday_engines["NIFTY"]

        # Previous Day Reference Levels (PDH / PDL / PDC) - Initialized unseeded with verified=False (Zero Hardcoding)
        self.prior_day_levels: dict[str, PriorDayReferenceLevels] = {
            "NIFTY": PriorDayReferenceLevels(index_name="NIFTY", verified=False),
            "SENSEX": PriorDayReferenceLevels(index_name="SENSEX", verified=False),
            "BANKNIFTY": PriorDayReferenceLevels(index_name="BANKNIFTY", verified=False),
        }

        # Index-specific baseline ATR floors
        self.index_atr_floors: dict[str, float] = {
            "NIFTY": 25.0,
            "BANKNIFTY": 100.0,
            "SENSEX": 150.0,
        }

        # Midday Liquidity Slump Guard configuration (11:30 - 12:30 IST)

        # Multi-Factor Option Confidence Scorer
        self.confidence_scorer = OptionConfidenceScorer(min_actionable_score=60)

        # FEAT-SENTINEL-REGIME-ROUTER-001: Upstream Supervisory Regime Router
        self.regime_routers: dict[str, SentinelRegimeRouter] = {
            "NIFTY": SentinelRegimeRouter(),
            "SENSEX": SentinelRegimeRouter(),
            "BANKNIFTY": SentinelRegimeRouter(),
        }
        self.regime_router = self.regime_routers["NIFTY"]

        # FEAT-SENTINEL-OPTIONMATE-RBFN-AUCTION-001: RBFN Strategy Engines per index
        self.rbfn_strategies: dict[str, Any] = {
            "NIFTY": OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=65.0, min_vix_hurdle=12.0),
            "BANKNIFTY": OptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=250.0, min_vix_hurdle=12.0),
            "SENSEX": SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=450.0, min_vix_hurdle=12.0),
        }
        self.rbfn_strategy = self.rbfn_strategies["NIFTY"]

        # Synthetic 5-minute bar buckets per index for Mode 5 RBFN Auction Engine
        self.bar_buckets_5m: dict[str, Synthetic5mBarBucket] = {
            "NIFTY": Synthetic5mBarBucket(),
            "SENSEX": Synthetic5mBarBucket(),
            "BANKNIFTY": Synthetic5mBarBucket(),
        }
        self.evaluated_5m_epochs: dict[str, set[int]] = {
            "NIFTY": set(),
            "SENSEX": set(),
            "BANKNIFTY": set(),
        }
        self.bars_5m_history: dict[str, list[dict[str, Any]]] = {
            "NIFTY": [],
            "SENSEX": [],
            "BANKNIFTY": [],
        }
        self.cached_rbfn_grids: dict[str, Any] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        self.rbfn_grids_frozen: dict[str, bool] = {
            "NIFTY": False,
            "SENSEX": False,
            "BANKNIFTY": False,
        }
        self.cached_rbfn_signals: dict[str, Optional[CachedRBFNAuctionSignal]] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        # Candidate age is process-local and intentionally not restored from WAL.
        self._cached_rbfn_candidate_meta: dict[str, Optional[CachedRBFNCandidateMetadata]] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        self._cached_rbfn_generation: dict[str, int] = {
            "NIFTY": 0,
            "SENSEX": 0,
            "BANKNIFTY": 0,
        }
        self._option_depth_watermarks: dict[str, dict[str, tuple[date, int, int]]] = {
            "NIFTY": {},
            "SENSEX": {},
            "BANKNIFTY": {},
        }
        self.rp2_upper_pierced_before_1030: dict[str, bool] = {
            "NIFTY": False,
            "SENSEX": False,
            "BANKNIFTY": False,
        }
        self.rp2_lower_pierced_before_1030: dict[str, bool] = {
            "NIFTY": False,
            "SENSEX": False,
            "BANKNIFTY": False,
        }
        # Backward-compatibility alias for tests and external inspection
        self.rp2_pierced_before_1030: dict[str, bool] = {
            "NIFTY": False,
            "SENSEX": False,
            "BANKNIFTY": False,
        }
        self._rp2_session_dates: dict[str, Optional[date]] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        self._ground_truth_required: dict[str, bool] = {
            "NIFTY": False,
            "SENSEX": False,
            "BANKNIFTY": False,
        }
        self._ground_truth_session_dates: dict[str, Optional[str]] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        self._last_spot_timestamp_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}
        self._last_5m_timestamp_ms: dict[str, int] = {"NIFTY": 0, "SENSEX": 0, "BANKNIFTY": 0}
        self._last_completed_5m_epoch: dict[str, int] = {"NIFTY": -1, "SENSEX": -1, "BANKNIFTY": -1}
        self.session_open_prices: dict[str, float] = {
            "NIFTY": 0.0,
            "SENSEX": 0.0,
            "BANKNIFTY": 0.0,
        }

        # Synthetic 1-minute bar buckets per index for discrete regime discretization (Invariant 4.1)
        self.bar_buckets: dict[str, SyntheticBarBucket] = {
            "NIFTY": SyntheticBarBucket(),
            "SENSEX": SyntheticBarBucket(),
            "BANKNIFTY": SyntheticBarBucket(),
        }

        # Rolling true ranges from 1-minute synthetic bars (maxlen=20) for dynamic ATR updates
        self.bar_true_ranges: dict[str, deque[float]] = {
            "NIFTY": deque(maxlen=20),
            "SENSEX": deque(maxlen=20),
            "BANKNIFTY": deque(maxlen=20),
        }

        # FEAT-SENTINEL-WALL-OBSERVER-001: In-Memory Strike Wall Observers per index
        self.wall_observers: dict[str, SentinelWallObserver] = {
            "NIFTY": SentinelWallObserver(underlying_symbol="NIFTY", atr_pts=65.0),
            "SENSEX": SentinelWallObserver(underlying_symbol="SENSEX", atr_pts=500.0),
            "BANKNIFTY": SentinelWallObserver(underlying_symbol="BANKNIFTY", atr_pts=300.0),
        }
        self.wall_observer = self.wall_observers["NIFTY"]

        # Gate 2: SentinelWallGates for pre-entry barrier verification
        self.wall_gates: dict[str, SentinelWallGate] = {
            "NIFTY": SentinelWallGate(observer=self.wall_observers["NIFTY"], proximity_veto_atr=0.50, wall_buffer_pts=2.0),
            "SENSEX": SentinelWallGate(observer=self.wall_observers["SENSEX"], proximity_veto_atr=0.50, wall_buffer_pts=15.0),
            "BANKNIFTY": SentinelWallGate(observer=self.wall_observers["BANKNIFTY"], proximity_veto_atr=0.50, wall_buffer_pts=10.0),
        }
        self.wall_gate = self.wall_gates["NIFTY"]

        self.alerts_history: list[AdvisoryAlert] = []
        self._lock = threading.RLock()
        # If launched post-09:45, seed the OR through the existing v2 path only
        # after locks are ready so bounds and provenance are committed atomically.
        self._seed_or_bounds_from_api_if_late_boot()
        self._om_levels_lock = threading.Lock()
        self._last_om_levels_mtime: float = 0.0
        self._last_om_check_mono: float = 0.0
        self._last_alert_time = 0.0
        self._last_wall_persist_time = 0.0
        self.session_gear = "GEAR_1_RANGE"  # Legacy global fallback
        self.session_gears: dict[str, str] = {
            "NIFTY": "GEAR_1_RANGE",
            "SENSEX": "GEAR_1_RANGE",
            "BANKNIFTY": "GEAR_1_RANGE",
        }
        self.gear_expansion_ratios: dict[str, float] = {
            "NIFTY": 0.0,
            "SENSEX": 0.0,
            "BANKNIFTY": 0.0,
        }
        self.gear_trend_bar_counters: dict[str, int] = {
            "NIFTY": 0,
            "SENSEX": 0,
            "BANKNIFTY": 0,
        }
        self.gear_range_bar_counters: dict[str, int] = {
            "NIFTY": 0,
            "SENSEX": 0,
            "BANKNIFTY": 0,
        }
        # Multi-Strategy Advisory Ranking Ledger (maps position_id -> priority weight)
        self.strategy_priority_weights: dict[str, float] = {
            "OPTIONMATE_RBFN_AUCTION": 1.00,
            "MIDDAY_MOMENTUM_EXTENSION": 0.85,
            "INTRADAY_REVERSAL": 0.40,
        }
        # Daily canonical trade counters per index for dual-stream shadow tagging
        # Vector 1 / 13: Seed from APM WAL so daily trade count survives restarts/reboots
        self.daily_trade_counters: dict[str, int] = {
            "NIFTY": self.apms["NIFTY"].daily_trade_count if "NIFTY" in self.apms else 0,
            "SENSEX": self.apms["SENSEX"].daily_trade_count if "SENSEX" in self.apms else 0,
            "BANKNIFTY": self.apms["BANKNIFTY"].daily_trade_count if "BANKNIFTY" in self.apms else 0,
        }

        # Forensic Decision Journal Engine (non-blocking in-memory queue & shadow barrier evaluator)
        self.journal = journal if journal is not None else SentinelRealtimeJournal()

        # Invariant 3.1: Granular Per-Gate Veto Ledger and Opportunity Starvation Counters
        self.veto_counters: dict[str, int] = {
            "SPREAD": 0,
            "PREMIUM_CAP": 0,
            "ADVERSE_WALL": 0,
            "MACRO_DIVERGENCE": 0,
            "VOL_EXHAUSTION": 0,
            "NIFTY_HURDLE": 0,
            "LOW_CONF": 0,
            "COMPANION_STALE": 0,
            "EOD_FROZEN": 0,
            "OI_FLOOR": 0,
        }
        self.total_veto_evaluations: int = 0
        self.accepted_trade_count: int = 0

        # Decision trace file path and lock (ARCH-SENTINEL-HARDENING-002)
        self.decision_trace_path = Path("runtime") / "sentinel_decision_trace.jsonl"
        # Trace-state reservations never perform I/O. Lock order is advisor `_lock`
        # then this state lock; append serialization is a separate lock acquired
        # only after both state locks have been released.
        self._mode5_quote_trace_state_lock = threading.Lock()
        self._decision_trace_lock = threading.Lock()
        self._mode5_quote_trace_emitted: set[tuple[str, str, Optional[int], str]] = set()
        self._mode5_quote_trace_attempts: dict[tuple[str, str, Optional[int], str], int] = {}
        self._mode5_quote_trace_inflight: dict[tuple[str, str, Optional[int], str], int] = {}
        self._mode5_quote_trace_dropped: set[tuple[str, str, Optional[int], str]] = set()
        self._mode5_quote_trace_sequence = 0
        self.trace_run_id = str(uuid.uuid4())
        self._mode5_quote_trace_active_generation: dict[str, Optional[int]] = {
            "NIFTY": None,
            "SENSEX": None,
            "BANKNIFTY": None,
        }
        self.mode5_trace_queue_capacity = mode5_trace_queue_capacity
        self.mode5_trace_max_record_bytes = mode5_trace_max_record_bytes
        self._mode5_trace_queue: queue.Queue[Mode5TraceQueueItem] = queue.Queue(
            maxsize=mode5_trace_queue_capacity
        )
        self._mode5_trace_health_lock = threading.Lock()
        self._mode5_trace_health: dict[str, Any] = {
            "enqueued": 0,
            "append_successes": 0,
            "append_failures": 0,
            "queue_full_drops": 0,
            "oversize_drops": 0,
            "writer_unavailable_drops": 0,
            "pending_unpersisted": 0,
            "active_writes": 0,
            "writer_status": "STARTING",
            "last_persisted_sequence": None,
            "last_processed_sequence": None,
            "last_error": None,
            "degraded": False,
        }
        self._mode5_trace_accepting = True
        self._mode5_trace_stop = threading.Event()
        self._mode5_trace_stopped = threading.Event()
        self._mode5_trace_shutdown_lock = threading.Lock()
        self._mode5_trace_atexit_callback = None
        self._mode5_trace_writer = threading.Thread(
            target=self._mode5_trace_writer_main,
            name=f"Mode5TraceWriter-{id(self):x}",
            daemon=True,
        )
        try:
            self._mode5_trace_writer.start()
        except Exception as exc:
            self._mode5_trace_accepting = False
            with self._mode5_trace_health_lock:
                self._mode5_trace_health["writer_status"] = "FAILED"
                self._mode5_trace_health["last_error"] = f"writer_start:{type(exc).__name__}"
                self._mode5_trace_health["degraded"] = True
            self._mode5_trace_stopped.set()
        else:
            self._mode5_trace_atexit_callback = self._shutdown_mode5_trace_writer_at_exit
            atexit.register(self._mode5_trace_atexit_callback)

        # Non-negotiable Trading Safety Invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    def _append_decision_trace_record_locked(self, record: str | dict[str, Any]) -> bool:
        """Append one pre-serialized JSONL record while the writer holds append lock."""
        try:
            serialized = record if isinstance(record, str) else json.dumps(record)
            self.decision_trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.decision_trace_path, "a", encoding="utf-8") as f:
                f.write(serialized + "\n")
            return True
        except Exception:
            return False

    def _mode5_trace_key(
        self, index_name: str, candidate_generation: Optional[int], reason: str, timestamp_ms: int
    ) -> tuple[str, str, Optional[int], str]:
        try:
            session = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).date().isoformat()
        except (OverflowError, OSError, TypeError, ValueError):
            session = "UNKNOWN_SESSION"
        return session, index_name, candidate_generation, reason

    def _mode5_trace_health_changed(self, **updates: Any) -> None:
        with self._mode5_trace_health_lock:
            self._mode5_trace_health.update(updates)

    def _mode5_trace_health_increment(self, **increments: int) -> None:
        with self._mode5_trace_health_lock:
            for key, amount in increments.items():
                self._mode5_trace_health[key] += amount

    def get_mode5_trace_health(self) -> dict[str, Any]:
        """Return a thread-safe snapshot of queue, writer, and persistence health."""
        with self._mode5_trace_health_lock:
            result = dict(self._mode5_trace_health)
        result.update({
            "capacity": self.mode5_trace_queue_capacity,
            "max_record_bytes": self.mode5_trace_max_record_bytes,
            "queue_depth": self._mode5_trace_queue.qsize(),
        })
        return result

    def _enqueue_mode5_trace_record(
        self,
        record: dict[str, Any],
        *,
        dedup_key: Optional[tuple[str, str, Optional[int], str]],
        suppression_record: bool = False,
        expected_signal: Optional[CachedRBFNAuctionSignal] = None,
        expected_generation: Optional[int] = None,
    ) -> bool:
        """Reserve and enqueue without blocking on disk; return queue acceptance only."""
        with self._lock:
            if expected_signal is not None:
                current_signal = self.cached_rbfn_signals.get(record["index_name"])
                current_meta = self._cached_rbfn_candidate_meta.get(record["index_name"])
                if (
                    current_signal is not expected_signal
                    or current_meta is None
                    or current_meta.generation != expected_generation
                    or current_meta.status != "AVAILABLE"
                ):
                    return False
            with self._mode5_quote_trace_state_lock:
                if suppression_record and dedup_key is not None:
                    if self._mode5_quote_trace_active_generation.get(record["index_name"]) != expected_generation:
                        return False
                    if (
                        dedup_key in self._mode5_quote_trace_emitted
                        or dedup_key in self._mode5_quote_trace_inflight
                        or dedup_key in self._mode5_quote_trace_dropped
                        or self._mode5_quote_trace_attempts.get(dedup_key, 0) >= 2
                    ):
                        return False
                elif dedup_key is not None:
                    if (
                        dedup_key in self._mode5_quote_trace_emitted
                        or dedup_key in self._mode5_quote_trace_dropped
                        or dedup_key in self._mode5_quote_trace_inflight
                        or self._mode5_quote_trace_attempts.get(dedup_key, 0) >= 2
                    ):
                        return False

                if not self._mode5_trace_accepting:
                    if dedup_key is not None:
                        self._mode5_quote_trace_dropped.add(dedup_key)
                    self._mode5_trace_health_increment(writer_unavailable_drops=1)
                    self._mode5_trace_health_changed(degraded=True)
                    return False

                self._mode5_quote_trace_sequence += 1
                trace_sequence = self._mode5_quote_trace_sequence
                record["trace_run_id"] = self.trace_run_id
                record["trace_sequence"] = trace_sequence
                try:
                    serialized = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
                    record_size = len(serialized.encode("utf-8"))
                except Exception:
                    serialized = ""
                    record_size = self.mode5_trace_max_record_bytes + 1
                if record_size > self.mode5_trace_max_record_bytes:
                    if dedup_key is not None:
                        self._mode5_quote_trace_dropped.add(dedup_key)
                    self._mode5_trace_health_increment(oversize_drops=1)
                    self._mode5_trace_health_changed(degraded=True, last_error="record_serialization_or_size_limit")
                    return False

                reservation_id = trace_sequence
                if dedup_key is not None:
                    self._mode5_quote_trace_inflight[dedup_key] = reservation_id
                item = Mode5TraceQueueItem(
                    serialized_record=serialized,
                    trace_sequence=trace_sequence,
                    dedup_key=dedup_key,
                    reservation_id=reservation_id,
                    suppression_record=suppression_record,
                )
                # Publish pending work before making the item visible to the
                # worker. A health reader can therefore never observe a dequeued
                # item before its pending reservation is counted.
                with self._mode5_trace_health_lock:
                    self._mode5_trace_health["pending_unpersisted"] += 1
                    try:
                        self._mode5_trace_queue.put_nowait(item)
                    except queue.Full:
                        self._mode5_trace_health["pending_unpersisted"] = max(
                            0, self._mode5_trace_health["pending_unpersisted"] - 1
                        )
                        self._mode5_trace_health["queue_full_drops"] += 1
                        self._mode5_trace_health["degraded"] = True
                        if dedup_key is not None:
                            if self._mode5_quote_trace_inflight.get(dedup_key) == reservation_id:
                                self._mode5_quote_trace_inflight.pop(dedup_key, None)
                            self._mode5_quote_trace_dropped.add(dedup_key)
                        return False
                    self._mode5_trace_health["enqueued"] += 1
                return True

    def _mode5_trace_writer_main(self) -> None:
        self._mode5_trace_health_changed(writer_status="RUNNING")
        try:
            while not self._mode5_trace_stop.is_set() or not self._mode5_trace_queue.empty():
                try:
                    item = self._mode5_trace_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                self._mode5_trace_health_increment(active_writes=1)
                try:
                    self._persist_mode5_trace_item(item)
                except Exception as exc:
                    self._finalize_mode5_trace_item_exception(item, exc)
                    logger.exception("Mode5 trace writer failed sequence=%s", item.trace_sequence)
                finally:
                    with self._mode5_trace_health_lock:
                        last_processed = self._mode5_trace_health["last_processed_sequence"]
                        self._mode5_trace_health["last_processed_sequence"] = max(
                            item.trace_sequence, last_processed or 0
                        )
                    self._mode5_trace_queue.task_done()
                    with self._mode5_trace_health_lock:
                        self._mode5_trace_health["active_writes"] = max(
                            0, self._mode5_trace_health["active_writes"] - 1
                        )
        finally:
            self._mode5_trace_health_changed(writer_status="STOPPED")
            self._mode5_trace_stopped.set()

    def _finalize_mode5_trace_item_exception(
        self, item: Mode5TraceQueueItem, exc: Exception
    ) -> None:
        """Account one unexpected item failure without poisoning the writer loop."""
        if item.dedup_key is not None:
            with self._mode5_quote_trace_state_lock:
                if self._mode5_quote_trace_inflight.get(item.dedup_key) == item.reservation_id:
                    self._mode5_quote_trace_inflight.pop(item.dedup_key, None)
                    self._mode5_quote_trace_dropped.add(item.dedup_key)
        with self._mode5_trace_health_lock:
            self._mode5_trace_health["append_failures"] += 1
            self._mode5_trace_health["last_error"] = f"writer:{type(exc).__name__}"
            self._mode5_trace_health["degraded"] = True

    def _persist_mode5_trace_item(self, item: Mode5TraceQueueItem) -> None:
        success = False
        last_failure: Optional[str] = None
        for _ in range(2):
            if item.dedup_key is not None:
                with self._mode5_quote_trace_state_lock:
                    if self._mode5_quote_trace_inflight.get(item.dedup_key) == item.reservation_id:
                        self._mode5_quote_trace_attempts[item.dedup_key] = (
                            self._mode5_quote_trace_attempts.get(item.dedup_key, 0) + 1
                        )
            try:
                with self._decision_trace_lock:
                    success = self._append_decision_trace_record_locked(item.serialized_record)
            except Exception as exc:
                success = False
                last_failure = f"append_exception:{type(exc).__name__}"
            if success:
                break
            self._mode5_trace_health_increment(append_failures=1)
            self._mode5_trace_health_changed(
                last_error=last_failure or "append_failed",
                degraded=True,
            )

        if item.dedup_key is not None:
            with self._mode5_quote_trace_state_lock:
                if self._mode5_quote_trace_inflight.get(item.dedup_key) == item.reservation_id:
                    self._mode5_quote_trace_inflight.pop(item.dedup_key, None)
                    if success:
                        self._mode5_quote_trace_emitted.add(item.dedup_key)
                    elif not success:
                        # A failed generic decision reason is also sticky for this
                        # generation; later quotes must not churn the writer.
                        self._mode5_quote_trace_dropped.add(item.dedup_key)
        if success:
            with self._mode5_trace_health_lock:
                self._mode5_trace_health["append_successes"] += 1
                self._mode5_trace_health["pending_unpersisted"] = max(
                    0, self._mode5_trace_health["pending_unpersisted"] - 1
                )
                last_seq = self._mode5_trace_health["last_persisted_sequence"]
                self._mode5_trace_health["last_persisted_sequence"] = max(
                    item.trace_sequence, last_seq or 0
                )
        else:
            logger.error(
                "Mode5 trace append exhausted retries sequence=%s reason_key=%s last_failure=%s",
                item.trace_sequence,
                item.dedup_key[3] if item.dedup_key is not None else "GENERIC",
                last_failure or "append_failed",
            )

    def get_mode5_trace_health_snapshot(self) -> dict[str, Any]:
        return self.get_mode5_trace_health()

    def shutdown_mode5_trace_writer(self, timeout_sec: float = 1.0) -> dict[str, Any]:
        """Stop accepting traces and boundedly drain the daemon writer."""
        timeout = max(0.0, float(timeout_sec))
        with self._mode5_trace_shutdown_lock:
            with self._mode5_quote_trace_state_lock:
                self._mode5_trace_accepting = False
            if not self._mode5_trace_stopped.is_set():
                self._mode5_trace_health_changed(writer_status="STOPPING")
                self._mode5_trace_stop.set()
                if self._mode5_trace_writer.is_alive():
                    self._mode5_trace_writer.join(timeout=timeout)
            snapshot = self.get_mode5_trace_health()
            if not self._mode5_trace_stopped.is_set() or snapshot["pending_unpersisted"]:
                snapshot["degraded"] = True
                snapshot["remaining_unpersisted"] = snapshot["pending_unpersisted"]
            else:
                snapshot["remaining_unpersisted"] = 0
            if self._mode5_trace_stopped.is_set():
                callback = self._mode5_trace_atexit_callback
                if callback is not None:
                    try:
                        atexit.unregister(callback)
                    except Exception:
                        logger.exception("Could not unregister Mode5 trace atexit callback")
                    else:
                        self._mode5_trace_atexit_callback = None
        if snapshot["degraded"]:
            logger.warning("Mode5 trace writer shutdown health: %s", snapshot)
        else:
            logger.info("Mode5 trace writer shutdown health: %s", snapshot)
        return snapshot

    def _shutdown_mode5_trace_writer_at_exit(self) -> None:
        self.shutdown_mode5_trace_writer(timeout_sec=0.25)

    def log_decision_trace(
        self,
        index_name: str,
        bar_time: Any,
        action: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp_ms: Optional[int] = None,
        candidate_generation: Optional[int] = None,
    ) -> None:
        """Queue structured decision telemetry without filesystem work on the caller."""
        try:
            bar_time_str = bar_time.strftime("%H:%M:%S") if hasattr(bar_time, "strftime") else str(bar_time)
            ts_ms = (
                timestamp_ms
                if isinstance(timestamp_ms, int) and not isinstance(timestamp_ms, bool) and timestamp_ms > 0
                else int(time.time() * 1000)
            )
            with self._lock:
                metadata = self._cached_rbfn_candidate_meta.get(index_name)
                generation = candidate_generation
                if generation is None and metadata is not None:
                    generation = metadata.generation
            record = {
                "event_type": "MODE5_DECISION_TRACE",
                "index_name": index_name,
                "bar_time": bar_time_str,
                "action": action,
                "reason": reason,
                "details": copy.deepcopy(details or {}),
                "timestamp_ms": ts_ms,
                "candidate_generation": generation,
            }
            key = self._mode5_trace_key(index_name, generation, reason, ts_ms)
            self._enqueue_mode5_trace_record(record, dedup_key=key)
        except Exception:
            # Trace serialization/queue errors must not alter the trading decision.
            self._mode5_trace_health_increment(oversize_drops=1)
            self._mode5_trace_health_changed(degraded=True, last_error="decision_trace_snapshot_failed")

    def _defer_mode5_decision_trace_locked(
        self,
        index_name: str,
        bar_time: Any,
        action: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp_ms: Optional[int] = None,
        candidate_generation: Optional[int] = None,
    ) -> None:
        """Snapshot and nonblockingly enqueue a decision trace under advisor lock."""
        if not self._lock._is_owned():
            raise RuntimeError("deferred Mode5 trace snapshot requires advisor lock")
        bar_time_str = bar_time.strftime("%H:%M:%S") if hasattr(bar_time, "strftime") else str(bar_time)
        ts_ms = (
            timestamp_ms
            if isinstance(timestamp_ms, int) and not isinstance(timestamp_ms, bool) and timestamp_ms > 0
            else int(time.time() * 1000)
        )
        try:
            details_snapshot = copy.deepcopy(details or {})
        except Exception as exc:
            # Trace snapshot failure must not escape into or alter the decision path.
            details_snapshot = {"trace_details_snapshot_error": type(exc).__name__}
        metadata = self._cached_rbfn_candidate_meta.get(index_name)
        generation = candidate_generation
        if generation is None and metadata is not None:
            generation = metadata.generation
        record = {
            "event_type": "MODE5_DECISION_TRACE",
            "index_name": index_name,
            "bar_time": bar_time_str,
            "action": action,
            "reason": reason,
            "details": details_snapshot,
            "timestamp_ms": ts_ms,
            "candidate_generation": generation,
        }
        key = self._mode5_trace_key(index_name, generation, reason, ts_ms)
        self._enqueue_mode5_trace_record(record, dedup_key=key)

    def _dispatch_reserved_entry_then_flush_traces(
        self, entry_dispatch_request: Optional[dict[str, Any]]
    ) -> None:
        """Dispatch an accepted reservation; trace writes continue asynchronously."""
        if self._lock._is_owned():
            raise RuntimeError("entry dispatch requires advisor lock release")
        if entry_dispatch_request is None:
            return
        if self.automated_dispatcher is not None:
            self.automated_dispatcher.on_apm_entry(**entry_dispatch_request)

    def record_veto(self, veto_category: str, reason: str = "") -> None:
        """Records a gate veto in the per-gate telemetry ledger and emits journal event."""
        with self._lock:
            self.total_veto_evaluations += 1
            if veto_category in self.veto_counters:
                self.veto_counters[veto_category] += 1
            else:
                self.veto_counters[veto_category] = 1

    def get_veto_telemetry_summary(self) -> dict[str, any]:
        """Returns per-gate veto frequencies and marginal survival metrics."""
        with self._lock:
            total = max(self.total_veto_evaluations, 1)
            freqs = {k: round(v / total, 4) for k, v in self.veto_counters.items()}
            return {
                "total_vetos": self.total_veto_evaluations,
                "accepted_trades": self.accepted_trade_count,
                "counters": dict(self.veto_counters),
                "frequencies": freqs,
            }

    @property
    def latest_spot(self) -> float:
        with self._lock:
            return self.spots.get("NIFTY", 0.0)

    def is_eod_entry_frozen(self, check_time: Optional[dt_time] = None) -> bool:
        """Evaluates whether current session time is in late-day entry freeze (>= 15:00:00)."""
        t = check_time or datetime.now(ZoneInfo("Asia/Kolkata")).time()
        return t >= self.eod_entry_freeze_time

    @staticmethod
    def _source_timestamp_exceeds_future_skew(timestamp_ms: int) -> bool:
        """Fail closed when a source timestamp exceeds the configured future-clock allowance."""
        try:
            max_skew_sec = float(app_config.MAX_CLOCK_SKEW_SEC)
            if not math.isfinite(max_skew_sec) or max_skew_sec < 0:
                return True
            return (float(timestamp_ms) - (time.time() * 1000.0)) > max_skew_sec * 1000.0
        except (AttributeError, TypeError, ValueError, OverflowError):
            return True

    @staticmethod
    def _canonical_option_instrument_key(index_name: str, raw_key: Any) -> Optional[str]:
        """Return a validated Upstox FO instrument key or None; display symbols are not identities."""
        expected_prefix = {
            "NIFTY": "NSE_FO",
            "BANKNIFTY": "NSE_FO",
            "SENSEX": "BSE_FO",
        }.get(index_name)
        if expected_prefix is None or not isinstance(raw_key, str):
            return None
        parts = raw_key.split("|")
        if len(parts) != 2 or parts[0] != expected_prefix or not parts[1]:
            return None
        suffix = parts[1]
        if not all(char.isascii() and (char.isalnum() or char in "_-") for char in suffix):
            return None
        suffix_upper = suffix.upper()
        embedded_underlying = None
        if suffix_upper.startswith("BANKNIFTY"):
            embedded_underlying = "BANKNIFTY"
        elif suffix_upper.startswith("SENSEX"):
            embedded_underlying = "SENSEX"
        elif suffix_upper.startswith("NIFTY"):
            embedded_underlying = "NIFTY"
        if embedded_underlying is not None and embedded_underlying != index_name:
            return None
        return raw_key

    @staticmethod
    def _resolve_option_index_from_display_symbol(raw_symbol: Any) -> Optional[str]:
        """Resolve supported space-delimited option display symbols; compact unknown forms fail closed."""
        if not isinstance(raw_symbol, str):
            return None
        symbol = raw_symbol.strip().upper()
        for root in ("BANKNIFTY", "SENSEX", "NIFTY"):
            if symbol.startswith(root) and len(symbol) > len(root) and symbol[len(root)].isspace():
                return root
        return None

    def seed_prior_day_levels(
        self,
        index_name: str,
        pdh: float,
        pdl: float,
        pdc: float,
        session_date: Optional[date] = None,
        atr_20: Optional[float] = None,
    ) -> bool:
        """Seeds and validates previous day reference levels for an index.
        
        Fail-closed: if pdh <= pdl or pdl <= 0, verified is False and levels are rejected.
        """
        resolved_atr = float(atr_20) if atr_20 is not None else None
        if resolved_atr is None or resolved_atr <= 0.0:
            pdr = float(pdh) - float(pdl)
            floor, ceiling = self.INDEX_ATR_BOUNDS.get(index_name, (130.0, 300.0))
            resolved_atr = max(floor, min(pdr, ceiling))

        levels = PriorDayReferenceLevels(
            index_name=index_name,
            pdh=float(pdh),
            pdl=float(pdl),
            pdc=float(pdc),
            session_date=session_date,
            atr_20=resolved_atr,
            verified=False,
        )
        if not levels.validate():
            logger.warning(
                f"[{index_name}] Invalid prior-day levels: pdh={pdh:.2f}, pdl={pdl:.2f}, pdc={pdc:.2f} (fail-closed, verified=False)"
            )
            self.prior_day_levels[index_name] = levels
            return False

        levels.verified = True
        self.prior_day_levels[index_name] = levels
        logger.info(
            f"[{index_name}] Successfully seeded verified prior-day levels: PDH={pdh:.2f}, PDL={pdl:.2f}, PDC={pdc:.2f}, ATR_20={resolved_atr:.2f}"
        )
        return True

    def _invalidate_optionmate_levels(self, index_name: Optional[str] = None) -> None:
        """Deprecate cached ground-truth levels and signals after invalid reload input."""
        names = [index_name] if index_name in self.rbfn_grids_frozen else list(self.rbfn_grids_frozen)
        with self._lock:
            for idx in names:
                self._ground_truth_required[idx] = True
                grid = self.cached_rbfn_grids.get(idx)
                if grid is not None and hasattr(grid, "is_ground_truth"):
                    try:
                        object.__setattr__(grid, "is_ground_truth", False)
                    except Exception:
                        pass
                self.cached_rbfn_grids[idx] = None
                self.rbfn_grids_frozen[idx] = False
                self._clear_cached_rbfn_candidate_locked(idx, "LEVELS_INVALIDATED")

    def _has_valid_ground_truth_grid(self, index_name: str, session_day: date) -> bool:
        grid = self.cached_rbfn_grids.get(index_name)
        return bool(
            grid is not None
            and self.rbfn_grids_frozen.get(index_name, False)
            and getattr(grid, "is_ground_truth", False)
            and getattr(grid, "date", None) == session_day.isoformat()
        )

    def inject_optionmate_levels(
        self,
        index_name: str,
        trend_decider: float,
        rp1_upper: float,
        rp2_upper: float,
        rp1_lower: float,
        rp2_lower: float,
        spot_open: Optional[float] = None,
        date_str: Optional[str] = None,
    ) -> bool:
        """Injects exact ground-truth OptionMate indicator levels (from TradingView / user).
        
        Freezes the RBFN grid with exact values to bypass heuristic estimation.
        Ensures sub-millisecond execution synchronization with official OptionMate indicators.
        """
        if index_name not in self._ground_truth_required:
            return False
        with self._lock:
            self._ground_truth_required[index_name] = True
        try:
            d_str = date_str or datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
            payload_day = date.fromisoformat(d_str)
            active_day = self._rp2_session_dates.get(index_name)
            expected_day = active_day or datetime.now(ZoneInfo("Asia/Kolkata")).date()
            expected_text = self._ground_truth_session_dates.get(index_name)
            if expected_text:
                expected_day = date.fromisoformat(expected_text)
            if payload_day < expected_day:
                # A parseable prior-session injection is stale and cannot replace
                # a valid current grid. With no valid grid, the latch stays set.
                with self._lock:
                    current_grid_valid = self._has_valid_ground_truth_grid(index_name, expected_day)
                if not current_grid_valid:
                    self._invalidate_optionmate_levels(index_name)
                return False
            if payload_day > expected_day:
                raise ValueError("OptionMate levels are for a future session")
            s_open = float(spot_open) if spot_open and spot_open > 0 else float(trend_decider)
            td = float(trend_decider)
            r1_u = float(rp1_upper)
            r2_u = float(rp2_upper)
            r1_l = float(rp1_lower)
            r2_l = float(rp2_lower)

            if not all(math.isfinite(v) and v > 0 for v in (s_open, td, r1_u, r2_u, r1_l, r2_l)):
                raise ValueError("OptionMate levels must be finite and positive")

            # Basic sanity assertions
            if not (r2_l < r1_l < td < r1_u < r2_u):
                logger.error(
                    f"[{index_name}] Invalid OptionMate grid hierarchy: "
                    f"RP2_L={r2_l} < RP1_L={r1_l} < TD={td} < RP1_U={r1_u} < RP2_U={r2_u} failed!"
                )
                self._invalidate_optionmate_levels(index_name)
                return False

            step_size = 100.0 if index_name in {"SENSEX", "BANKNIFTY"} else 50.0
            if index_name == "SENSEX":
                target_call = round(r2_u / step_size) * step_size
                target_put = round(r2_l / step_size) * step_size
                grid = SensexOptionMateGrid(
                    date=d_str,
                    spot_open=round(s_open, 2),
                    prev_close=round(s_open, 2),
                    atr_14=round(r2_u - r2_l, 2),
                    vix=14.0,
                    trend_decider=round(td, 2),
                    rp1_upper=round(r1_u, 2),
                    rp2_upper=round(r2_u, 2),
                    rp1_lower=round(r1_l, 2),
                    rp2_lower=round(r2_l, 2),
                    target_call_strike=float(target_call),
                    target_put_strike=float(target_put),
                    sustainable_price_anchor=30.0,
                    dte=0,
                    is_ground_truth=True,
                )
            else:
                call_strike = round(r1_u / step_size) * step_size
                put_strike = round(r1_l / step_size) * step_size
                bias = "BULL" if s_open >= td else "BEAR"
                target_strike = call_strike if bias == "BULL" else put_strike
                grid = OptionMateGrid(
                    date=d_str,
                    spot_open=round(s_open, 2),
                    trend_decider=round(td, 2),
                    rp1_upper=round(r1_u, 2),
                    rp2_upper=round(r2_u, 2),
                    rp1_lower=round(r1_l, 2),
                    rp2_lower=round(r2_l, 2),
                    call_strike=float(call_strike),
                    put_strike=float(put_strike),
                    recommended_bias=bias,
                    target_strike=float(target_strike),
                    is_ground_truth=True,
                )

            with self._lock:
                self.cached_rbfn_grids[index_name] = grid
                self.rbfn_grids_frozen[index_name] = True

            logger.info(
                f"[{index_name}] 🎯 Injected Ground-Truth OptionMate Levels: "
                f"TD={td:.2f}, RP1_U={r1_u:.2f}, RP2_U={r2_u:.2f}, RP1_L={r1_l:.2f}, RP2_L={r2_l:.2f} (Grid Frozen)"
            )
            return True
        except Exception as e:
            logger.error(f"[{index_name}] Failed to inject OptionMate levels: {e}")
            self._invalidate_optionmate_levels(index_name)
            return False

    def check_and_reload_optionmate_levels(
        self,
        levels_path: Optional[Path] = None,
        force: bool = False,
        session_date: Optional[str] = None,
    ) -> dict[str, bool]:
        """Dynamically reloads and injects verified OptionMate indicator levels from runtime JSON.

        ARCH-SENTINEL-OPTIONMATE-HARDENING-001:
        - Thread-safe using self._om_levels_lock.
        - Rate-limited to at most once per 1.0s using time.monotonic() unless force=True.
        - Reads mtime of runtime/optionmate_daily_levels.json (or passed levels_path).
        - Strictly verifies that level payload date matches session_date (or today_str).
        - Fails closed if date does not match or payload is invalid, returning {idx: False}.
        - Injects validated levels via self.inject_optionmate_levels(...) returning {idx: True}.
        """
        # Invoking ingestion opts every supported index into required-level mode
        # before throttle checks, file reads, or payload validation.
        with self._lock:
            for idx_name in self._ground_truth_required:
                self._ground_truth_required[idx_name] = True

        now_mono = time.monotonic()
        if not force and (now_mono - self._last_om_check_mono < 1.0):
            return {}

        target_file = levels_path or (Path("runtime") / "optionmate_daily_levels.json")
        expected_date = session_date or datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        try:
            expected_day = date.fromisoformat(expected_date)
        except (TypeError, ValueError):
            self._invalidate_optionmate_levels()
            return {idx_name: False for idx_name in self._ground_truth_required}
        with self._lock:
            for idx_name in self._ground_truth_session_dates:
                self._ground_truth_session_dates[idx_name] = expected_day.isoformat()

        with self._om_levels_lock:
            # Re-check rate limit inside lock in case another thread just completed reload
            now_mono = time.monotonic()
            if not force and (now_mono - self._last_om_check_mono < 1.0):
                return {}
            self._last_om_check_mono = now_mono

            if not target_file.exists():
                self._invalidate_optionmate_levels()
                return {}

            try:
                stat_res = target_file.stat()
                mtime = stat_res.st_mtime
                if not force and mtime <= self._last_om_levels_mtime:
                    return {}

                with open(target_file, "r", encoding="utf-8") as f:
                    levels_dict = json.load(f)

                if not isinstance(levels_dict, dict):
                    logger.error(f"[OptionMate Reload] Invalid JSON root format in {target_file}")
                    self._invalidate_optionmate_levels()
                    return {}

                reload_results: dict[str, bool] = {}
                expected_indices = set(self.cached_rbfn_grids)
                supplied_indices = set(levels_dict)
                for missing_index in expected_indices - supplied_indices:
                    self._invalidate_optionmate_levels(missing_index)
                    reload_results[missing_index] = False
                if supplied_indices - expected_indices:
                    logger.error(f"[OptionMate Reload] Unknown index keys: {sorted(supplied_indices - expected_indices)}")
                    self._invalidate_optionmate_levels()
                    return {name: False for name in supplied_indices}
                for idx_name, idx_payload in levels_dict.items():
                    if not isinstance(idx_payload, dict):
                        self._invalidate_optionmate_levels(idx_name)
                        reload_results[idx_name] = False
                        continue

                    # Reject stale prior-day candidates without poisoning an
                    # already valid current-session grid.
                    payload_date = idx_payload.get("date")
                    try:
                        payload_day = date.fromisoformat(str(payload_date))
                    except (TypeError, ValueError):
                        payload_day = None
                    if payload_day != expected_day:
                        logger.warning(
                            f"[{idx_name}] Stale OptionMate levels rejected! "
                            f"Payload date '{payload_date}' != expected session date '{expected_date}'"
                        )
                        reload_results[idx_name] = False
                        if payload_day is not None and payload_day < expected_day:
                            with self._lock:
                                current_grid_valid = self._has_valid_ground_truth_grid(idx_name, expected_day)
                            if not current_grid_valid:
                                self._invalidate_optionmate_levels(idx_name)
                        else:
                            self._invalidate_optionmate_levels(idx_name)
                        continue

                    td = idx_payload.get("trend_decider")
                    r1_u = idx_payload.get("rp1_upper")
                    r2_u = idx_payload.get("rp2_upper")
                    r1_l = idx_payload.get("rp1_lower")
                    r2_l = idx_payload.get("rp2_lower")
                    s_open = idx_payload.get("spot_open")

                    if any(v is None for v in (td, r1_u, r2_u, r1_l, r2_l)):
                        logger.error(f"[{idx_name}] Incomplete OptionMate level attributes in {target_file}")
                        self._invalidate_optionmate_levels(idx_name)
                        reload_results[idx_name] = False
                        continue

                    ok = self.inject_optionmate_levels(
                        index_name=idx_name,
                        trend_decider=float(td),
                        rp1_upper=float(r1_u),
                        rp2_upper=float(r2_u),
                        rp1_lower=float(r1_l),
                        rp2_lower=float(r2_l),
                        spot_open=float(s_open) if s_open is not None else None,
                        date_str=payload_date,
                    )
                    reload_results[idx_name] = ok
                    if not ok:
                        self._invalidate_optionmate_levels(idx_name)

                self._last_om_levels_mtime = mtime
                return reload_results
            except Exception as e:
                logger.error(f"[OptionMate Reload] Error reading levels file {target_file}: {e}")
                self._invalidate_optionmate_levels()
                return {}

    def _replace_mode5_trace_generation_locked(self, index_name: str, generation: Optional[int]) -> None:
        """Publish generation and clear trace state while advisor lock is held."""
        with self._mode5_quote_trace_state_lock:
            self._mode5_quote_trace_emitted = {
                key for key in self._mode5_quote_trace_emitted if key[1] != index_name
            }
            self._mode5_quote_trace_attempts = {
                key: attempts for key, attempts in self._mode5_quote_trace_attempts.items()
                if key[1] != index_name
            }
            self._mode5_quote_trace_inflight = {
                key: reservation
                for key, reservation in self._mode5_quote_trace_inflight.items()
                if key[1] != index_name
            }
            self._mode5_quote_trace_dropped = {
                key for key in self._mode5_quote_trace_dropped if key[1] != index_name
            }
            self._mode5_quote_trace_active_generation[index_name] = generation

    def _clear_cached_rbfn_candidate_locked(self, index_name: str, status: str = "CLEARED") -> None:
        """Invalidate a candidate generation and its process-local age metadata."""
        if index_name not in self._cached_rbfn_generation:
            return
        self._cached_rbfn_generation[index_name] += 1
        self.cached_rbfn_signals[index_name] = None
        self._cached_rbfn_candidate_meta[index_name] = None
        self._replace_mode5_trace_generation_locked(index_name, None)

    def _cache_rbfn_signal_locked(
        self, index_name: str, signal: CachedRBFNAuctionSignal, epoch_5min: int
    ) -> None:
        """Atomically replace the signal and its decision-availability metadata."""
        self._cached_rbfn_generation[index_name] += 1
        generation = self._cached_rbfn_generation[index_name]
        try:
            session_day = datetime.fromtimestamp(
                signal.timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
            ).date()
            boundary_ms = (epoch_5min + 1) * 300_000
        except (OverflowError, OSError, TypeError, ValueError):
            self.cached_rbfn_signals[index_name] = None
            self._cached_rbfn_candidate_meta[index_name] = None
            self._replace_mode5_trace_generation_locked(index_name, None)
            return
        self.cached_rbfn_signals[index_name] = signal
        actionable = (
            signal.is_active
            and not signal.is_vetoed
            and signal.action in {"BUY_CALL", "BUY_PUT"}
        )
        self._cached_rbfn_candidate_meta[index_name] = CachedRBFNCandidateMetadata(
            generation=generation,
            issued_monotonic_ns=time.monotonic_ns(),
            boundary_timestamp_ms=boundary_ms,
            session_day=session_day,
            status="AVAILABLE" if actionable else "SUPERSEDED_BY_ABSTENTION",
        )
        self._replace_mode5_trace_generation_locked(index_name, generation if actionable else None)

    def _emit_mode5_quote_suppression(
        self,
        index_name: str,
        instrument_key: str,
        signal: CachedRBFNAuctionSignal,
        metadata: CachedRBFNCandidateMetadata,
        depth: UpstoxLevel5DepthRecord,
        reason: str,
        validated_decision_timestamp_ms: int,
    ) -> bool:
        """Reserve under state locks, append without them, then reconcile safely."""
        if reason not in {
            "MODE5_QUOTE_BEFORE_BAR_BOUNDARY",
            "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE",
        }:
            return False
        dedup_key = (
            metadata.session_day.isoformat(),
            index_name,
            metadata.generation,
            reason,
        )
        bar_time = signal.bar_time.strftime("%H:%M:%S") if hasattr(signal.bar_time, "strftime") else str(signal.bar_time)
        record = {
            "event_type": "MODE5_QUOTE_SUPPRESSED",
            "action": "ABSTAIN",
            "decision": "RETAIN_CANDIDATE",
            "index_name": index_name,
            "canonical_instrument": instrument_key,
            "candidate_generation": metadata.generation,
            "candidate_action": signal.action,
            "candidate_setup": signal.setup_reason,
            "candidate_bar_time": bar_time,
            "boundary_timestamp_ms": metadata.boundary_timestamp_ms,
            "issued_monotonic_ns": metadata.issued_monotonic_ns,
            "quote_exchange_timestamp_ms": depth.exchange_timestamp_ms,
            "ingress_monotonic_ns": depth.ingress_monotonic_ns,
            "validated_decision_timestamp_ms": validated_decision_timestamp_ms,
            "timestamp_ms": validated_decision_timestamp_ms,
            "reason": reason,
        }
        return self._enqueue_mode5_trace_record(
            record,
            dedup_key=dedup_key,
            suppression_record=True,
            expected_signal=signal,
            expected_generation=metadata.generation,
        )

    def _candidate_snapshot_locked(
        self, index_name: str, ttl_seconds: float = 300.0, now_ns: Optional[int] = None
    ) -> tuple[Optional[CachedRBFNAuctionSignal], Optional[CachedRBFNCandidateMetadata]]:
        signal = self.cached_rbfn_signals.get(index_name)
        metadata = self._cached_rbfn_candidate_meta.get(index_name)
        if signal is None or metadata is None or metadata.status != "AVAILABLE":
            return None, None
        current_ns = time.monotonic_ns() if now_ns is None else now_ns
        if isinstance(current_ns, bool) or not isinstance(current_ns, int) or current_ns < metadata.issued_monotonic_ns:
            self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_MONOTONIC_CLOCK")
            return None, None
        age_ns = current_ns - metadata.issued_monotonic_ns
        ttl_ns = int(ttl_seconds * 1_000_000_000)
        if age_ns > ttl_ns:
            logger.info("[%s] Expiring Mode5 candidate generation=%s after %.3fs", index_name, metadata.generation, age_ns / 1e9)
            self._clear_cached_rbfn_candidate_locked(index_name, "EXPIRED")
            return None, None
        if not signal.is_active or signal.is_vetoed or signal.action not in {"BUY_CALL", "BUY_PUT"}:
            return None, None
        return signal, metadata

    def _option_quote_identity(
        self,
        index_name: str,
        depth: UpstoxLevel5DepthRecord,
        *,
        wall_now_ms: Optional[int] = None,
        monotonic_now_ns: Optional[int] = None,
    ) -> tuple[bool, str, Optional[date], Optional[str], Optional[tuple[int, int]]]:
        """Validate option quote source/receipt clocks without mutating advisor state."""
        timestamp_ms = depth.exchange_timestamp_ms
        ingress_ns = depth.ingress_monotonic_ns
        sequence_id = depth.sequence_id
        if (
            isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int) or timestamp_ms <= 0
            or isinstance(ingress_ns, bool) or not isinstance(ingress_ns, int) or ingress_ns <= 0
            or isinstance(sequence_id, bool) or not isinstance(sequence_id, int) or sequence_id <= 0
        ):
            return False, "OPTION_DEPTH_INVALID_CLOCK_OR_SEQUENCE", None, None, None
        try:
            max_age_sec = float(app_config.MAX_QUOTE_AGE_SEC)
            max_skew_sec = float(app_config.MAX_CLOCK_SKEW_SEC)
            if not math.isfinite(max_age_sec) or max_age_sec <= 0 or not math.isfinite(max_skew_sec) or max_skew_sec < 0:
                return False, "OPTION_DEPTH_INVALID_FRESHNESS_CONFIG", None, None, None
            current_wall_ms = int(time.time() * 1000) if wall_now_ms is None else wall_now_ms
            current_monotonic_ns = time.monotonic_ns() if monotonic_now_ns is None else monotonic_now_ns
            source_age_sec = (current_wall_ms - timestamp_ms) / 1000.0
            ingress_age_sec = (current_monotonic_ns - ingress_ns) / 1_000_000_000.0
            if source_age_sec > max_age_sec or source_age_sec < -max_skew_sec:
                return False, "OPTION_DEPTH_SOURCE_STALE_OR_FUTURE", None, None, None
            if ingress_age_sec < 0 or ingress_age_sec > max_age_sec:
                return False, "OPTION_DEPTH_INGRESS_STALE_OR_FUTURE", None, None, None
            quote_day = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).date()
            current_day = datetime.fromtimestamp(current_wall_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).date()
            if quote_day != current_day:
                return False, "OPTION_DEPTH_WRONG_SESSION", None, None, None
        except (AttributeError, OverflowError, OSError, TypeError, ValueError):
            return False, "OPTION_DEPTH_INVALID_CLOCK_OR_FRESHNESS", None, None, None
        instrument_key = self._canonical_option_instrument_key(index_name, depth.token)
        if instrument_key is None:
            return False, "OPTION_DEPTH_INVALID_INSTRUMENT_KEY", quote_day, None, None
        return True, "OPTION_DEPTH_VALID", quote_day, instrument_key, (timestamp_ms, sequence_id)

    def _record_option_depth_order(
        self, index_name: str, quote_day: date, instrument_key: str, source_order: tuple[int, int]
    ) -> bool:
        """Commit a strictly increasing per-token event watermark under the advisor lock."""
        with self._lock:
            known_day = self._rp2_session_dates.get(index_name)
            if known_day is not None and quote_day < known_day:
                return False
            if known_day is not None and quote_day > known_day:
                self._reset_rp2_state_for_session_locked(index_name, quote_day)
            elif known_day is None:
                self._reset_rp2_state_for_session_locked(index_name, quote_day)
            token_watermarks = self._option_depth_watermarks.setdefault(index_name, {})
            watermark_days = {row[0] for row in token_watermarks.values()}
            if watermark_days and quote_day not in watermark_days:
                token_watermarks.clear()
            candidate_meta = self._cached_rbfn_candidate_meta.get(index_name)
            if candidate_meta is not None and quote_day != candidate_meta.session_day:
                self._clear_cached_rbfn_candidate_locked(index_name, "OPTION_SESSION_ROLLOVER")
                token_watermarks.clear()
            previous = token_watermarks.get(instrument_key)
            current = (source_order[0], source_order[1])
            if previous is not None and previous[0] == quote_day and current <= (previous[1], previous[2]):
                return False
            token_watermarks[instrument_key] = (quote_day, current[0], current[1])
            return True

    def _candidate_for_option_depth(
        self, index_name: str, depth: UpstoxLevel5DepthRecord, quote_day: date, instrument_key: str,
        source_order: tuple[int, int], now_ns: Optional[int] = None,
        validated_decision_timestamp_ms: Optional[int] = None,
    ) -> tuple[Optional[CachedRBFNAuctionSignal], Optional[int]]:
        suppressions: list[tuple[CachedRBFNAuctionSignal, CachedRBFNCandidateMetadata, str]] = []
        result: tuple[Optional[CachedRBFNAuctionSignal], Optional[int]] = (None, None)
        with self._lock:
            signal, metadata = self._candidate_snapshot_locked(index_name, now_ns=now_ns)
            if signal is None or metadata is None:
                return result
            try:
                depth_day = datetime.fromtimestamp(
                    depth.exchange_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
                ).date()
            except (OverflowError, OSError, TypeError, ValueError):
                return result
            if depth_day != metadata.session_day or quote_day != metadata.session_day:
                return result
            if depth.exchange_timestamp_ms < metadata.boundary_timestamp_ms:
                suppressions.append((signal, metadata, "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"))
            if depth.ingress_monotonic_ns <= metadata.issued_monotonic_ns:
                suppressions.append((signal, metadata, "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE"))
            if not suppressions and self._option_depth_watermarks.get(index_name, {}).get(instrument_key) == (
                quote_day, source_order[0], source_order[1]
            ):
                result = (signal, metadata.generation)
        if suppressions:
            decision_ts_ms = (
                int(time.time() * 1000)
                if validated_decision_timestamp_ms is None
                else validated_decision_timestamp_ms
            )
            for signal, metadata, reason in suppressions:
                self._emit_mode5_quote_suppression(
                    index_name=index_name,
                    instrument_key=instrument_key,
                    signal=signal,
                    metadata=metadata,
                    depth=depth,
                    reason=reason,
                    validated_decision_timestamp_ms=decision_ts_ms,
                )
        return result

    def _final_candidate_authorization_locked(
        self,
        index_name: str,
        generation: int,
        depth: UpstoxLevel5DepthRecord,
        quote_day: date,
        instrument_key: str,
        source_order: tuple[int, int],
        now_ns: int,
        wall_now_ms: Optional[int] = None,
    ) -> tuple[bool, str]:
        signal, metadata = self._candidate_snapshot_locked(index_name, now_ns=now_ns)
        if signal is None or metadata is None or metadata.generation != generation:
            return False, "MODE5_CANDIDATE_SUPERSEDED_OR_EXPIRED"
        if (
            metadata.session_day != quote_day
            or depth.exchange_timestamp_ms < metadata.boundary_timestamp_ms
            or depth.ingress_monotonic_ns <= metadata.issued_monotonic_ns
            or self._option_depth_watermarks.get(index_name, {}).get(instrument_key)
            != (quote_day, source_order[0], source_order[1])
        ):
            return False, "MODE5_QUOTE_NO_LONGER_ELIGIBLE"
        quote_valid, quote_reason, current_day, current_key, current_order = self._option_quote_identity(
            index_name, depth, wall_now_ms=wall_now_ms, monotonic_now_ns=now_ns
        )
        if not quote_valid or current_day != quote_day or current_key != instrument_key or current_order != source_order:
            return False, quote_reason
        return True, "MODE5_CANDIDATE_AUTHORIZED"

    def _consume_cached_rbfn_candidate_locked(self, index_name: str, generation: int, status: str) -> bool:
        metadata = self._cached_rbfn_candidate_meta.get(index_name)
        if metadata is None or metadata.generation != generation:
            return False
        self.cached_rbfn_signals[index_name] = None
        self._cached_rbfn_candidate_meta[index_name] = CachedRBFNCandidateMetadata(
            generation=metadata.generation,
            issued_monotonic_ns=metadata.issued_monotonic_ns,
            boundary_timestamp_ms=metadata.boundary_timestamp_ms,
            session_day=metadata.session_day,
            status=status,
        )
        self._replace_mode5_trace_generation_locked(index_name, None)
        return True

    def get_valid_cached_rbfn_signal(
        self,
        index_name: str,
        current_timestamp_ms: Optional[int] = None,
        ttl_seconds: float = 300.0,
    ) -> Optional[CachedRBFNAuctionSignal]:
        """Return an unconsumed candidate while its process-local monotonic TTL remains valid.

        `current_timestamp_ms` remains for API compatibility; source event time is no
        longer used to measure candidate lifetime.
        """
        with self._lock:
            signal, _ = self._candidate_snapshot_locked(index_name, ttl_seconds=ttl_seconds)
            return signal

    def clamp_atr(self, index_name: str, raw_atr: float) -> float:
        """Clamps ATR to index-specific floor (NIFTY: 25.0, BANKNIFTY: 100.0, SENSEX: 150.0)."""
        floor = self.index_atr_floors.get(index_name, 25.0)
        return max(floor, float(raw_atr))

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

    def on_tick(self, tick: UpstoxTickRecord) -> None:
        """Handle incoming tick for NIFTY, SENSEX, and BANKNIFTY."""
        with self._lock:
            token = tick.token
            idx_key = None
            if "Nifty 50" in token:
                idx_key = "NIFTY"
            elif "SENSEX" in token:
                idx_key = "SENSEX"
            elif "Nifty Bank" in token:
                idx_key = "BANKNIFTY"

            if idx_key is not None and not self._update_spot(
                idx_key, tick.ltp, tick.exchange_timestamp_ms
            ):
                return

            if idx_key is not None:
                # Update upstream regime router ring buffer and state via discrete 1-minute SyntheticBarBucket
                router = self.regime_routers.get(idx_key)
                bucket = self.bar_buckets.get(idx_key)
                if router is not None and bucket is not None:
                    ts_ms = tick.exchange_timestamp_ms
                    epoch_sec = ts_ms / 1000.0
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
                        bar_time = datetime.fromtimestamp(bucket.bucket_epoch_min * 60, tz=ZoneInfo("Asia/Kolkata")).time()
                        router.on_bar_close(
                            bar_close=bucket.close,
                            bar_volume=bucket.volume,
                            cvd_delta=0.0,
                            timestamp_ms=bucket.last_timestamp_ms,
                            bar_time=bar_time,
                        )
                        # Wire dynamic 1-minute synthetic bar range updates into bar_true_ranges and observer ATR
                        bar_tr = max(1.0, bucket.high - bucket.low)
                        if idx_key in self.bar_true_ranges:
                            self.bar_true_ranges[idx_key].append(bar_tr)
                            obs = self.wall_observers.get(idx_key)
                            if obs is not None:
                                avg_tr = sum(self.bar_true_ranges[idx_key]) / len(self.bar_true_ranges[idx_key])
                                obs.update_atr(max(1.0, round(avg_tr, 2)))
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

                # Mode 5: Discrete 5-minute bar accumulator for RBFN Auction Engine
                bucket_5m = self.bar_buckets_5m.get(idx_key)
                if bucket_5m is not None:
                    ts_ms = tick.exchange_timestamp_ms
                    epoch_sec = ts_ms / 1000.0
                    epoch_5min = int(epoch_sec // 300)

                    if idx_key not in self.evaluated_5m_epochs:
                        self.evaluated_5m_epochs[idx_key] = set()

                    if bucket_5m.bucket_epoch_5min == -1:
                        # Initialize first 5m bucket
                        bucket_5m.bucket_epoch_5min = epoch_5min
                        bucket_5m.open = tick.ltp
                        bucket_5m.high = tick.ltp
                        bucket_5m.low = tick.ltp
                        bucket_5m.close = tick.ltp
                        bucket_5m.volume = float(tick.volume)
                        bucket_5m.tick_count = 1
                        bucket_5m.last_timestamp_ms = ts_ms
                    elif epoch_5min > bucket_5m.bucket_epoch_5min:
                        # 5-minute boundary crossed: finalize completed bar
                        completed_epoch = bucket_5m.bucket_epoch_5min
                        if completed_epoch not in self.evaluated_5m_epochs[idx_key]:
                            bar_time = datetime.fromtimestamp((completed_epoch + 1) * 300, tz=ZoneInfo("Asia/Kolkata")).time()
                            self._on_5m_bar_close(
                                index_name=idx_key,
                                bar_open=bucket_5m.open,
                                bar_high=bucket_5m.high,
                                bar_low=bucket_5m.low,
                                bar_close=bucket_5m.close,
                                bar_volume=bucket_5m.volume,
                                bar_time=bar_time,
                                timestamp_ms=bucket_5m.last_timestamp_ms,
                                epoch_5min=completed_epoch,
                            )
                            self.evaluated_5m_epochs[idx_key].add(completed_epoch)
                        # Start new 5m bucket
                        bucket_5m.bucket_epoch_5min = epoch_5min
                        bucket_5m.open = tick.ltp
                        bucket_5m.high = tick.ltp
                        bucket_5m.low = tick.ltp
                        bucket_5m.close = tick.ltp
                        bucket_5m.volume = float(tick.volume)
                        bucket_5m.tick_count = 1
                        bucket_5m.last_timestamp_ms = ts_ms
                    else:
                        # Accumulate within current 5-minute bar
                        if bucket_5m.bucket_epoch_5min not in self.evaluated_5m_epochs[idx_key]:
                            bucket_5m.high = max(bucket_5m.high, tick.ltp)
                            bucket_5m.low = min(bucket_5m.low, tick.ltp)
                            bucket_5m.close = tick.ltp
                            bucket_5m.volume += float(tick.volume)
                            bucket_5m.tick_count += 1
                            bucket_5m.last_timestamp_ms = ts_ms

    def reconcile_5m_bars(self, wall_clock_time: Optional[datetime] = None) -> list[int]:
        """Clock-driven reconciler for 5-minute bars to handle low-tick/stale stream periods.

        Checks all tracked indices under self._lock. If wall_clock_time has crossed into a new
        5-minute epoch (current_epoch_5min > bucket_5m.bucket_epoch_5min), finalizes the pending bar
        and evaluates Mode 5 (OPTIONMATE_RBFN_AUCTION) idempotently, ensuring zero duplicate
        evaluations via self.evaluated_5m_epochs.

        Args:
            wall_clock_time: Optional reference datetime. Defaults to datetime.now().

        Returns:
            list[int]: List of unique completed 5-minute epoch IDs that were reconciled in this pass.
        """
        with self._lock:
            if wall_clock_time is None:
                wall_clock_time = datetime.now(ZoneInfo("Asia/Kolkata"))
            elif wall_clock_time.tzinfo is None:
                wall_clock_time = wall_clock_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

            india_now = wall_clock_time.astimezone(ZoneInfo("Asia/Kolkata"))
            for idx_key, previous_day in self._rp2_session_dates.items():
                if previous_day is not None and india_now.date() > previous_day:
                    self._reset_rp2_state_for_session(idx_key, india_now.date())

            wall_clock_sec = wall_clock_time.timestamp()
            current_epoch_5min = int(wall_clock_sec // 300)
            reconciled_epochs: list[int] = []

            for idx_key, bucket_5m in self.bar_buckets_5m.items():
                if bucket_5m.bucket_epoch_5min != -1 and bucket_5m.tick_count > 0:
                    if current_epoch_5min > bucket_5m.bucket_epoch_5min:
                        completed_epoch = bucket_5m.bucket_epoch_5min
                        if idx_key not in self.evaluated_5m_epochs:
                            self.evaluated_5m_epochs[idx_key] = set()

                        if completed_epoch not in self.evaluated_5m_epochs[idx_key]:
                            bar_time = datetime.fromtimestamp((completed_epoch + 1) * 300, tz=ZoneInfo("Asia/Kolkata")).time()
                            self._on_5m_bar_close(
                                index_name=idx_key,
                                bar_open=bucket_5m.open,
                                bar_high=bucket_5m.high,
                                bar_low=bucket_5m.low,
                                bar_close=bucket_5m.close,
                                bar_volume=bucket_5m.volume,
                                bar_time=bar_time,
                                timestamp_ms=bucket_5m.last_timestamp_ms,
                                epoch_5min=completed_epoch,
                            )
                            self.evaluated_5m_epochs[idx_key].add(completed_epoch)
                            if completed_epoch not in reconciled_epochs:
                                reconciled_epochs.append(completed_epoch)

            result = reconciled_epochs
        return result

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

    @staticmethod
    def _empty_or_evidence(session_day: Optional[date] = None) -> dict[str, Any]:
        return {
            "session_date": session_day.isoformat() if session_day else None,
            "status": "UNSEEDED",
            "source": "NONE",
            "source_timestamp_ms": 0,
            "coverage_count": 0,
            "coverage_start_ms": 0,
            "coverage_end_ms": 0,
        }

    @staticmethod
    def _or_candles_digest(candles: list[list[Any]]) -> str:
        encoded = json.dumps(
            candles,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _new_or_reconciliation_ledger(session_day: date) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_date": session_day.isoformat(),
            "indices": {
                index_name: {
                    "attempt_count": 0,
                    "last_attempt_timestamp_ms": 0,
                }
                for index_name in ("NIFTY", "BANKNIFTY", "SENSEX")
            },
        }

    def _acquire_or_reconciliation_lock(self) -> tuple[int, bool]:
        """Acquire the persistent sidecar flock, reporting whether it was created."""
        lock_path = self.or_reconciliation_lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            lock_fd = os.open(lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            lock_fd = os.open(lock_path, flags)
            created = False
        try:
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise OSError("OR reconciliation lock is not a regular file")
            if created:
                os.fsync(lock_fd)
                self._fsync_or_reconciliation_directory(lock_path.parent)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            return lock_fd, created
        except Exception:
            os.close(lock_fd)
            raise

    @staticmethod
    def _fsync_or_reconciliation_directory(directory: Path) -> None:
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _write_or_reconciliation_ledger_locked(self, ledger: dict[str, Any]) -> None:
        """Atomically persist a ledger while its sidecar flock is held."""
        path = self.or_reconciliation_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            ledger,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            self._fsync_or_reconciliation_directory(path.parent)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _or_reconciliation_marker_identity(self, state: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "ledger_path": str(self.or_reconciliation_state_path.resolve()),
            "lock_path": str(self.or_reconciliation_lock_path.resolve()),
            "marker_path": str(self.or_reconciliation_initialized_path.resolve()),
            "state": state,
        }

    def _write_or_reconciliation_initialized_marker_locked(self, state: str, *, exclusive: bool) -> None:
        path = self.or_reconciliation_initialized_path
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= os.O_EXCL if exclusive else os.O_TRUNC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            payload = json.dumps(
                self._or_reconciliation_marker_identity(state),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._fsync_or_reconciliation_directory(path.parent)
        finally:
            if fd >= 0:
                os.close(fd)

    def _replace_or_reconciliation_marker_with_ready_locked(self) -> None:
        path = self.or_reconciliation_initialized_path
        payload = json.dumps(
            self._or_reconciliation_marker_identity("READY"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            ready_fd = os.open(path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(ready_fd)
            finally:
                os.close(ready_fd)
            self._fsync_or_reconciliation_directory(path.parent)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _read_or_reconciliation_initialized_marker_locked(self) -> Optional[dict[str, Any]]:
        path = self.or_reconciliation_initialized_path
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("OR reconciliation initialization marker is not a regular file")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict) or raw.get("state") != "READY":
            raise ValueError("OR reconciliation initialization marker is not READY")
        if raw != self._or_reconciliation_marker_identity("READY"):
            raise ValueError("OR reconciliation initialization marker identity mismatch")
        return raw

    def _validate_or_reconciliation_ledger(
        self, raw: Any, expected_day: date
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw.get("schema_version") != 1:
            raise ValueError("unsupported or malformed OR reconciliation ledger schema")
        try:
            ledger_day = date.fromisoformat(str(raw.get("session_date")))
        except (TypeError, ValueError) as exc:
            raise ValueError("malformed OR reconciliation ledger session date") from exc
        if ledger_day.isoformat() != raw.get("session_date"):
            raise ValueError("noncanonical OR reconciliation ledger session date")
        indices = raw.get("indices")
        expected_indices = {"NIFTY", "BANKNIFTY", "SENSEX"}
        if not isinstance(indices, dict) or set(indices) != expected_indices:
            raise ValueError("OR reconciliation ledger must contain exactly all supported indices")

        validated_indices: dict[str, dict[str, Any]] = {}
        for index_name, state in indices.items():
            if not isinstance(state, dict):
                raise ValueError("malformed OR reconciliation index state")
            attempts = state.get("attempt_count")
            last_attempt_ms = state.get("last_attempt_timestamp_ms")
            if (type(attempts) is not int or not 0 <= attempts <= self.OR_MAX_RETRY_ATTEMPTS
                    or type(last_attempt_ms) is not int or last_attempt_ms < 0
                    or (attempts == 0) != (last_attempt_ms == 0)):
                raise ValueError("invalid OR reconciliation attempt counters")
            normalized = {
                "attempt_count": attempts,
                "last_attempt_timestamp_ms": last_attempt_ms,
            }
            proof = state.get("completion_proof")
            if proof is not None:
                if not isinstance(proof, dict) or attempts <= 0:
                    raise ValueError("invalid OR completion proof")
                candles = proof.get("candles")
                digest = proof.get("sha256")
                if (not isinstance(candles, list) or len(candles) != 30
                        or not isinstance(digest, str) or len(digest) != 64
                        or self._or_candles_digest(candles) != digest):
                    raise ValueError("OR completion proof digest mismatch")
                parsed = self._parse_complete_v2_or_candles(candles, ledger_day)
                if parsed is None:
                    raise ValueError("OR completion proof failed exact coverage validation")
                expected_proof = {
                    "source": "UPSTOX_V2_1M_EXACT_30",
                    "coverage_count": parsed["coverage_count"],
                    "coverage_start_ms": parsed["coverage_start_ms"],
                    "coverage_end_ms": parsed["coverage_end_ms"],
                    "source_timestamp_ms": parsed["source_timestamp_ms"],
                }
                if any(proof.get(key) != value for key, value in expected_proof.items()):
                    raise ValueError("OR completion proof metadata mismatch")
                if parsed.get("normalized_candles") != candles:
                    raise ValueError("OR completion proof candles are not canonical")
                normalized["completion_proof"] = proof
            validated_indices[index_name] = normalized

        ledger = {
            "schema_version": 1,
            "session_date": ledger_day.isoformat(),
            "indices": validated_indices,
        }
        if ledger_day > expected_day:
            raise ValueError("stale OR event cannot move ledger session date backward")
        return ledger, validated_indices

    def _load_or_reconciliation_ledger_locked(
        self, expected_day: date, lock_created: bool
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        path = self.or_reconciliation_state_path
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        marker = self._read_or_reconciliation_initialized_marker_locked()
        try:
            ledger_fd = os.open(path, flags)
        except FileNotFoundError:
            ledger_fd = None
        if lock_created:
            # A newly-created lock is first-use only when every durable marker
            # was absent before this process acquired it. Any mixed state is a
            # crash, deletion, or manual mutation and must not be repaired here.
            if marker is not None or ledger_fd is not None:
                if ledger_fd is not None:
                    os.close(ledger_fd)
                raise ValueError("partial OR reconciliation initialization state")
            self._write_or_reconciliation_initialized_marker_locked(
                "INITIALIZING", exclusive=True
            )
            ledger = self._new_or_reconciliation_ledger(expected_day)
            self._write_or_reconciliation_ledger_locked(ledger)
            self._replace_or_reconciliation_marker_with_ready_locked()
            return ledger, ledger["indices"]
        if marker is None or ledger_fd is None:
            if ledger_fd is not None:
                os.close(ledger_fd)
            raise ValueError("OR reconciliation initialization artifacts are incomplete")
        if not stat.S_ISREG(os.fstat(ledger_fd).st_mode):
            os.close(ledger_fd)
            raise ValueError("OR reconciliation ledger is not a regular file")
        with os.fdopen(ledger_fd, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        ledger, indices = self._validate_or_reconciliation_ledger(raw, expected_day)
        ledger_day = date.fromisoformat(ledger["session_date"])
        if ledger_day < expected_day:
            ledger = self._new_or_reconciliation_ledger(expected_day)
            indices = ledger["indices"]
            self._write_or_reconciliation_ledger_locked(ledger)
        return ledger, indices

    def _apply_or_ledger_snapshot(
        self, session_day: date, indices: dict[str, dict[str, Any]]
    ) -> None:
        with self._lock:
            for index_name in self.or_bounds:
                state = indices[index_name]
                self.or_reconcile_retry_count[index_name] = state["attempt_count"]
                self.or_last_reconcile_attempt_ms[index_name] = state["last_attempt_timestamp_ms"]
                self._or_last_ledger_check_ms[index_name] = state["last_attempt_timestamp_ms"]
                proof = state.get("completion_proof")
                if proof is None:
                    current_evidence = self.or_evidence.get(index_name) or {}
                    if current_evidence.get("session_date") != session_day.isoformat():
                        self.or_bounds[index_name] = {"high": -math.inf, "low": math.inf}
                        self.or_evidence[index_name] = self._empty_or_evidence(session_day)
                        if index_name == "NIFTY":
                            self.active_range_high = -math.inf
                            self.active_range_low = math.inf
                    continue
                parsed = self._parse_complete_v2_or_candles(proof["candles"], session_day)
                if parsed is None:
                    raise ValueError("validated OR proof failed restore-time parsing")
                self.or_bounds[index_name] = {"high": parsed["high"], "low": parsed["low"]}
                self.or_evidence[index_name] = {
                    "session_date": session_day.isoformat(),
                    "status": "COMPLETE",
                    "source": proof["source"],
                    "source_timestamp_ms": proof["source_timestamp_ms"],
                    "coverage_count": proof["coverage_count"],
                    "coverage_start_ms": proof["coverage_start_ms"],
                    "coverage_end_ms": proof["coverage_end_ms"],
                }
                if index_name == "NIFTY":
                    self.active_range_high = parsed["high"]
                    self.active_range_low = parsed["low"]
            self.or_reconciliation_frozen = all(
                (self.or_evidence.get(index_name) or {}).get("session_date") == session_day.isoformat()
                and (self.or_evidence.get(index_name) or {}).get("status") == "COMPLETE"
                for index_name in self.or_bounds
            )
            self._or_reconciliation_loaded_session_day = session_day

    def _read_or_ledger_snapshot(self, expected_day: date) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        lock_fd, lock_created = self._acquire_or_reconciliation_lock()
        try:
            ledger, indices = self._load_or_reconciliation_ledger_locked(expected_day, lock_created)
            self._apply_or_ledger_snapshot(expected_day, indices)
            return ledger, indices
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _reserve_or_reconciliation_attempt(
        self, expected_day: date, index_name: str, now_ms: int, force: bool
    ) -> tuple[bool, str, int]:
        lock_fd, lock_created = self._acquire_or_reconciliation_lock()
        try:
            ledger, indices = self._load_or_reconciliation_ledger_locked(expected_day, lock_created)
            self._apply_or_ledger_snapshot(expected_day, indices)
            state = indices[index_name]
            if state.get("completion_proof") is not None:
                with self._lock:
                    self._or_last_ledger_check_ms[index_name] = now_ms
                return False, "COMPLETE", state["attempt_count"]
            attempts = state["attempt_count"]
            last_attempt_ms = state["last_attempt_timestamp_ms"]
            if attempts >= self.OR_MAX_RETRY_ATTEMPTS:
                with self._lock:
                    self._or_last_ledger_check_ms[index_name] = now_ms
                return False, "ATTEMPT_CAP_REACHED", attempts
            if now_ms < last_attempt_ms:
                raise ValueError("OR retry clock moved backward")
            if not force and last_attempt_ms > 0 and now_ms - last_attempt_ms < self.OR_MIN_RETRY_INTERVAL_MS:
                with self._lock:
                    self._or_last_ledger_check_ms[index_name] = now_ms
                return False, "THROTTLED", attempts

            next_attempt = attempts + 1
            indices[index_name] = {
                "attempt_count": next_attempt,
                "last_attempt_timestamp_ms": now_ms,
            }
            ledger["indices"] = indices
            self._write_or_reconciliation_ledger_locked(ledger)
            with self._lock:
                self.or_reconcile_retry_count[index_name] = next_attempt
                self.or_last_reconcile_attempt_ms[index_name] = now_ms
                self._or_last_ledger_check_ms[index_name] = now_ms
                self._or_reconciliation_loaded_session_day = expected_day
            return True, "RESERVED", next_attempt
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _persist_or_completion_proof(
        self, expected_day: date, index_name: str, parsed: dict[str, Any]
    ) -> bool:
        candles = parsed.get("normalized_candles")
        if not isinstance(candles, list) or len(candles) != 30:
            return False
        proof = {
            "source": "UPSTOX_V2_1M_EXACT_30",
            "coverage_count": parsed["coverage_count"],
            "coverage_start_ms": parsed["coverage_start_ms"],
            "coverage_end_ms": parsed["coverage_end_ms"],
            "source_timestamp_ms": parsed["source_timestamp_ms"],
            "candles": candles,
            "sha256": self._or_candles_digest(candles),
        }
        lock_fd: Optional[int] = None
        try:
            lock_fd, lock_created = self._acquire_or_reconciliation_lock()
            ledger, indices = self._load_or_reconciliation_ledger_locked(expected_day, lock_created)
            state = indices.get(index_name)
            if state is None or state["attempt_count"] <= 0:
                raise ValueError("OR completion has no durable retry reservation")
            previous = state.get("completion_proof")
            if previous is not None and previous["sha256"] != proof["sha256"]:
                raise ValueError("conflicting exact OR completion proof")
            state["completion_proof"] = proof
            indices[index_name] = state
            ledger["indices"] = indices
            self._write_or_reconciliation_ledger_locked(ledger)
            return True
        except Exception as exc:
            logger.error(
                "OR completion ledger persist failed for %s session=%s (%s)",
                index_name,
                expected_day.isoformat(),
                type(exc).__name__,
            )
            self._or_reconciliation_ledger_degraded = True
            return False
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    @staticmethod
    def _parse_complete_v2_or_candles(candles: Any, session_day: date) -> Optional[dict[str, Any]]:
        """Prove exact 09:15-09:45 IST one-minute coverage from aware v2 candle rows."""
        if not isinstance(candles, list):
            return None
        ist = ZoneInfo("Asia/Kolkata")
        expected = {
            datetime.combine(session_day, dt_time(9, 15), tzinfo=ist) + timedelta(minutes=minute)
            for minute in range(30)
        }
        selected: dict[datetime, tuple[float, float]] = {}
        selected_candles: dict[datetime, list[Any]] = {}
        seen_timestamps: set[datetime] = set()
        for row in candles:
            if not isinstance(row, (list, tuple)) or len(row) < 5 or not isinstance(row[0], str):
                return None
            try:
                source_dt = datetime.fromisoformat(row[0].strip().replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
            if source_dt.tzinfo is None or source_dt.utcoffset() is None:
                return None
            local_dt = source_dt.astimezone(ist)
            if local_dt.date() != session_day:
                return None
            if local_dt.second != 0 or local_dt.microsecond != 0 or local_dt.time() < dt_time(9, 15):
                return None
            if local_dt in seen_timestamps:
                return None
            seen_timestamps.add(local_dt)
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in row[1:5]):
                return None
            try:
                open_price, high, low, close = (float(value) for value in row[1:5])
            except (TypeError, ValueError, OverflowError):
                return None
            if not all(math.isfinite(value) and value > 0 for value in (open_price, high, low, close)):
                return None
            if high < low or high < max(open_price, close) or low > min(open_price, close):
                return None
            if not (dt_time(9, 15) <= local_dt.time() < dt_time(9, 45)):
                continue
            if local_dt not in expected:
                return None
            selected[local_dt] = (high, low)
            selected_candles[local_dt] = [
                local_dt.isoformat(), open_price, high, low, close,
            ]

        if set(selected) != expected or len(selected) != 30:
            return None
        highest = max(value[0] for value in selected.values())
        lowest = min(value[1] for value in selected.values())
        if not math.isfinite(highest) or not math.isfinite(lowest) or lowest <= 0 or highest < lowest:
            return None
        start_dt = datetime.combine(session_day, dt_time(9, 15), tzinfo=ist)
        end_dt = datetime.combine(session_day, dt_time(9, 44), tzinfo=ist)
        end_ms = int(end_dt.timestamp() * 1000)
        return {
            "high": highest,
            "low": lowest,
            "coverage_count": 30,
            "coverage_start_ms": int(start_dt.timestamp() * 1000),
            "coverage_end_ms": end_ms,
            "source_timestamp_ms": end_ms,
            "normalized_candles": [selected_candles[item] for item in sorted(expected)],
        }

    def _reset_opening_range_for_session_locked(self, index_name: str, session_day: date) -> None:
        self.or_bounds[index_name] = {"high": -math.inf, "low": math.inf}
        self.or_evidence[index_name] = self._empty_or_evidence(session_day)
        if index_name == "NIFTY":
            self.active_range_high = -math.inf
            self.active_range_low = math.inf

    def _seed_or_bounds_from_api_if_late_boot(
        self,
        session_day: Optional[date] = None,
        current_time_ms: Optional[int] = None,
        force: bool = False,
    ) -> bool:
        """Serialize same-process reconciliation while durable reservations span restarts."""
        with self._or_reconcile_call_lock:
            return self._seed_or_bounds_from_api_serialized(
                session_day=session_day,
                current_time_ms=current_time_ms,
                force=force,
            )

    def _seed_or_bounds_from_api_serialized(
        self,
        session_day: Optional[date],
        current_time_ms: Optional[int],
        force: bool,
    ) -> bool:
        """Retry exact OR reconciliation with a durable per-index attempt budget."""
        now_dt = datetime.now(ZoneInfo("Asia/Kolkata"))
        expected_day = session_day or now_dt.date()
        if now_dt.time() < self.opening_shock_end_time:
            return False

        now_ms = current_time_ms if current_time_ms is not None else int(now_dt.timestamp() * 1000)
        if type(now_ms) is not int or now_ms <= 0:
            logger.error("OR reconciliation blocked: invalid event timestamp")
            return False
        try:
            event_day = datetime.fromtimestamp(
                now_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
            ).date()
        except (OverflowError, OSError, ValueError):
            logger.error("OR reconciliation blocked: invalid event timestamp")
            return False
        if expected_day != now_dt.date() or event_day != expected_day:
            logger.warning(
                "OR reconciliation blocked for non-current session event=%s expected=%s current=%s",
                event_day.isoformat(),
                expected_day.isoformat(),
                now_dt.date().isoformat(),
            )
            return False

        if self._or_reconciliation_loaded_session_day != expected_day:
            if now_ms < self._or_ledger_retry_after_ms:
                return False
            try:
                self._read_or_ledger_snapshot(expected_day)
                self._or_reconciliation_ledger_degraded = False
                self._or_ledger_retry_after_ms = 0
            except Exception as exc:
                logger.error(
                    "OR reconciliation ledger unavailable for session=%s (%s); no API request issued",
                    expected_day.isoformat(),
                    type(exc).__name__,
                )
                self._or_reconciliation_ledger_degraded = True
                self._or_ledger_retry_after_ms = now_ms + self.OR_MIN_RETRY_INTERVAL_MS
                return False
        elif now_ms < self._or_ledger_retry_after_ms:
            return False

        with self._lock:
            if self.or_reconciliation_frozen:
                return True

        import os
        import requests
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
        if not token:
            return False

        headers = {"accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
        indices = [
            ("NIFTY", "NSE_INDEX%7CNifty%2050"),
            ("BANKNIFTY", "NSE_INDEX%7CNifty%20Bank"),
            ("SENSEX", "BSE_INDEX%7CSENSEX"),
        ]
        all_valid = True

        for index_name, instrument in indices:
            with self._lock:
                current = self.or_evidence.get(index_name) or {}
                if current.get("session_date") == expected_day.isoformat() and current.get("status") == "COMPLETE":
                    continue
                last_attempt_ms = self.or_last_reconcile_attempt_ms.get(index_name, 0)
                last_check_ms = self._or_last_ledger_check_ms.get(index_name, 0)
                attempt_count = self.or_reconcile_retry_count.get(index_name, 0)

            if now_ms < max(last_attempt_ms, last_check_ms):
                logger.error(
                    "OR reconciliation clock regressed for %s session=%s; request suppressed",
                    index_name,
                    expected_day.isoformat(),
                )
                all_valid = False
                continue
            if not force:
                if attempt_count >= self.OR_MAX_RETRY_ATTEMPTS:
                    if last_check_ms > 0 and now_ms - last_check_ms < self.OR_MIN_RETRY_INTERVAL_MS:
                        all_valid = False
                        continue
                elif last_attempt_ms > 0 and now_ms - last_attempt_ms < self.OR_MIN_RETRY_INTERVAL_MS:
                    all_valid = False
                    continue

            try:
                reserved, reserve_reason, retry_count = self._reserve_or_reconciliation_attempt(
                    expected_day, index_name, now_ms, force
                )
            except Exception as exc:
                logger.error(
                    "OR retry reservation failed for %s session=%s (%s); no API request issued",
                    index_name,
                    expected_day.isoformat(),
                    type(exc).__name__,
                )
                self._or_reconciliation_ledger_degraded = True
                self._or_ledger_retry_after_ms = now_ms + self.OR_MIN_RETRY_INTERVAL_MS
                all_valid = False
                continue
            if not reserved:
                if reserve_reason != "COMPLETE":
                    all_valid = False
                    if reserve_reason == "ATTEMPT_CAP_REACHED":
                        logger.warning(
                            "OR reconciliation retry cap reached for %s session=%s attempts=%s",
                            index_name,
                            expected_day.isoformat(),
                            retry_count,
                        )
                continue

            try:
                url = f"https://api.upstox.com/v2/historical-candle/intraday/{instrument}/1minute"
                response = requests.get(url, headers=headers, timeout=4)
                candles = response.json().get("data", {}).get("candles", []) if response.status_code == 200 else None
                parsed = self._parse_complete_v2_or_candles(candles, expected_day)
            except Exception as exc:
                logger.warning("Failed to fetch/validate v2 OR candles for %s: %s", index_name, exc)
                parsed = None

            with self._lock:
                current = self.or_evidence[index_name]
                if parsed is None:
                    all_valid = False
                    if not (current.get("session_date") == expected_day.isoformat()
                            and current.get("status") == "COMPLETE"):
                        pending = dict(current)
                        pending.update({
                            "session_date": expected_day.isoformat(),
                            "status": "PENDING_RECONCILIATION",
                            "source": "UPSTOX_V2_1M_RETRY",
                            "retry_count": retry_count,
                        })
                        self.or_evidence[index_name] = pending
                    continue

            if not self._persist_or_completion_proof(expected_day, index_name, parsed):
                all_valid = False
                with self._lock:
                    current = dict(self.or_evidence.get(index_name) or {})
                    current.update({
                        "session_date": expected_day.isoformat(),
                        "status": "PENDING_RECONCILIATION",
                        "source": "OR_LEDGER_PERSIST_FAILED",
                        "retry_count": retry_count,
                    })
                    self.or_evidence[index_name] = current
                continue

            with self._lock:
                self.or_bounds[index_name] = {"high": parsed["high"], "low": parsed["low"]}
                self.or_evidence[index_name] = {
                    "session_date": expected_day.isoformat(),
                    "status": "COMPLETE",
                    "source": "UPSTOX_V2_1M_EXACT_30",
                    "source_timestamp_ms": parsed["source_timestamp_ms"],
                    "coverage_count": parsed["coverage_count"],
                    "coverage_start_ms": parsed["coverage_start_ms"],
                    "coverage_end_ms": parsed["coverage_end_ms"],
                }
                if index_name == "NIFTY":
                    self.active_range_high = parsed["high"]
                    self.active_range_low = parsed["low"]
                if self.enable_stdout:
                    print(f"📥 [OR RECOVERY/RECONCILE] {index_name}: Verified 30 timestamped v2 1m candles -> High={parsed['high']:.2f}, Low={parsed['low']:.2f}")

        with self._lock:
            # Check if all required indices are now COMPLETE for expected_day
            all_complete = True
            for idx_name, _ in indices:
                ev = self.or_evidence.get(idx_name) or {}
                if not (ev.get("session_date") == expected_day.isoformat() and ev.get("status") == "COMPLETE"):
                    all_complete = False
                    break
            if all_complete:
                self.or_reconciliation_frozen = True
                if self.enable_stdout:
                    print("🔒 [OR RECONCILIATION COMPLETE] All indices verified exact 30-bar coverage. Reconciliation permanently frozen.")

        return all_valid

    def _validate_mode5_or_evidence(
        self,
        index_name: str,
        decision_timestamp_ms: int,
        completed_bar_boundary_ms: Optional[int] = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Validate OR evidence against an explicit completed-bar boundary."""
        try:
            decision_dt = datetime.fromtimestamp(
                decision_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
            )
        except (OverflowError, OSError, ValueError):
            return False, "OR_DECISION_TIMESTAMP_INVALID", {"index": index_name}
        with self._lock:
            state = dict(self.or_evidence.get(index_name) or {})
            bounds = dict(self.or_bounds.get(index_name) or {})
        details = {"index": index_name, "evidence": state, "bounds": bounds}
        if (
            isinstance(completed_bar_boundary_ms, bool)
            or not isinstance(completed_bar_boundary_ms, int)
            or completed_bar_boundary_ms <= 0
        ):
            return False, "OR_BOUNDARY_TIMESTAMP_INVALID", details
        try:
            boundary_dt = datetime.fromtimestamp(
                completed_bar_boundary_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
            )
        except (OverflowError, OSError, ValueError):
            return False, "OR_BOUNDARY_TIMESTAMP_INVALID", details
        if boundary_dt.date() != decision_dt.date():
            return False, "OR_BOUNDARY_SESSION_MISMATCH", details
        if state.get("session_date") != decision_dt.date().isoformat():
            return False, "OR_SESSION_MISMATCH", details
        try:
            high = float(bounds["high"])
            low = float(bounds["low"])
            source_timestamp_ms = int(state.get("source_timestamp_ms") or 0)
        except (KeyError, TypeError, ValueError, OverflowError):
            return False, "OR_EVIDENCE_MISSING", details
        if not (math.isfinite(high) and math.isfinite(low) and low > 0 and high >= low):
            return False, "OR_BOUNDS_INVALID", details
        if source_timestamp_ms <= 0 or source_timestamp_ms > completed_bar_boundary_ms:
            return False, "OR_SOURCE_NONCAUSAL", details
        try:
            source_dt = datetime.fromtimestamp(
                source_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
            )
        except (OverflowError, OSError, ValueError):
            return False, "OR_SOURCE_TIMESTAMP_INVALID", details
        if source_dt.date() != decision_dt.date():
            return False, "OR_SOURCE_SESSION_MISMATCH", details

        status = state.get("status")
        if decision_dt.time() < self.market_open_time:
            return False, "OR_PREOPEN_DECISION", details
        if decision_dt.time() < self.opening_shock_end_time:
            if status == "PARTIAL" and self.market_open_time <= source_dt.time() < self.opening_shock_end_time:
                return True, "OR_PARTIAL_CAUSAL", details
            if status != "COMPLETE":
                return False, "OR_PARTIAL_UNAVAILABLE", details
        if status != "COMPLETE":
            return False, "OR_COMPLETE_REQUIRED", details

        expected_start = int(datetime.combine(
            decision_dt.date(), dt_time(9, 15), tzinfo=ZoneInfo("Asia/Kolkata")
        ).timestamp() * 1000)
        expected_end = int(datetime.combine(
            decision_dt.date(), dt_time(9, 44), tzinfo=ZoneInfo("Asia/Kolkata")
        ).timestamp() * 1000)
        if (state.get("source") != "UPSTOX_V2_1M_EXACT_30"
                or state.get("coverage_count") != 30
                or state.get("coverage_start_ms") != expected_start
                or state.get("coverage_end_ms") != expected_end
                or source_timestamp_ms != expected_end):
            return False, "OR_COMPLETE_COVERAGE_UNPROVEN", details
        return True, "OR_COMPLETE_VERIFIED", details

    def _validate_mode5_or_pair(
        self,
        index_name: str,
        decision_timestamp_ms: int,
        completed_bar_boundary_ms: Optional[int] = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        target_ok, target_reason, target_detail = self._validate_mode5_or_evidence(
            index_name, decision_timestamp_ms, completed_bar_boundary_ms
        )
        companion_index = "SENSEX" if index_name == "NIFTY" else "NIFTY"
        companion_ok, companion_reason, companion_detail = self._validate_mode5_or_evidence(
            companion_index, decision_timestamp_ms, completed_bar_boundary_ms
        )
        details = {"target": target_detail, "companion": companion_detail}
        if not target_ok:
            return False, f"MODE5_TARGET_{target_reason}", details
        if not companion_ok:
            return False, f"MODE5_COMPANION_{companion_reason}", details
        return True, "MODE5_OR_VALID", details

    def on_stream_status(self, status: Any) -> None:
        pass

    def _update_spot(self, index_name: str, spot: float, ts_ms: int) -> bool:
        with self._lock:
            return self._update_spot_locked(index_name, spot, ts_ms)

    def _update_spot_locked(self, index_name: str, spot: float, ts_ms: int) -> bool:
        try:
            spot_value = float(spot)
        except (TypeError, ValueError, OverflowError):
            return False
        if (not isinstance(ts_ms, int) or isinstance(ts_ms, bool) or ts_ms <= 0
                or not math.isfinite(spot_value) or spot_value <= 0):
            return False
        if self._source_timestamp_exceeds_future_skew(ts_ms):
            return False
        try:
            source_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata"))
            tick_day = source_dt.date()
        except (OverflowError, OSError, ValueError):
            return False
        with self._lock:
            last_ts = self._last_spot_timestamp_ms.get(index_name, 0)
            if ts_ms <= last_ts:
                return False
            prior_day = self._rp2_session_dates.get(index_name)
            if prior_day is not None and tick_day < prior_day:
                return False
            if prior_day is not None and tick_day > prior_day:
                self._reset_rp2_state_for_session(index_name, tick_day)
            elif prior_day is None:
                self._rp2_session_dates[index_name] = tick_day
                if self._ground_truth_required.get(index_name, False):
                    self._ground_truth_session_dates[index_name] = tick_day.isoformat()
            self._last_spot_timestamp_ms[index_name] = ts_ms
        wall_obs = self.wall_observers.get(index_name)
        if wall_obs is not None:
            wall_obs.on_spot_tick(spot_price=spot_value, timestamp_ms=ts_ms)
        with self._lock:
            self.spots[index_name] = spot_value
            self.spots_ts_ms[index_name] = ts_ms
            if self.session_open_prices.get(index_name, 0.0) <= 0.0 and spot_value > 0.0:
                self.session_open_prices[index_name] = spot_value

            now_t = source_dt.time()
            if now_t < self.opening_shock_end_time:
                self.trade_lock_active = True
                # Strictly accumulate opening range ticks only after official market open (09:15)
                if now_t >= self.market_open_time:
                    evidence = self.or_evidence.get(index_name, {})
                    if evidence.get("session_date") != tick_day.isoformat():
                        self._reset_opening_range_for_session_locked(index_name, tick_day)
                    evidence = self.or_evidence[index_name]
                    b = self.or_bounds[index_name]
                    if evidence.get("status") != "COMPLETE":
                        b["high"] = max(b["high"], spot_value)
                        b["low"] = min(b["low"], spot_value)
                        self.or_evidence[index_name] = {
                            "session_date": tick_day.isoformat(),
                            "status": "PARTIAL",
                            "source": "UPSTOX_TICK_PARTIAL",
                            "source_timestamp_ms": ts_ms,
                            "coverage_count": 0,
                            "coverage_start_ms": 0,
                            "coverage_end_ms": 0,
                        }
                    # Feed session open to midday momentum extension engine
                    if (m_engine := self.midday_engines.get(index_name)) is not None:
                        m_engine.set_session_open(spot_value)
                    if index_name == "NIFTY":
                        self.active_range_high = b["high"]
                        self.active_range_low = b["low"]
            else:
                if self.trade_lock_active:
                    self.trade_lock_active = False
                    # Reconcile OR with official 1m candles to eliminate any stream drops or spurious ticks
                    self._seed_or_bounds_from_api_if_late_boot(session_day=tick_day, current_time_ms=ts_ms)
                    if self.enable_stdout:
                        print("\n🔓 [OPENING SHOCK CONCLUDED] Opening Range Boundaries Established:")
                        for idx, bounds in self.or_bounds.items():
                            if bounds["high"] > -math.inf:
                                rng = bounds["high"] - bounds["low"]
                                print(f"   • {idx}: OR High={bounds['high']:.1f} | OR Low={bounds['low']:.1f} | Range={rng:.1f} pts")
                        print("🛰️ Sentinel Live Setup Trigger Engine ACTIVE.")
                elif not self.or_reconciliation_frozen:
                    self._seed_or_bounds_from_api_if_late_boot(session_day=tick_day, current_time_ms=ts_ms)
        return True

    def _compute_rbfn_grid(
        self,
        index_name: str,
        spot_open: float,
        range_10m: Optional[float] = None,
        atr: Optional[float] = None,
        vix: Optional[float] = None,
    ) -> Any:
        """Computes scale-calibrated, gap-aware OptionMate RBFN Grid with dynamic channel scaling."""
        open_p = spot_open if spot_open > 0 else self.session_open_prices.get(index_name, 0.0)
        if open_p <= 0:
            open_p = self.spots.get(index_name, 0.0)

        pd_levels = self.prior_day_levels.get(index_name)
        prev_close = pd_levels.pdc if (pd_levels and pd_levels.pdc > 0) else open_p

        if atr is not None and atr > 0:
            eff_atr = float(atr)
        elif pd_levels and pd_levels.atr_20 and pd_levels.atr_20 > 0:
            eff_atr = float(pd_levels.atr_20)
        elif (obs := self.wall_observers.get(index_name)) and obs.atr_pts > 0:
            eff_atr = float(obs.atr_pts)
        else:
            eff_atr = 160.0 if index_name == "NIFTY" else (350.0 if index_name == "BANKNIFTY" else 500.0)

        vix_val = float(vix) if vix is not None else 14.0

        if index_name == "SENSEX":
            step_round_base = 50.0
            anchor_base = 100.0
            step_size = 100
        elif index_name == "BANKNIFTY":
            step_round_base = 50.0
            anchor_base = 50.0
            step_size = 100
        else:  # NIFTY
            step_round_base = 10.0
            anchor_base = 40.0
            step_size = 50

        # Scale-Invariant Harmonic Step: 0.50% of spot rounded to step_round_base
        baseline_step = round((open_p * 0.0050) / step_round_base) * step_round_base

        # Scale-calibrated dynamic channel step: max(baseline_step, 0.35 * range_10m)
        if range_10m is not None and range_10m > 0:
            channel_step = max(baseline_step, 0.35 * range_10m)
        else:
            channel_step = baseline_step

        # Dynamic Trend Decider (TD)
        gap = open_p - prev_close
        gap_threshold = 0.25 * eff_atr
        if abs(gap) >= gap_threshold:
            raw_td = open_p
        else:
            raw_td = 0.5 * (open_p + prev_close)
        trend_decider = round(raw_td / anchor_base) * anchor_base

        # Harmonic Volatility Bands
        vol_scale = math.sqrt(max(vix_val, 9.0) / 14.0)
        rp1_dist = channel_step * vol_scale
        rp2_dist = 2.0 * channel_step * vol_scale

        rp1_up = trend_decider + rp1_dist
        rp1_down = trend_decider - rp1_dist
        rp2_up = trend_decider + rp2_dist
        rp2_down = trend_decider - rp2_dist

        if index_name == "SENSEX":
            target_call = round(rp2_up / step_size) * step_size
            target_put = round(rp2_down / step_size) * step_size
            effective_dte = 2.0
            straddle_fv = open_p * 0.80 * (max(vix_val, 9.0) / 100.0) * math.sqrt(effective_dte / 365.0)
            sustainable_anchor = round(straddle_fv / 2.0, 1)
            return SensexOptionMateGrid(
                date=datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"),
                spot_open=round(float(open_p), 2),
                prev_close=round(float(prev_close), 2),
                atr_14=round(float(eff_atr), 2),
                vix=round(float(vix_val), 2),
                trend_decider=round(float(trend_decider), 2),
                rp1_upper=round(float(rp1_up), 2),
                rp2_upper=round(float(rp2_up), 2),
                rp1_lower=round(float(rp1_down), 2),
                rp2_lower=round(float(rp2_down), 2),
                target_call_strike=float(target_call),
                target_put_strike=float(target_put),
                sustainable_price_anchor=sustainable_anchor,
                dte=int(effective_dte),
            )
        else:
            call_strike = round(rp1_up / step_size) * step_size
            put_strike = round(rp1_down / step_size) * step_size
            bias = "BULL" if open_p >= trend_decider else "BEAR"
            target_strike = call_strike if bias == "BULL" else put_strike
            return OptionMateGrid(
                date=datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"),
                spot_open=round(float(open_p), 2),
                trend_decider=round(float(trend_decider), 2),
                rp1_upper=round(float(rp1_up), 2),
                rp2_upper=round(float(rp2_up), 2),
                rp1_lower=round(float(rp1_down), 2),
                rp2_lower=round(float(rp2_down), 2),
                call_strike=float(call_strike),
                put_strike=float(put_strike),
                recommended_bias=bias,
                target_strike=float(target_strike),
            )

    def _reset_rp2_state_for_session(self, index_name: str, session_day: date) -> bool:
        with self._lock:
            return self._reset_rp2_state_for_session_locked(index_name, session_day)

    def _reset_rp2_state_for_session_locked(self, index_name: str, session_day: date) -> bool:
        """Reset session-scoped RP2 piercing/retest state on an India-local day change."""
        previous_day = self._rp2_session_dates.get(index_name)
        if previous_day is None:
            self._rp2_session_dates[index_name] = session_day
            if self.or_evidence.get(index_name, {}).get("session_date") != session_day.isoformat():
                self._reset_opening_range_for_session_locked(index_name, session_day)
            if self._ground_truth_required.get(index_name, False):
                self._ground_truth_session_dates[index_name] = session_day.isoformat()
            return False
        if previous_day == session_day:
            return False
        self._rp2_session_dates[index_name] = session_day
        if self._ground_truth_required.get(index_name, False):
            self._ground_truth_session_dates[index_name] = session_day.isoformat()
        self.rp2_upper_pierced_before_1030[index_name] = False
        self.rp2_lower_pierced_before_1030[index_name] = False
        self.rp2_pierced_before_1030[index_name] = False
        self.session_open_prices[index_name] = 0.0
        self.bars_5m_history[index_name].clear()
        self.evaluated_5m_epochs[index_name].clear()
        self._clear_cached_rbfn_candidate_locked(index_name, "SESSION_ROLLOVER")
        self._option_depth_watermarks.setdefault(index_name, {}).clear()
        self._last_completed_5m_epoch[index_name] = -1
        self._last_5m_timestamp_ms[index_name] = 0
        self._last_spot_timestamp_ms[index_name] = 0
        self.bar_buckets_5m[index_name] = Synthetic5mBarBucket()
        self.bar_buckets[index_name] = SyntheticBarBucket()
        if index_name in self.or_bounds:
            self._reset_opening_range_for_session_locked(index_name, session_day)
        self.or_reconciliation_frozen = False
        self.or_last_reconcile_attempt_ms[index_name] = 0
        self.or_reconcile_retry_count[index_name] = 0
        if not self._has_valid_ground_truth_grid(index_name, session_day):
            old_grid = self.cached_rbfn_grids.get(index_name)
            if old_grid is not None and hasattr(old_grid, "is_ground_truth"):
                try:
                    object.__setattr__(old_grid, "is_ground_truth", False)
                except Exception:
                    pass
            self.cached_rbfn_grids[index_name] = None
            self.rbfn_grids_frozen[index_name] = False
        return True

    @staticmethod
    def _has_consecutive_rp2_hold_epochs(history: list[dict[str, Any]]) -> bool:
        """Require a touched bar followed by two contiguous five-minute bars."""
        if len(history) < 3:
            return False
        epochs: list[int] = []
        for record in history[-3:]:
            if not isinstance(record, dict):
                return False
            epoch = record.get("epoch_5min")
            if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
                return False
            epochs.append(epoch)
        return epochs[0] + 1 == epochs[1] and epochs[1] + 1 == epochs[2]

    def _on_5m_bar_close(
        self,
        index_name: str,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_volume: float,
        bar_time: dt_time,
        timestamp_ms: int,
        epoch_5min: int,
    ) -> Optional[CachedRBFNAuctionSignal]:
        with self._lock:
            result = self._on_5m_bar_close_locked(
                index_name, bar_open, bar_high, bar_low, bar_close, bar_volume,
                bar_time, timestamp_ms, epoch_5min,
            )
        return result

    def _on_5m_bar_close_locked(
        self,
        index_name: str,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_volume: float,
        bar_time: dt_time,
        timestamp_ms: int,
        epoch_5min: int,
    ) -> Optional[CachedRBFNAuctionSignal]:
        """Evaluates Mode 5 (OPTIONMATE_RBFN_AUCTION) on discrete 5-minute bar close.
        
        Evaluates:
        - Phase A: Opening Drive Auction (09:20:00 - 09:45:00 IST)
          * Aggressive Drive on 09:20 bar close if strong expansion candle outside RP1.
          * Conservative Drive on 09:25 bar close with 2-candle confirmation.
          * Scale-calibrated dynamic channel step: max(baseline_step, 0.35 * range_10m).
          * Strict Gate 2 verification (ATR hurdle, VIX hurdle, Sustainable Anchor, OR quality).
        - Phase B: Midday Reversal (10:45:00 - 13:30:00 IST)
          * 2-bar rejection inside RP1 targeting Trend Decider.
          * Permanently suppressed if the 10:30 RP2 piercing invalidation rule was tripped.
        Updates self.cached_rbfn_signals[index_name] atomically.
        """
        if (not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool) or timestamp_ms <= 0
                or not isinstance(epoch_5min, int) or isinstance(epoch_5min, bool) or epoch_5min < 0):
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR")
            return None
        if self._source_timestamp_exceeds_future_skew(timestamp_ms):
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR_CLOCK")
            return None
        if epoch_5min != timestamp_ms // 300000:
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR_EPOCH")
            return None
        completed_bar_boundary_ms = (epoch_5min + 1) * 300_000
        try:
            expected_bar_time = datetime.fromtimestamp(
                (epoch_5min + 1) * 300, tz=ZoneInfo("Asia/Kolkata")
            ).time()
        except (OverflowError, OSError, ValueError):
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR_TIME")
            return None
        if not isinstance(bar_time, dt_time) or bar_time != expected_bar_time:
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR_TIME")
            return None
        previous_ts = self._last_5m_timestamp_ms.get(index_name, 0)
        previous_epoch = self._last_completed_5m_epoch.get(index_name, -1)
        if timestamp_ms <= previous_ts or epoch_5min <= previous_epoch:
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "OUT_OF_ORDER_COMPLETED_BAR")
            return None
        try:
            session_day = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).date()
        except (OverflowError, OSError, ValueError):
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "INVALID_COMPLETED_BAR_SESSION")
            return None
        prior_day = self._rp2_session_dates.get(index_name)
        if prior_day is not None and session_day < prior_day:
            if index_name in self._cached_rbfn_candidate_meta:
                self._clear_cached_rbfn_candidate_locked(index_name, "PRIOR_SESSION_COMPLETED_BAR")
            return None
        self._reset_rp2_state_for_session(index_name, session_day)
        self._last_5m_timestamp_ms[index_name] = timestamp_ms
        self._last_completed_5m_epoch[index_name] = epoch_5min

        # GATE-SENTINEL-15: Retry Opening Range reconciliation until complete
        if expected_bar_time >= self.opening_shock_end_time and not self.or_reconciliation_frozen:
            self._seed_or_bounds_from_api_if_late_boot(session_day=session_day, current_time_ms=timestamp_ms)

        if self._ground_truth_required.get(index_name, False) and not self._has_valid_ground_truth_grid(index_name, session_day):
            signal = CachedRBFNAuctionSignal(
                timestamp_ms=timestamp_ms,
                index_name=index_name,
                action="ABSTAIN",
                direction="",
                target_strike=0.0,
                target_pts=0.0,
                sl_pts=0.0,
                setup_reason="GROUND_TRUTH_LEVELS_REQUIRED",
                trade_phase="UNSEEDED",
                bar_time=bar_time,
                is_active=False,
                is_vetoed=True,
                veto_reason="GROUND_TRUTH_LEVELS_REQUIRED",
            )
            self._cache_rbfn_signal_locked(index_name, signal, epoch_5min)
            return signal
        or_valid, or_reason, or_details = self._validate_mode5_or_pair(
            index_name, timestamp_ms, completed_bar_boundary_ms
        )
        if not or_valid:
            signal = CachedRBFNAuctionSignal(
                timestamp_ms=timestamp_ms,
                index_name=index_name,
                action="ABSTAIN",
                direction="",
                target_strike=0.0,
                target_pts=0.0,
                sl_pts=0.0,
                setup_reason="MODE5_OR_UNVERIFIED",
                trade_phase="OR_GATED",
                bar_time=bar_time,
                is_active=False,
                is_vetoed=True,
                veto_reason=or_reason,
            )
            self._cache_rbfn_signal_locked(index_name, signal, epoch_5min)
            self.record_veto("MODE5_OR", or_reason)
            self._defer_mode5_decision_trace_locked(
                index_name=index_name,
                bar_time=bar_time,
                action="ABSTAIN",
                reason=or_reason,
                details=or_details,
                timestamp_ms=timestamp_ms,
            )
            return signal
        bar_record = {
            "open": bar_open,
            "high": bar_high,
            "low": bar_low,
            "close": bar_close,
            "volume": bar_volume,
            "time": bar_time,
            "timestamp_ms": timestamp_ms,
            "epoch_5min": epoch_5min,
        }
        if index_name not in self.bars_5m_history:
            self.bars_5m_history[index_name] = []
        self.bars_5m_history[index_name].append(bar_record)

        if self.session_open_prices.get(index_name, 0.0) <= 0.0:
            self.session_open_prices[index_name] = bar_open

        history = self.bars_5m_history[index_name]
        if len(history) >= 2:
            range_10m = max(b["high"] for b in history[:2]) - min(b["low"] for b in history[:2])
        else:
            range_10m = bar_high - bar_low

        pd_levels = self.prior_day_levels.get(index_name)
        if pd_levels is None or not pd_levels.verified or pd_levels.atr_20 is None or pd_levels.atr_20 <= 0.0:
            signal = CachedRBFNAuctionSignal(
                timestamp_ms=timestamp_ms,
                index_name=index_name,
                action="ABSTAIN",
                direction="",
                target_strike=0.0,
                target_pts=0.0,
                sl_pts=0.0,
                setup_reason="UNSEEDED_PRIOR_DAY_LEVELS",
                trade_phase="UNSEEDED",
                bar_time=bar_time,
                is_active=False,
                is_vetoed=True,
                veto_reason="UNSEEDED_PRIOR_DAY_LEVELS",
            )
            self._cache_rbfn_signal_locked(index_name, signal, epoch_5min)
            return signal

        macro_daily_atr = float(pd_levels.atr_20)
        micro_intraday_atr = float(obs.atr_pts) if ((obs := self.wall_observers.get(index_name)) and obs.atr_pts > 0) else 0.0
        vix_val = 14.0

        # Grid Immutability Lock: Freeze RBFN grid once 09:20 bar completes so Trend Decider and RP1/RP2 are immutable
        if self.rbfn_grids_frozen.get(index_name, False) and self.cached_rbfn_grids.get(index_name) is not None:
            grid = self.cached_rbfn_grids[index_name]
        else:
            grid = self._compute_rbfn_grid(
                index_name=index_name,
                spot_open=self.session_open_prices[index_name],
                range_10m=range_10m,
                atr=macro_daily_atr,
                vix=vix_val,
            )
            self.cached_rbfn_grids[index_name] = grid
            if bar_time >= dt_time(9, 20):
                self.rbfn_grids_frozen[index_name] = True

        # Dynamic Black-Scholes ATM half-straddle sustainable price anchor calculation:
        # formula: 0.40 * spot * (max(vix, 9.0) / 100.0) * math.sqrt(max(dte, 0.20) / 365.0)
        spot_ref = bar_close if bar_close > 0 else (self.session_open_prices.get(index_name, 0.0) or bar_open)
        dte_ref = 2.0 if index_name == "SENSEX" else (1.0 if index_name in {"NIFTY", "BANKNIFTY"} else 1.0)
        if getattr(self, "expiry_info", None) and self.expiry_info.active_expiry_index == index_name:
            dte_ref = 0.20  # Expiry day fraction
        calc_anchor = round(
            0.40 * spot_ref * (max(vix_val, 9.0) / 100.0) * math.sqrt(max(dte_ref, 0.20) / 365.0),
            1,
        )

        eff_time = bar_time
        if eff_time == dt_time(9, 15):
            eff_time = dt_time(9, 20)

        # Continuous Trading Session (09:20 - 15:00 IST)
        # Strategy logic is continuous and invariant to artificial time partitions.
        is_session_active = (dt_time(9, 20) <= eff_time <= dt_time(15, 0))
        rp2_piercing_cutoff = dt_time(10, 30)

        # 10:30 RP2 Piercing Invalidation Rule check (Directional RP2 Piercing: ARCH-SENTINEL-HARDENING-002)
        if eff_time <= rp2_piercing_cutoff:
            if bar_high >= grid.rp2_upper:
                self.rp2_upper_pierced_before_1030[index_name] = True
                self.rp2_pierced_before_1030[index_name] = True
            if bar_low <= grid.rp2_lower:
                self.rp2_lower_pierced_before_1030[index_name] = True
                self.rp2_pierced_before_1030[index_name] = True

        strat = self.rbfn_strategies.get(index_name)
        min_atr = getattr(strat, "min_atr_frictional_hurdle", 150.0) if strat else 150.0
        min_vix = getattr(strat, "min_vix_hurdle", 12.0) if strat else 12.0

        signal: Optional[CachedRBFNAuctionSignal] = None

        # -----------------------------------------------------------------
        # Continuous State-Machine Auction Evaluation (09:20 - 15:00 IST)
        # -----------------------------------------------------------------
        # Dynamic ATR scale-down factor for low-volatility regimes (ATR < 150)
        is_low_vol = (macro_daily_atr < min_atr or vix_val < min_vix)
        target_scale = 0.60 if is_low_vol else 1.0

        if is_session_active:
            phase_label = "OPENING_DRIVE" if eff_time <= dt_time(9, 45) else "CONTINUOUS_STATE_MACHINE"
            # Strict Gate 2 Frictional Hurdle: Hard-abort when daily ATR is below minimum threshold (150 for NIFTY, 450 for SENSEX)
            if macro_daily_atr < min_atr:
                signal = CachedRBFNAuctionSignal(
                    timestamp_ms=timestamp_ms,
                    index_name=index_name,
                    action="ABSTAIN",
                    direction="",
                    target_strike=0.0,
                    target_pts=0.0,
                    sl_pts=0.0,
                    setup_reason="GATE_2_FRICTIONAL_HURDLE",
                    trade_phase=phase_label,
                    bar_time=bar_time,
                    is_active=False,
                    is_vetoed=True,
                    veto_reason="GATE_2_FRICTIONAL_HURDLE",
                )
            elif range_10m < (0.35 * macro_daily_atr) and not is_low_vol and len(history) < 2:
                signal = CachedRBFNAuctionSignal(
                    timestamp_ms=timestamp_ms,
                    index_name=index_name,
                    action="ABSTAIN",
                    direction="",
                    target_strike=0.0,
                    target_pts=0.0,
                    sl_pts=0.0,
                    setup_reason="GATE_2_COMPRESSION_CHOP",
                    trade_phase=phase_label,
                    bar_time=bar_time,
                    is_active=False,
                    is_vetoed=True,
                    veto_reason="GATE_2_COMPRESSION_CHOP",
                )
            elif len(history) < 2:
                # Need at least 2 bars of 5m history for 2-bar confirmation
                # On the very first 09:20 bar, evaluate opening drive if tested TD
                td_max_aggr_dist = 10.0 if index_name == "NIFTY" else (30.0 if index_name == "SENSEX" else 20.0)
                tested_td_aggr_bull = (abs(bar_open - grid.trend_decider) <= td_max_aggr_dist or abs(bar_low - grid.trend_decider) <= td_max_aggr_dist)
                tested_td_aggr_bear = (abs(bar_open - grid.trend_decider) <= td_max_aggr_dist or abs(bar_high - grid.trend_decider) <= td_max_aggr_dist)
                is_bullish = bar_close > grid.rp1_upper
                is_bearish = bar_close < grid.rp1_lower

                if is_bullish or is_bearish:
                    strong_expansion = (is_bullish and bar_close > bar_open) or (is_bearish and bar_close < bar_open)
                    if not strong_expansion:
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action="ABSTAIN",
                            direction="",
                            target_strike=0.0,
                            target_pts=0.0,
                            sl_pts=0.0,
                            setup_reason="GATE_2_UNCONFIRMED_BREAKOUT",
                            trade_phase=phase_label,
                            bar_time=bar_time,
                            is_active=False,
                            is_vetoed=True,
                            veto_reason="GATE_2_UNCONFIRMED_BREAKOUT",
                        )
                    elif (
                        (is_bullish and bar_close >= grid.rp2_upper)
                        or (is_bearish and bar_close <= grid.rp2_lower)
                    ):
                        # The opening drive targets RP2. Do not turn an already
                        # reached target into a farther chase target via abs().
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action="ABSTAIN",
                            direction="",
                            target_strike=0.0,
                            target_pts=0.0,
                            sl_pts=0.0,
                            setup_reason="OPENING_RP2_TARGET_ALREADY_REACHED",
                            trade_phase=phase_label,
                            bar_time=bar_time,
                            is_active=False,
                            is_vetoed=True,
                            veto_reason="OPENING_RP2_TARGET_ALREADY_REACHED",
                        )
                    else:
                        action = "BUY_CALL" if is_bullish else "BUY_PUT"
                        direction = "CE" if is_bullish else "PE"
                        if index_name == "SENSEX":
                            t_strike = grid.target_call_strike if is_bullish else grid.target_put_strike
                            t_target = grid.rp2_upper if is_bullish else grid.rp2_lower
                            inval = grid.rp1_upper - 50.0 if is_bullish else grid.rp1_lower + 50.0
                            t_pts = max(45.0, abs(t_target - bar_close))
                            s_pts = max(35.0, abs(bar_close - inval))
                        else:
                            t_strike = grid.call_strike if is_bullish else grid.put_strike
                            t_target = grid.rp2_upper if is_bullish else grid.rp2_lower
                            inval = grid.rp1_upper - 15.0 if is_bullish else grid.rp1_lower + 15.0
                            t_pts = max(20.0, abs(t_target - bar_close))
                            s_pts = max(15.0, abs(bar_close - inval))
                        setup_str = f"RP1_{'UPPER' if is_bullish else 'LOWER'}_AGGRESSIVE_DRIVE"
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action=action,
                            direction=direction,
                            target_strike=float(t_strike),
                            target_pts=round(t_pts, 2),
                            sl_pts=round(s_pts, 2),
                            setup_reason=setup_str,
                            trade_phase=phase_label,
                            bar_time=bar_time,
                            sustainable_anchor_price=calc_anchor,
                            is_active=True,
                            is_vetoed=False,
                            veto_reason="",
                        )
                elif bar_close > grid.trend_decider and bar_close > bar_open and tested_td_aggr_bull:
                    action = "BUY_CALL"
                    direction = "CE"
                    if index_name == "SENSEX":
                        t_strike = round(grid.rp1_upper / 100.0) * 100.0
                        inval = grid.trend_decider - 50.0
                        t_pts = max(40.0, abs(grid.rp1_upper - bar_close))
                        s_pts = max(30.0, abs(bar_close - inval))
                    else:
                        t_strike = grid.call_strike
                        inval = grid.trend_decider - 15.0
                        t_pts = max(15.0, abs(grid.rp1_upper - bar_close))
                        s_pts = max(12.0, abs(bar_close - inval))
                    setup_str = "TD_TO_RP1_UPPER_AGGRESSIVE_DRIVE"
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action=action,
                        direction=direction,
                        target_strike=float(t_strike),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason=setup_str,
                        trade_phase=phase_label,
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                elif bar_close < grid.trend_decider and bar_close < bar_open and tested_td_aggr_bear:
                    action = "BUY_PUT"
                    direction = "PE"
                    if index_name == "SENSEX":
                        t_strike = round(grid.rp1_lower / 100.0) * 100.0
                        inval = grid.trend_decider + 50.0
                        t_pts = max(40.0, abs(bar_close - grid.rp1_lower))
                        s_pts = max(30.0, abs(inval - bar_close))
                    else:
                        t_strike = grid.put_strike
                        inval = grid.trend_decider + 15.0
                        t_pts = max(15.0, abs(bar_close - grid.rp1_lower))
                        s_pts = max(12.0, abs(inval - bar_close))
                    setup_str = "TD_TO_RP1_LOWER_AGGRESSIVE_DRIVE"
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action=action,
                        direction=direction,
                        target_strike=float(t_strike),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason=setup_str,
                        trade_phase=phase_label,
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                else:
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="ABSTAIN",
                        direction="",
                        target_strike=0.0,
                        target_pts=0.0,
                        sl_pts=0.0,
                        setup_reason="IN_CORRIDOR_BETWEEN_RP1",
                        trade_phase=phase_label,
                        bar_time=bar_time,
                        is_active=False,
                        is_vetoed=False,
                        veto_reason="",
                    )
            else:
                # Full 2-Bar Confirmation State Machine (Evaluated continuous 09:20 - 15:00 IST)
                buf = 15.0 if index_name == "SENSEX" else 5.0
                step = 100 if index_name in {"SENSEX", "BANKNIFTY"} else 50

                c_prev = history[-2].get("close", history[-2].get("high", 0.0))
                c_curr = history[-1].get("close", history[-1].get("high", 0.0))
                is_10m_breakout_upper = (c_prev >= grid.rp1_upper and c_curr >= grid.rp1_upper)
                is_10m_breakdown_lower = (c_prev <= grid.rp1_lower and c_curr <= grid.rp1_lower)

                # Check for S7: Extreme Floor Bounce (Tested RP2_LOWER and holds above for 10 mins, or single-bar fast bounce)
                rejection_buffer = 25.0 if index_name in {"SENSEX", "BANKNIFTY"} else 10.0
                fast_bounce_rp2 = (
                    bar_low <= grid.rp2_lower
                    and bar_close >= (grid.rp2_lower + rejection_buffer)
                    and bar_close < grid.rp1_lower
                )
                # A touch qualifies for the 10-minute branch only when two
                # consecutive completed five-minute bars follow it. The current
                # bar is already appended, so validate all three epochs.
                has_consecutive_rp2_hold = self._has_consecutive_rp2_hold_epochs(history)
                tested_rp2_lower = has_consecutive_rp2_hold and history[-3]["low"] <= grid.rp2_lower
                is_10m_bounce_rp2 = tested_rp2_lower and (c_prev >= grid.rp2_lower and c_curr >= grid.rp2_lower and c_curr < grid.rp1_lower)

                # Check for S5: Extreme Ceiling Fade (Tested RP2_UPPER and holds below for 10 mins, or single-bar fast rejection)
                fast_rejection_rp2 = (
                    bar_high >= grid.rp2_upper
                    and bar_close <= (grid.rp2_upper - rejection_buffer)
                    and bar_close > grid.rp1_upper
                )
                tested_rp2_upper = has_consecutive_rp2_hold and history[-3]["high"] >= grid.rp2_upper
                is_10m_fade_rp2 = tested_rp2_upper and (c_prev <= grid.rp2_upper and c_curr <= grid.rp2_upper and c_curr > grid.rp1_upper)

                # -------------------------------------------------------------
                # 1. SCENARIO 7 (S7): RP2_LOWER -> RP1_LOWER Extreme Floor Bounce / Fast Bounce
                # -------------------------------------------------------------
                if fast_bounce_rp2 or is_10m_bounce_rp2:
                    target_k = round(grid.rp1_lower / step) * step
                    t_pts = max(20.0 if index_name != "SENSEX" else 50.0, abs(grid.rp1_lower - bar_close))
                    s_pts = max(15.0 if index_name != "SENSEX" else 40.0, abs(bar_close - (grid.rp2_lower - (25.0 if index_name == "SENSEX" else 15.0))))
                    setup_str = "RP2_LOWER_FAST_BOUNCE" if fast_bounce_rp2 else "RP2_LOWER_10M_FLOOR_BOUNCE"
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_CALL",
                        direction="CE",
                        target_strike=float(target_k),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason=setup_str,
                        trade_phase="EXTREME_EXHAUSTION_REVERSAL",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp2_lower,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 2. SCENARIO 5 (S5): RP2_UPPER -> RP1_UPPER Extreme Ceiling Fade / Fast Rejection
                # -------------------------------------------------------------
                elif fast_rejection_rp2 or is_10m_fade_rp2:
                    target_k = round(grid.rp1_upper / step) * step
                    t_pts = max(20.0 if index_name != "SENSEX" else 50.0, abs(bar_close - grid.rp1_upper))
                    s_pts = max(15.0 if index_name != "SENSEX" else 40.0, abs((grid.rp2_upper + (25.0 if index_name == "SENSEX" else 15.0)) - bar_close))
                    setup_str = "RP2_UPPER_FAST_REJECTION" if fast_rejection_rp2 else "RP2_UPPER_10M_CEILING_FADE"
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_PUT",
                        direction="PE",
                        target_strike=float(target_k),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason=setup_str,
                        trade_phase="EXTREME_EXHAUSTION_REVERSAL",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp2_upper,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 10:30 RP2 Piercing Invalidation Rule check for Early Retests / Continuations
                # ARCH-SENTINEL-OPTIONMATE-HARDENING-001 & ARCH-SENTINEL-HARDENING-002:
                # Directional RP2 Piercing uncouples upper from lower checks
                # ARCH-SENTINEL-HARDENING-003: Upper pierce tests upper boundary; lower pierce tests lower boundary
                # -------------------------------------------------------------
                elif (
                    (self.rp2_upper_pierced_before_1030.get(index_name, False) and not (any(b.get("low", math.inf) <= grid.rp2_upper for b in history[-6:]) if len(history) >= 2 else False))
                    or (self.rp2_lower_pierced_before_1030.get(index_name, False) and not (any(b.get("high", -math.inf) >= grid.rp2_lower for b in history[-6:]) if len(history) >= 2 else False))
                ):
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="ABSTAIN",
                        direction="",
                        target_strike=0.0,
                        target_pts=0.0,
                        sl_pts=0.0,
                        setup_reason="10:30_RP2_PIERCING_TREND_DAY_INVALIDATION",
                        trade_phase=phase_label,
                        bar_time=bar_time,
                        is_active=False,
                        is_vetoed=True,
                        veto_reason="10:30_RP2_PIERCING_TREND_DAY_INVALIDATION",
                    )
                # -------------------------------------------------------------
                # 3. SCENARIO 2 (S2): RP1_UPPER -> RP2_UPPER Expansion Breakout
                # -------------------------------------------------------------
                elif is_10m_breakout_upper and bar_close < grid.rp2_upper:
                    target_k = round(grid.rp2_upper / step) * step
                    t_pts = max(20.0 if index_name != "SENSEX" else 60.0, abs(grid.rp2_upper - bar_close))
                    s_pts = max(15.0 if index_name != "SENSEX" else 45.0, abs(bar_close - (grid.rp1_upper - (25.0 if index_name == "SENSEX" else 15.0))))
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_CALL",
                        direction="CE",
                        target_strike=float(target_k),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason="RP1_UPPER_10M_EXPANSION_BREAKOUT",
                        trade_phase="MIDDAY_EXPANSION_BREAKOUT",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp1_upper,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 4. SCENARIO 4 (S4): RP1_LOWER -> RP2_LOWER Expansion Breakdown
                # -------------------------------------------------------------
                elif is_10m_breakdown_lower and bar_close > grid.rp2_lower:
                    target_k = round(grid.rp2_lower / step) * step
                    t_pts = max(20.0 if index_name != "SENSEX" else 60.0, abs(bar_close - grid.rp2_lower))
                    s_pts = max(15.0 if index_name != "SENSEX" else 45.0, abs((grid.rp1_lower + (25.0 if index_name == "SENSEX" else 15.0)) - bar_close))
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_PUT",
                        direction="PE",
                        target_strike=float(target_k),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason="RP1_LOWER_10M_EXPANSION_BREAKDOWN",
                        trade_phase="MIDDAY_EXPANSION_BREAKDOWN",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp1_lower,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 5. SCENARIO 6 (S6): RP1_UPPER Reversal Fade (Capped Target)
                # Tested RP1_UPPER and 2 consecutive closes below RP1_UPPER - buf -> Targets TD
                # -------------------------------------------------------------
                elif any(b["high"] >= grid.rp1_upper for b in history[-3:]) and all(b["close"] <= (grid.rp1_upper - buf) for b in history[-2:]) and bar_close > grid.trend_decider and bar_close < bar_open:
                    t_strike = round(grid.trend_decider / step) * step
                    t_pts = max(18.0 if index_name != "SENSEX" else 50.0, round(abs(bar_close - grid.trend_decider), 2))
                    s_pts = max(12.0 if index_name != "SENSEX" else 35.0, abs((grid.rp1_upper + (30.0 if index_name == "SENSEX" else 20.0)) - bar_close))
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_PUT",
                        direction="PE",
                        target_strike=float(t_strike),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason="RP1_UPPER_REVERSAL_CONFIRMED",
                        trade_phase="MIDDAY_REVERSAL",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp1_upper,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 6. SCENARIO 8 (S8): RP1_LOWER Reversal Fade (Capped Target)
                # Tested RP1_LOWER and 2 consecutive closes above RP1_LOWER + buf -> Targets TD
                # -------------------------------------------------------------
                elif any(b["low"] <= grid.rp1_lower for b in history[-3:]) and all(b["close"] >= (grid.rp1_lower + buf) for b in history[-2:]) and bar_close < grid.trend_decider and bar_close > bar_open:
                    t_strike = round(grid.trend_decider / step) * step
                    t_pts = max(18.0 if index_name != "SENSEX" else 50.0, round(abs(grid.trend_decider - bar_close), 2))
                    s_pts = max(12.0 if index_name != "SENSEX" else 35.0, abs(bar_close - (grid.rp1_lower - (30.0 if index_name == "SENSEX" else 20.0))))
                    signal = CachedRBFNAuctionSignal(
                        timestamp_ms=timestamp_ms,
                        index_name=index_name,
                        action="BUY_CALL",
                        direction="CE",
                        target_strike=float(t_strike),
                        target_pts=round(t_pts, 2),
                        sl_pts=round(s_pts, 2),
                        setup_reason="RP1_LOWER_REVERSAL_CONFIRMED",
                        trade_phase="MIDDAY_REVERSAL",
                        bar_time=bar_time,
                        sustainable_anchor_price=calc_anchor,
                        triggering_reference_price=grid.rp1_lower,
                        is_active=True,
                        is_vetoed=False,
                        veto_reason="",
                    )
                # -------------------------------------------------------------
                # 7. SCENARIO TD-RETEST: Continuous Trend Decider Retest & Rejection (Active Throughout Session)
                # 2-bar confirmation at TD: Candle 1 tested TD, Candle 2 confirms directional hold near TD (<= 15 pts NIFTY, <= 45 pts SENSEX)
                # Bullish rejection drives toward RP1_UPPER; Bearish rejection drives toward RP1_LOWER.
                # -------------------------------------------------------------
                else:
                    td_touch_tolerance = 15.0 if index_name == "SENSEX" else (10.0 if index_name == "BANKNIFTY" else 5.0)
                    max_midway_dist = 45.0 if index_name == "SENSEX" else (30.0 if index_name == "BANKNIFTY" else 15.0)
                    min_target_retest = 45.0 if index_name == "SENSEX" else (30.0 if index_name == "BANKNIFTY" else 15.0)
                    min_sl_retest = 35.0 if index_name == "SENSEX" else (25.0 if index_name == "BANKNIFTY" else 12.0)

                    prev_bar = history[-2]
                    curr_bar = history[-1]

                    # Candle 1 (previous bar) tested Trend Decider
                    c1_tested_td_bull = prev_bar.get("low", 0.0) <= (grid.trend_decider + td_touch_tolerance)
                    c1_tested_td_bear = prev_bar.get("high", math.inf) >= (grid.trend_decider - td_touch_tolerance)

                    # Candle 2 (current bar) confirms sustained directional rejection at TD without running away midway
                    c2_holds_near_td = abs(bar_close - grid.trend_decider) <= max_midway_dist
                    c2_confirmed_bull = (curr_bar.get("close", 0.0) > curr_bar.get("open", 0.0)) and (curr_bar.get("close", 0.0) >= grid.trend_decider)
                    c2_confirmed_bear = (curr_bar.get("close", 0.0) < curr_bar.get("open", 0.0)) and (curr_bar.get("close", 0.0) <= grid.trend_decider)

                    holding_at_td_bull = c1_tested_td_bull and c2_confirmed_bull and c2_holds_near_td
                    holding_at_td_bear = c1_tested_td_bear and c2_confirmed_bear and c2_holds_near_td
                    call_k = getattr(grid, "call_strike", getattr(grid, "target_call_strike", round(grid.rp1_upper / step) * step))
                    put_k = getattr(grid, "put_strike", getattr(grid, "target_put_strike", round(grid.rp1_lower / step) * step))

                    if holding_at_td_bull:
                        t_pts = max(min_target_retest, abs(grid.rp1_upper - bar_close))
                        s_pts = max(min_sl_retest, abs(bar_close - (grid.trend_decider - td_touch_tolerance * 2.0)))
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action="BUY_CALL",
                            direction="CE",
                            target_strike=float(call_k),
                            target_pts=round(t_pts, 2),
                            sl_pts=round(s_pts, 2),
                            setup_reason="TD_PULLBACK_REENTRY_BULL_CONFIRMED_2BAR",
                            trade_phase="RETEST_CORRIDOR",
                            bar_time=bar_time,
                            sustainable_anchor_price=calc_anchor,
                            is_active=True,
                            is_vetoed=False,
                            veto_reason="",
                        )
                    elif holding_at_td_bear:
                        t_pts = max(min_target_retest, abs(bar_close - grid.rp1_lower))
                        s_pts = max(min_sl_retest, abs((grid.trend_decider + td_touch_tolerance * 2.0) - bar_close))
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action="BUY_PUT",
                            direction="PE",
                            target_strike=float(put_k),
                            target_pts=round(t_pts, 2),
                            sl_pts=round(s_pts, 2),
                            setup_reason="TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR",
                            trade_phase="RETEST_CORRIDOR",
                            bar_time=bar_time,
                            sustainable_anchor_price=calc_anchor,
                            is_active=True,
                            is_vetoed=False,
                            veto_reason="",
                        )
                    else:
                        signal = CachedRBFNAuctionSignal(
                            timestamp_ms=timestamp_ms,
                            index_name=index_name,
                            action="ABSTAIN",
                            direction="",
                            target_strike=0.0,
                            target_pts=0.0,
                            sl_pts=0.0,
                            setup_reason="NO_CONFIRMED_TD_TEST_OR_MIDWAY",
                            trade_phase="RETEST_CORRIDOR",
                            bar_time=bar_time,
                            is_active=False,
                            is_vetoed=False,
                            veto_reason="",
                        )

        with self._lock:
            self._cache_rbfn_signal_locked(index_name, signal, epoch_5min)

            # -------------------------------------------------------------
            # Step 1: Dynamic Per-Index Gear Switching with 3-Bar Hysteresis Lock
            # Mathematical Specification:
            # Ω_10 = Range_10m / ATR_20
            # If Ω_10 >= 1.80: Escalate to GEAR_2_TREND immediately on expansion impulse.
            # If Ω_10 < 1.00: Require 3 consecutive 5m bars of corridor compression
            # before de-escalating to GEAR_1_RANGE, preventing trailing stop chattering.
            # -------------------------------------------------------------
            if macro_daily_atr > 0.0:
                omega_10 = round(range_10m / macro_daily_atr, 3)
                self.gear_expansion_ratios[index_name] = omega_10
                curr_gear = self.session_gears.get(index_name, "GEAR_1_RANGE")

                if omega_10 >= 1.80:
                    self.gear_range_bar_counters[index_name] = 0
                    self.gear_trend_bar_counters[index_name] = self.gear_trend_bar_counters.get(index_name, 0) + 1
                    if curr_gear != "GEAR_2_TREND":
                        self.session_gears[index_name] = "GEAR_2_TREND"
                        if index_name == "NIFTY":
                            self.session_gear = "GEAR_2_TREND"  # Sync legacy fallback
                        logger.info(
                            f"⚙️ [GEAR ESCALATION] {index_name} switched {curr_gear} -> GEAR_2_TREND "
                            f"(Range10m={range_10m:.1f}, ATR20={macro_daily_atr:.1f}, Ω10={omega_10:.2f} >= 1.80)"
                        )
                elif omega_10 < 1.00:
                    self.gear_range_bar_counters[index_name] = self.gear_range_bar_counters.get(index_name, 0) + 1
                    # 3-Bar Hysteresis Lock: require 3 consecutive consolidation bars to revert to RANGE
                    if curr_gear == "GEAR_2_TREND" and self.gear_range_bar_counters[index_name] >= 3:
                        self.session_gears[index_name] = "GEAR_1_RANGE"
                        if index_name == "NIFTY":
                            self.session_gear = "GEAR_1_RANGE"  # Sync legacy fallback
                        logger.info(
                            f"⚙️ [GEAR DE-ESCALATION] {index_name} switched GEAR_2_TREND -> GEAR_1_RANGE "
                            f"(3 consecutive compression bars, Ω10={omega_10:.2f} < 1.00)"
                        )
                else:
                    # In hysteresis deadband [1.00, 1.80): retain current gear and reset counters
                    self.gear_range_bar_counters[index_name] = 0
                    self.gear_trend_bar_counters[index_name] = 0

        if signal is not None:
            self._defer_mode5_decision_trace_locked(
                index_name=index_name,
                bar_time=bar_time,
                action=signal.action,
                reason=signal.setup_reason,
                details={
                    "direction": signal.direction,
                    "target_strike": signal.target_strike,
                    "target_pts": signal.target_pts,
                    "sl_pts": signal.sl_pts,
                    "is_active": signal.is_active,
                    "is_vetoed": signal.is_vetoed,
                    "veto_reason": signal.veto_reason,
                    "bar_close": bar_close,
                    "or_validation": {"reason": or_reason, **or_details},
                },
                timestamp_ms=timestamp_ms,
            )

        return signal

    def _evaluate_option_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        now_ts = time.time()
        # Rate-limit console telemetry prints to at most 1 per second unless a live BUY signal occurs
        is_throttled = (now_ts - self._last_alert_time < 1.0)

        # Determine which index this option belongs to and setup strike parameters
        index_name = self._resolve_option_index_from_display_symbol(depth.symbol)
        if index_name is None:
            self.record_veto(
                "UNKNOWN_OPTION_UNDERLYING_SYMBOL",
                "OPTION_DEPTH_BLOCKED_UNKNOWN_OR_UNRECOGNIZED_DISPLAY_SYMBOL",
            )
            return
        quote_valid, quote_reason, quote_day, option_instrument_key, source_order = self._option_quote_identity(
            index_name, depth
        )
        if not quote_valid or quote_day is None or option_instrument_key is None or source_order is None:
            self.record_veto("OPTION_DEPTH_TIMESTAMP", quote_reason)
            return
        validated_decision_timestamp_ms = int(time.time() * 1000)
        if not self._record_option_depth_order(index_name, quote_day, option_instrument_key, source_order):
            self.record_veto("OPTION_DEPTH_ORDER", "OPTION_DEPTH_DUPLICATE_DECREASING_OR_PRIOR_SESSION")
            return
        sym = depth.symbol.upper()
        if index_name == "SENSEX":
            strike_interval = 100.0
            eff_atr_fallback = 500.0
            min_target = 45.0
            min_sl = 35.0
            eff_atr_15m = 100.0
            eff_atr_60m = 140.0
        elif index_name == "BANKNIFTY":
            strike_interval = 100.0
            eff_atr_fallback = 300.0
            min_target = 30.0
            min_sl = 25.0
            eff_atr_15m = 45.0
            eff_atr_60m = 65.0
        else:  # Explicit NIFTY prefix; BANKNIFTY has already matched above.
            strike_interval = 50.0
            eff_atr_fallback = 65.0
            min_target = 12.0
            min_sl = 12.0
            eff_atr_15m = 32.5
            eff_atr_60m = 65.0

        broker_instrument_key = self._canonical_option_instrument_key(index_name, depth.token)
        if self.automated_dispatcher is not None and broker_instrument_key is None:
            self.record_veto(
                "BROKER_INSTRUMENT_KEY",
                "OPTION_DEPTH_BLOCKED_MISSING_OR_MALFORMED_KEY",
            )
            return

        # Feed option depth tick to SentinelWallObserver
        wall_obs = self.wall_observers.get(index_name)
        effective_atr = wall_obs.atr_pts if (wall_obs is not None and wall_obs.atr_pts > 0) else eff_atr_fallback

        # Dynamically align multi-timeframe ATRs with live observer ATR
        if effective_atr > 0:
            eff_atr_60m = max(eff_atr_60m, round(effective_atr, 1))
            eff_atr_15m = max(eff_atr_15m, round(0.50 * eff_atr_60m, 1))

        nominal_target = round(0.35 * effective_atr, 2)
        nominal_sl = round(0.25 * effective_atr, 2)
        target_pts = max(min_target, nominal_target)
        sl_pts = max(min_sl, nominal_sl)
        if wall_obs is not None:
            bid_d = float(depth.bid_q1 + depth.bid_q2 + depth.bid_q3 + depth.bid_q4 + depth.bid_q5)
            ask_d = float(depth.ask_q1 + depth.ask_q2 + depth.ask_q3 + depth.ask_q4 + depth.ask_q5)
            
            # Gate 4: Derivatives OI Quarantine (Pre-09:15:00 IST stand-aside)
            # OI broadcast during pre-market is stale remnant from prior session
            effective_oi = float(depth.open_interest)
            if depth.exchange_timestamp_ms > 0:
                opt_check_time = datetime.fromtimestamp(depth.exchange_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).time()
            else:
                opt_check_time = datetime.now(ZoneInfo("Asia/Kolkata")).time()
            if opt_check_time < self.market_open_time:
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
                    fn = str(self.wal_dir / f"sentinel_wall_state_{index_name.lower()}.json")
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

        # Derive causal wall time from exchange timestamp or fallback to system clock
        if depth.exchange_timestamp_ms > 0:
            now_dt = datetime.fromtimestamp(depth.exchange_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata"))
        else:
            now_dt = datetime.now(ZoneInfo("Asia/Kolkata"))
        now_time = now_dt.time()

        # Opening shock freeze: strictly suppress all candidate setups unless Mode 5 Opening Drive is active
        # Mode 5 Opening Drive is permitted between 09:20:00 and 09:45:00 IST.
        # General setups remain frozen until 09:45:00.
        effective_shock_end = self.opening_shock_end_time
        session_pre_open_cutoff = dt_time(9, 20)

        in_opening_shock = (trade_lock or now_time < effective_shock_end)
        if now_time < session_pre_open_cutoff:
            return

        mode5_generation: Optional[int] = None
        rbfn_sig, mode5_generation = self._candidate_for_option_depth(
            index_name=index_name,
            depth=depth,
            quote_day=quote_day,
            instrument_key=option_instrument_key,
            source_order=source_order,
            validated_decision_timestamp_ms=validated_decision_timestamp_ms,
        )
        has_mode_5_signal = (
            rbfn_sig is not None
            and rbfn_sig.is_active
            and not rbfn_sig.is_vetoed
            and rbfn_sig.action in {"BUY_CALL", "BUY_PUT"}
        )

        if has_mode_5_signal and rbfn_sig is not None:
            with self._lock:
                candidate_meta = self._cached_rbfn_candidate_meta.get(index_name)
                completed_bar_boundary_ms = (
                    candidate_meta.boundary_timestamp_ms
                    if candidate_meta is not None and candidate_meta.generation == mode5_generation
                    else None
                )
            or_valid, or_reason, or_details = self._validate_mode5_or_pair(
                index_name, depth.exchange_timestamp_ms, completed_bar_boundary_ms
            )
            if not or_valid:
                self.record_veto("MODE5_OR", or_reason)
                self.log_decision_trace(
                    index_name=index_name,
                    bar_time=now_time,
                    action="ABSTAIN",
                    reason=or_reason,
                    details={"signal_timestamp_ms": rbfn_sig.timestamp_ms, **or_details},
                    timestamp_ms=depth.exchange_timestamp_ms,
                    candidate_generation=mode5_generation,
                )
                return

        if in_opening_shock and not has_mode_5_signal:
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

        # Setup Detection for RBFN and retained shared intraday modules
        is_ce = "CE" in sym
        is_pe = "PE" in sym
        atm_strike = round(spot / strike_interval) * strike_interval

        trigger_active = False
        setup_reason = ""
        strategy_name = "SENTINEL"
        required_option_type = None
        is_exp = (self.expiry_info.active_expiry_index == index_name)

        # -------------------------------------------------------------
        # Mode 5: FEAT-SENTINEL-OPTIONMATE-RBFN-AUCTION-001 - OptionMate RBFN Auction Engine
        # Evaluates Phase A (Opening Drive 09:20-09:45) and Phase B (Midday Reversal 10:45-13:30).
        # Cached from 5m bar close evaluation: < 250ns execution with zero float math overhead.
        # -------------------------------------------------------------
        if has_mode_5_signal and rbfn_sig is not None:
            trigger_active = True
            strategy_name = "OPTIONMATE_RBFN_AUCTION"
            required_option_type = rbfn_sig.direction
            setup_reason = f"[{rbfn_sig.trade_phase}] {rbfn_sig.setup_reason}"
            target_pts = rbfn_sig.target_pts
            sl_pts = rbfn_sig.sl_pts

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
            strategy_name = f"INTRADAY_REVERSAL_{rev_sig.setup_type.value}"
            required_option_type = rev_sig.direction.value
            setup_reason = f"[{rev_sig.setup_type.value}] {rev_sig.setup_reason}"
            target_pts = rev_sig.reward_pts
            sl_pts = rev_sig.risk_pts

        # -------------------------------------------------------------
        # Mode 4: FEAT-SENTINEL-MIDDAY-MOMENTUM-001 - Causal Midday Momentum Extension
        # Evaluates morning drift strictly at 12:30:00 IST on completed 12:29 bar
        # 1:1 Fixed Symmetrical Payoff (40.0 pts target / 40.0 pts stop)
        # -------------------------------------------------------------
        elif (
            (m_engine := self.midday_engines.get(index_name)) is not None
            and (
                midday_sig := m_engine.evaluate_at_1230(
                    current_spot=spot,
                    timestamp_ms=depth.exchange_timestamp_ms,
                    wall_time=now_time,
                    date_str=now_dt.strftime("%Y-%m-%d"),
                )
            ) is not None
            and midday_sig.direction != MiddayDirection.ABSTAIN
        ):
            trigger_active = True
            self._last_midday_sig = midday_sig
            strategy_name = "MIDDAY_MOMENTUM_EXTENSION"
            required_option_type = midday_sig.recommended_option_type
            setup_reason = f"[MIDDAY_1230] {midday_sig.setup_reason}"
            target_pts = midday_sig.target_pts
            sl_pts = midday_sig.stop_pts

        # Compute Multi-Factor Confidence Score
        conf_eval = None
        if trigger_active and ((required_option_type == "CE" and is_ce) or (required_option_type == "PE" and is_pe)):
            depth_bids = depth.bid_q1 + depth.bid_q2 + depth.bid_q3 + depth.bid_q4 + depth.bid_q5
            depth_asks = depth.ask_q1 + depth.ask_q2 + depth.ask_q3 + depth.ask_q4 + depth.ask_q5
            if strategy_name == "OPTIONMATE_RBFN_AUCTION" and rbfn_sig is not None:
                cached_g = self.cached_rbfn_grids.get(index_name)
                td_anchor = getattr(cached_g, "trend_decider", 0.0) if cached_g is not None else 0.0
                displacement = abs(spot - td_anchor) if td_anchor > 0.0 else abs(spot - rbfn_sig.target_strike)
            elif required_option_type == "CE":
                displacement = (spot - or_high) if or_high > -math.inf else 0.0
            else:
                displacement = (spot - or_low) if or_low < math.inf else 0.0
            
            # Strike matching check for ITM or Strategy Target Strike
            tolerance_to_use = 1
            if strategy_name == "MIDDAY_MOMENTUM_EXTENSION" and (m_sig := getattr(self, "_last_midday_sig", None)) is not None:
                target_strike_to_match = m_sig.recommended_strike
                itm_res = self.strike_resolver.resolve_target_strike(
                    spot=spot,
                    direction=required_option_type,
                    index_name=index_name,
                )
            elif strategy_name == "OPTIONMATE_RBFN_AUCTION" and rbfn_sig is not None:
                # Mode 5 Golden Strategy strictly targets the OTM Slingshot corridor strike (RP1).
                # Live stream quotes must match the exact strike (zero tolerance) to prevent ATM drift.
                # In order to select the genuine OTM Slingshot strike in the accumulation band [0.50, 0.75] * anchor,
                # we query all live option depths currently coalesced in InMemorySentinelAdapter.
                all_depths = self.adapter.get_all_depth()
                opt_quote_candidates = []
                for d_rec in all_depths.values():
                    d_sym = d_rec.symbol.upper()
                    if index_name not in d_sym:
                        continue
                    if (required_option_type == "CE" and "CE" not in d_sym) or (required_option_type == "PE" and "PE" not in d_sym):
                        continue
                    # Extract strike from token/symbol
                    d_stk = 0.0
                    for part in d_sym.split():
                        if part.isdigit() and len(part) >= 4:
                            d_stk = float(part)
                            break
                    if d_stk > 0 and (d_rec.ltp or d_rec.bid_p1) > 0:
                        opt_quote_candidates.append({
                            "symbol": d_rec.symbol,
                            "strike": d_stk,
                            "ltp": float(d_rec.ltp or d_rec.bid_p1),
                            "direction": required_option_type,
                        })

                if not opt_quote_candidates:
                    quote_strike = float(atm_strike)
                    for part in depth.symbol.upper().split():
                        if part.isdigit() and len(part) >= 4:
                            quote_strike = float(part)
                            break
                    opt_quote_candidates = [{
                        "symbol": depth.symbol,
                        "strike": quote_strike,
                        "ltp": ltp,
                        "direction": required_option_type,
                    }]

                m5_strike_res = SentinelOptionStrikeResolver.resolve_mode5_strike(
                    index_name=index_name,
                    direction=required_option_type,
                    anchor_price=rbfn_sig.sustainable_anchor_price,
                    geometric_strike=rbfn_sig.target_strike,
                    live_quotes=opt_quote_candidates,
                )
                target_strike_to_match = m5_strike_res.target_strike
                # Tier-1 exact match preferred; if exact strike absent from active stream quotes, allow Tier-2 adjacent liquid depth match (tolerance = 1)
                exact_depth_present = any(abs(c["strike"] - target_strike_to_match) < 1.0 for c in opt_quote_candidates)
                tolerance_to_use = 0 if exact_depth_present else 1
                itm_res = self.strike_resolver.resolve_target_strike(
                    spot=spot,
                    direction=required_option_type,
                    index_name=index_name,
                )
            else:
                itm_res = self.strike_resolver.resolve_target_strike(
                    spot=spot,
                    direction=required_option_type,
                    index_name=index_name,
                )
                target_strike_to_match = itm_res.target_strike

            is_target_strike = self.strike_resolver.is_contract_matching(
                symbol=sym,
                target_strike=target_strike_to_match,
                option_type=required_option_type,
                tolerance_strikes=tolerance_to_use,
                strike_interval=strike_interval,
            )

            is_mode5_reversal = (
                strategy_name == "OPTIONMATE_RBFN_AUCTION"
                and rbfn_sig is not None
                and (
                    rbfn_sig.trade_phase in {"MIDDAY_REVERSAL", "EXTREME_EXHAUSTION_REVERSAL"}
                    or any(k in rbfn_sig.setup_reason for k in ("REVERSAL", "FADE", "BOUNCE", "FLOOR", "CEILING", "PULLBACK"))
                )
            )
            if is_mode5_reversal:
                # Check companion index safety: do not fade if companion index is plunging at day extreme in same direction
                comp_index = "SENSEX" if index_name == "NIFTY" else "NIFTY"
                comp_s = self.spots.get(comp_index, 0.0)
                comp_b = self.or_bounds.get(comp_index, {})
                comp_low = comp_b.get("low", -math.inf)
                comp_high = comp_b.get("high", math.inf)
                comp_levels = self.prior_day_levels.get(comp_index)
                comp_atr = float(comp_levels.atr_20 or 150.0) if comp_levels else 150.0
                
                # If buying CE (bullish bounce), companion must not be plunging < comp_low - 0.5 * ATR (macro breakdown)
                # If buying PE (bearish fade), companion must not be exploding > comp_high + 0.5 * ATR (macro breakout)
                macro_extreme_trap = False
                if required_option_type == "CE" and comp_s > 0 and comp_low > -math.inf and comp_s < (comp_low - 0.50 * comp_atr):
                    macro_extreme_trap = True
                elif required_option_type == "PE" and comp_s > 0 and comp_high < math.inf and comp_s > (comp_high + 0.50 * comp_atr):
                    macro_extreme_trap = True

                if macro_extreme_trap:
                    macro_ok = False
                    macro_reason = "MACRO_EXTREME_LIQUIDATION_TRAP"
                else:
                    macro_ok = True
                    macro_reason = "MODE_5_REVERSAL_AUTONOMOUS"
            elif strategy_name == "OPTIONMATE_RBFN_AUCTION":
                comp_index = "SENSEX" if index_name == "NIFTY" else "NIFTY"
                comp_s = self.spots.get(comp_index, 0.0)
                comp_b = self.or_bounds.get(comp_index, {})
                if comp_s > 0 and comp_b.get("high", -math.inf) > -math.inf:
                    macro_ok, macro_reason = self.macro_gate.evaluate_alignment(
                        target_index=index_name,
                        setup_direction=required_option_type,
                        spots=self.spots,
                        or_bounds=self.or_bounds,
                    )
                else:
                    macro_ok = True
                    macro_reason = "MODE_5_RBFN_AUTONOMOUS"
            else:
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

            # Boost conviction for Mode 5: RBFN auction breakout confirmed outside Gaussian barrier RP1
            if strategy_name == "OPTIONMATE_RBFN_AUCTION":
                dyn_conviction = max(0.75, dyn_conviction)

            conf_eval = self.confidence_scorer.evaluate_confidence(
                macro_aligned=macro_ok,
                macro_reason=macro_reason,
                writer_alignment="BEARS_IN_CONTROL" if required_option_type == "PE" else "BULLS_IN_CONTROL",
                writer_conviction=dyn_conviction,
                setup_direction=required_option_type,
                depth_bid_q_sum=depth_bids,
                depth_ask_q_sum=depth_asks,
                displacement_pts=displacement,
                eff_atr=(max(float(self.prior_day_levels.get(index_name, {}).get("atr_20", 150.0) or 150.0), 150.0) if strategy_name == "OPTIONMATE_RBFN_AUCTION" and self.prior_day_levels.get(index_name) else eff_atr_15m),
                is_target_itm=is_target_strike,
                spread_ratio=spread_ratio,
                is_expiry_session=is_exp,
            )

            vol_displacement = displacement
            vol_input_error = None
            if strategy_name == "OPTIONMATE_RBFN_AUCTION" and rbfn_sig is not None:
                vol_displacement, vol_input_error = mode5_rp_exhaustion_displacement(
                    setup_reason=rbfn_sig.setup_reason,
                    triggering_reference_price=rbfn_sig.triggering_reference_price,
                    spot=spot,
                    fallback_displacement=displacement,
                )

            vol_ok, vol_reason, _ = self.vol_compression_gate.evaluate_compression(
                atr_15m=eff_atr_15m,
                atr_60m=eff_atr_60m,
                recent_displacement_pts=vol_displacement,
            )
            if vol_input_error is not None:
                vol_ok = False
                vol_reason = vol_input_error
            elif (
                vol_ok is False
                and rbfn_sig is not None
                and rbfn_sig.setup_reason in MODE_5_EXHAUSTION_FADES
                and "EXHAUSTED_EXPANSION" in vol_reason
            ):
                try:
                    rp_reference = float(rbfn_sig.triggering_reference_price)
                    rp_spot = float(spot)
                except (TypeError, ValueError, OverflowError):
                    rp_reference = math.nan
                    rp_spot = math.nan
                if (
                    math.isfinite(rp_reference)
                    and rp_reference > 0.0
                    and math.isfinite(rp_spot)
                    and rp_spot > 0.0
                ):
                    rp_name, reference_side, _ = rbfn_sig.setup_reason.split("_", 2)
                    reference_name = f"{'U' if reference_side == 'UPPER' else 'L'}{rp_name}"
                    vol_reason = (
                        f"DISTANCE_TO_BOUNDARY (distance={vol_displacement:.1f} pts, "
                        f"reference={reference_name} {rp_reference:.1f}, "
                        f"setup={rbfn_sig.setup_reason}, "
                        f"limit={self.vol_compression_gate.exhaustion_multiplier:g}x "
                        f"ATR60={eff_atr_60m:.1f} pts)"
                    )

            # Gate 2: SentinelWallGate pre-entry check (0.5 * ATR Adverse Wall Clamping)
            # ARCH-SENTINEL-OPTIONMATE-HARDENING-001: Wall-Gate Exemption for Mode 5 Structural Breakouts & Exhaustion Fades
            is_wall_exempt = is_mode_5_structural_breakout(setup_reason) or is_mode_5_exhaustion_fade(setup_reason)
            wall_gate = self.wall_gates.get(index_name)
            wall_vetoed = False
            wall_reason = ""
            if wall_gate is not None and not is_wall_exempt:
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
                        wall_buffer_pts=None,
                        min_rr_ratio=1.0,
                    )
                    if clamp_decision.action == GATE_ACTION_VETO:
                        wall_vetoed = True
                        wall_reason = clamp_decision.reason
                    elif clamp_decision.action == GATE_ACTION_CLAMP_TARGET and clamp_decision.clamped_target_pts is not None:
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
            elif ltp > self.max_premium_cap:
                status_flag = "VETO_PREMIUM_OVER_CAP"
                advisory = f"🚨 [PREMIUM VETO] BUY {depth.symbol} LTP ₹{ltp:.1f} > ₹{self.max_premium_cap:.1f} (Deep-ITM Gamma Collapse Risk)"
                self.journal.record_veto(
                    index_name=index_name,
                    symbol=depth.symbol,
                    direction=required_option_type,
                    setup_reason=setup_reason,
                    veto_reason="PREMIUM_OVER_CAP",
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
                # Option Native Stop Loss: 20% of option premium or 15.0 pts minimum
                opt_sl_pts = max(15.0, round(ltp * 0.20, 2))

                # Gate 1: Capital Discretization & Integer Lot Math (Floor-or-Reject Model)
                # allow_single_lot_floor enabled for accounts with ₹30k - ₹50k to guarantee 1 lot execution
                computed_lots, sizing_tier = calculate_discrete_lots(
                    total_capital=self.advisory_capital,
                    risk_budget_pct=0.02,
                    opt_premium=ltp,
                    sl_points=opt_sl_pts,
                    index_name=index_name,
                    sizing_recommendation=conf_eval.sizing_recommendation,
                    allow_single_lot_floor=True,
                )

                # Strict Lot Caps enforcement per index
                idx_upper = (index_name or "NIFTY").upper().strip()
                if "NIFTY" in idx_upper and "BANK" not in idx_upper:
                    computed_lots = min(computed_lots, 3)
                elif "SENSEX" in idx_upper:
                    computed_lots = min(computed_lots, 2)
                elif "BANKNIFTY" in idx_upper:
                    computed_lots = min(computed_lots, 2)

                ex_lot_size = get_exchange_lot_size(index_name)
                total_qty = computed_lots * ex_lot_size

                if computed_lots < 1 or sizing_tier == "ZERO_SUPPRESS":
                    status_flag = "VETO_INSUFFICIENT_MARGIN" if computed_lots < 1 else "VETO_SIZING_SUPPRESSED"
                    advisory = f"🚨 [SIZING VETO: {sizing_tier}] BUY {depth.symbol} @ {setup_reason} -> SUPPRESSED (Lots={computed_lots})"
                    veto_tag = "VETO_INSUFFICIENT_MARGIN" if computed_lots < 1 else f"SIZING_{sizing_tier}"
                    self.journal.record_veto(
                        index_name=index_name,
                        symbol=depth.symbol,
                        direction=required_option_type,
                        setup_reason=setup_reason,
                        veto_reason=veto_tag,
                        spot_price=spot,
                        option_ltp=ltp,
                        bid=bid,
                        ask=ask,
                        spread_pts=spread,
                        spread_ratio=spread_ratio,
                        nominal_target_pts=target_pts,
                        nominal_sl_pts=opt_sl_pts,
                        confidence_score=conf_eval.total_score if conf_eval else 0,
                        confidence_grade=conf_eval.grade if conf_eval else "GRADE_C_SUPPRESSED",
                        sizing_tier=sizing_tier,
                        timestamp_ms=depth.exchange_timestamp_ms,
                        wall_time_str=now_time.strftime("%H:%M:%S"),
                    )
                else:
                    status_flag = "SIGNAL_TRIGGERED"
                    anchor_info = f" | Anchor: ₹{rbfn_sig.sustainable_anchor_price:.1f}" if (strategy_name == "OPTIONMATE_RBFN_AUCTION" and rbfn_sig and rbfn_sig.sustainable_anchor_price > 0) else ""
                    advisory = (
                        f"🎯 [BUY {depth.symbol}] @ {setup_reason}{anchor_info} | "
                        f"Conviction: {conf_eval.total_score}/100 ({conf_eval.grade}, WinRate ~{conf_eval.probable_win_rate_pct:.0f}%, {sizing_tier}, {computed_lots} lots / {total_qty} qty) | "
                        f"Target: +{target_pts:.1f}pts | Vol-SL: -{sl_pts:.1f}pts"
                    )

                    # Gate 4: Passive Midpoint Queue Execution Price
                    fill_price, savings, fill_mode = self.passive_midpoint_queue.calculate_entry_fill(
                        bid=bid,
                        ask=ask,
                        passive_fill_enabled=True,
                    )

                    entry_dispatch_request = None
                    with self._lock:
                        idx_apm = self.apms.get(index_name, self.apm)
                        active_gear = self.session_gears.get(index_name, self.session_gear)
                        strat_priority = self.strategy_priority_weights.get(strategy_name, 0.50)

                        # Dual-Stream Shadow Telemetry Tagging (Canonical vs Observational)
                        curr_trades = self.daily_trade_counters.get(index_name, 0)
                        shadow_tier = "PRIMARY_CANONICAL" if curr_trades < 5 else "OBSERVATIONAL_SHADOW"

                        # Invariant 2.3 & Hardened Defense 3: Encapsulated Cool-off State Evaluation
                        # Check whether APM is actively blocking entry due to cool-off
                        cool_off_blocking = idx_apm.is_cool_off_active(
                            now_dt=now_dt,
                            incoming_direction=required_option_type
                        )

                        entered = False
                        if idx_apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK, STATE_EXIT_PENDING}:
                            is_target_strike = False
                        elif cool_off_blocking:
                            is_target_strike = False
                        elif is_target_strike and (idx_apm.state in {STATE_STANDBY, STATE_LIQUIDATED, STATE_PULLBACK_WAIT} or not cool_off_blocking):
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
                            entry_or_valid = True
                            entry_or_reason = "MODE5_OR_VALID"
                            if strategy_name == "OPTIONMATE_RBFN_AUCTION":
                                if mode5_generation is None:
                                    entry_or_valid = False
                                    entry_or_reason = "MODE5_CANDIDATE_METADATA_MISSING"
                                else:
                                    entry_or_valid, entry_or_reason = self._final_candidate_authorization_locked(
                                        index_name=index_name,
                                        generation=mode5_generation,
                                        depth=depth,
                                        quote_day=quote_day,
                                        instrument_key=option_instrument_key,
                                        source_order=source_order,
                                        now_ns=time.monotonic_ns(),
                                    )
                                if entry_or_valid:
                                    candidate_meta = self._cached_rbfn_candidate_meta.get(index_name)
                                    completed_bar_boundary_ms = (
                                        candidate_meta.boundary_timestamp_ms
                                        if candidate_meta is not None and candidate_meta.generation == mode5_generation
                                        else None
                                    )
                                    entry_or_valid, entry_or_reason, _ = self._validate_mode5_or_pair(
                                        index_name,
                                        depth.exchange_timestamp_ms,
                                        completed_bar_boundary_ms,
                                    )
                            if entry_or_valid:
                                exec_reason = f"[{shadow_tier}] {setup_reason}"
                                if strategy_name == "OPTIONMATE_RBFN_AUCTION" and rbfn_sig and rbfn_sig.sustainable_anchor_price > 0:
                                    exec_reason = f"{exec_reason} [ANCHOR: ₹{rbfn_sig.sustainable_anchor_price:.1f}]"

                                # CONTRACT 1: Gate APM entry, WAL, and counters on automated dispatcher acceptance
                                dispatcher_accepted = True
                                if self.automated_dispatcher:
                                    if broker_instrument_key is None:
                                        dispatcher_accepted = False
                                        entered = False
                                        if strategy_name == "OPTIONMATE_RBFN_AUCTION" and mode5_generation is not None:
                                            self._consume_cached_rbfn_candidate_locked(
                                                index_name, mode5_generation, "TERMINAL_INVALID_BROKER_KEY"
                                            )
                                        status_flag = "VETO_BROKER_KEY"
                                        advisory = "WAIT (BROKER_KEY_INVALID)"
                                        self.record_veto("BROKER_INSTRUMENT_KEY", "ENTRY_DISPATCH_BLOCKED_MISSING_OR_MALFORMED_KEY")
                                        self._defer_mode5_decision_trace_locked(
                                            index_name=index_name,
                                            bar_time=now_time,
                                            action="ABSTAIN",
                                            reason="ENTRY_DISPATCH_BLOCKED_MISSING_OR_MALFORMED_KEY",
                                            details={"authorization_recheck": True},
                                            timestamp_ms=depth.exchange_timestamp_ms,
                                            candidate_generation=mode5_generation,
                                        )
                                    else:
                                        try:
                                            res = self.automated_dispatcher.reserve_entry_intent(
                                                index_name=index_name,
                                                symbol=broker_instrument_key,
                                                option_type=required_option_type,
                                                entry_price=fill_price,
                                                target_pts=target_pts,
                                                sl_pts=sl_pts,
                                                setup_reason=exec_reason,
                                                qty=int(total_qty),
                                                intent_id=str(pos_id),
                                            )
                                        except Exception as exc:
                                            dispatcher_accepted = False
                                            entered = False
                                            if strategy_name == "OPTIONMATE_RBFN_AUCTION" and mode5_generation is not None:
                                                self._consume_cached_rbfn_candidate_locked(
                                                    index_name, mode5_generation, "RESERVATION_EXCEPTION_UNKNOWN"
                                                )
                                            logger.exception("[%s] Entry reservation raised; candidate quarantined", index_name)
                                            status_flag = "VETO_RESERVATION_UNKNOWN"
                                            advisory = "WAIT (RESERVATION_OUTCOME_UNKNOWN)"
                                            self.record_veto("ENTRY_RESERVATION", "ENTRY_RESERVATION_EXCEPTION_UNKNOWN")
                                            self._defer_mode5_decision_trace_locked(
                                                index_name=index_name,
                                                bar_time=now_time,
                                                action="ABSTAIN",
                                                reason="ENTRY_RESERVATION_EXCEPTION_UNKNOWN",
                                                details={"exception_type": type(exc).__name__},
                                                timestamp_ms=depth.exchange_timestamp_ms,
                                                candidate_generation=mode5_generation,
                                            )
                                        else:
                                            if not res.accepted:
                                                dispatcher_accepted = False
                                                entered = False
                                                if strategy_name == "OPTIONMATE_RBFN_AUCTION" and mode5_generation is not None:
                                                    self._consume_cached_rbfn_candidate_locked(
                                                        index_name, mode5_generation,
                                                        f"RESERVATION_{res.action or 'UNKNOWN'}",
                                                    )
                                                status_flag = f"VETO_{res.action}"
                                                advisory = f"WAIT ({res.action})"
                                                self.record_veto(res.action, res.reason)
                                                self._defer_mode5_decision_trace_locked(
                                                    index_name=index_name,
                                                    bar_time=now_time,
                                                    action="ABSTAIN",
                                                    reason=res.reason,
                                                    details={"veto_action": res.action, "routed_mode": res.routed_mode},
                                                    timestamp_ms=depth.exchange_timestamp_ms,
                                                    candidate_generation=mode5_generation,
                                                )
                                            else:
                                                if strategy_name == "OPTIONMATE_RBFN_AUCTION" and mode5_generation is not None:
                                                    # Quarantine immediately after accepted reservation, before the
                                                    # out-of-lock dispatcher callback can observe another quote.
                                                    self._consume_cached_rbfn_candidate_locked(
                                                        index_name, mode5_generation, "RESERVATION_ACCEPTED"
                                                    )
                                                entry_dispatch_request = {
                                                    "index_name": index_name,
                                                    "symbol": broker_instrument_key,
                                                    "option_type": required_option_type,
                                                    "entry_price": fill_price,
                                                    "target_pts": target_pts,
                                                    "sl_pts": sl_pts,
                                                    "setup_reason": exec_reason,
                                                    "qty": int(total_qty),
                                                    "intent_id": str(pos_id),
                                                }

                                if dispatcher_accepted:
                                    if (
                                        strategy_name == "OPTIONMATE_RBFN_AUCTION"
                                        and mode5_generation is not None
                                        and self.automated_dispatcher is None
                                    ):
                                        # Local APM authorization is the one-shot point when no dispatcher
                                        # reservation is configured.
                                        self._consume_cached_rbfn_candidate_locked(
                                            index_name, mode5_generation, "LOCAL_APM_AUTHORIZED"
                                        )
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
                                        is_runner_mode=(active_gear == "GEAR_2_TREND"),
                                        session_gear=active_gear,
                                        opt_stop_loss_pct=0.20,
                                        atr_1m=effective_atr,
                                        lots=computed_lots,
                                        sizing_tier=sizing_tier,
                                        lot_size=ex_lot_size,
                                        total_quantity=total_qty,
                                        is_expiry_day=is_exp,
                                        is_deep_itm=(itm_res.moneyness in {"ITM_1", "DEEP_ITM"}),
                                        strategy_name=strategy_name,
                                    )
                            else:
                                entered = False
                                status_flag = "VETO_MODE5_OR"
                                advisory = "WAIT (MODE5_OR_UNVERIFIED)"
                                self.record_veto("MODE5_OR", entry_or_reason)
                                self._defer_mode5_decision_trace_locked(
                                    index_name=index_name,
                                    bar_time=now_time,
                                    action="ABSTAIN",
                                    reason=entry_or_reason,
                                    details={"authorization_recheck": True},
                                    timestamp_ms=depth.exchange_timestamp_ms,
                                    candidate_generation=mode5_generation,
                                )
                            if entered:
                                self.daily_trade_counters[index_name] = curr_trades + 1
                                idx_apm.daily_trade_count = self.daily_trade_counters[index_name]
                                idx_apm._persist_wal_atomic(force_sync=True)
                                if rbfn_sig is not None and mode5_generation is not None:
                                    self._consume_cached_rbfn_candidate_locked(
                                        index_name, mode5_generation, "ENTRY_SUCCEEDED"
                                    )
                                self.journal.record_execution(
                                    position_id=pos_id,
                                    index_name=index_name,
                                    symbol=depth.symbol,
                                    direction=required_option_type,
                                    setup_reason=exec_reason,
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
                    # Reservation/candidate consumption happened under the state lock;
                    # the bounded writer persists telemetry independently.
                    self._dispatch_reserved_entry_then_flush_traces(entry_dispatch_request)
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

                            # Pure Algo Automated Order Dispatching on Exit
                            if self.automated_dispatcher:
                                if broker_instrument_key is not None:
                                    self.automated_dispatcher.on_apm_exit(
                                        index_name=index_name,
                                        symbol=broker_instrument_key,
                                        exit_price=float(lt_dict.get("opt_exit_ltp") or ltp),
                                        reason=str(lt_dict.get("exit_reason") or "LIQUIDATED"),
                                        qty=int(lt_dict.get("total_quantity") or 0),
                                        intent_id=str(lt_dict.get("position_id") or ""),
                                    )
                                else:
                                    self.record_veto(
                                        "BROKER_INSTRUMENT_KEY",
                                        "EXIT_DISPATCH_BLOCKED_MISSING_OR_MALFORMED_KEY",
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
