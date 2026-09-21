#!/usr/bin/env python3
"""
Governed Market Replay Engine: core.replay.governed_market_replay
Strictly non-trading, read-only market replay engine adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- orders_placed = 0
- orders_modified = 0
- orders_cancelled = 0

Feeds recorded market data through the exact canonical runtime path:
  ReplayClock -> StrategyMarketSnapshotBuilder -> StrategyShadowAdapterRegistry
Preserves strict causality: REPLAY_CLOCK <= EVENT_AVAILABLE_TIMESTAMP
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timezone, timedelta
from enum import Enum
import json
import logging
import math
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Literal, Mapping, Optional, Sequence, Tuple
import pandas as pd

from core.candidate_audits.intraday_opening_drive import (
    IST_TZ,
    calculate_intraday_drive_signal,
    calculate_spot_atm_strike,
    _extract_authoritative_contract_key,
    CANDIDATE_ID as OPENING_DRIVE_ID,
)
from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S4_ID,
)
from core.paper_shadow.strategy_shadow_adapter import (
    Bar1M,
    Level1Depth,
    StrategyMarketSnapshotV1,
    StrategyMarketSnapshotBuilder,
    StrategyShadowAdapterRegistry,
)

logger = logging.getLogger(__name__)


class UnsortedReplayStreamError(ValueError):
    """Raised when recorded events arrive out of temporal or causal sequence."""
    pass


class ReplayMode(str, Enum):
    EXACT_REPLAY = "EXACT_REPLAY"
    ACCELERATED_REPLAY = "ACCELERATED_REPLAY"
    FAULT_INJECTION_REPLAY = "FAULT_INJECTION_REPLAY"


@dataclass(frozen=True)
class ReplayEvent:
    event_timestamp_ist: datetime
    available_timestamp_ist: datetime
    symbol_data: Mapping[str, Any]
    session_id: str = "REPLAY_SESSION"
    feed_ok: bool = True
    websocket_ok: bool = True
    session_health: str = "NORMAL"

    def __post_init__(self):
        # Strict Causality Invariant: event cannot be available before it occurs in reality
        if self.available_timestamp_ist < self.event_timestamp_ist:
            raise ValueError(
                f"CAUSALITY_VIOLATION: available_timestamp ({self.available_timestamp_ist.isoformat()}) "
                f"is earlier than event_timestamp ({self.event_timestamp_ist.isoformat()})"
            )

    def is_causally_valid(self, clock_ist: datetime) -> bool:
        """Enforce monotonic causality: event cannot be visible before its available timestamp."""
        return clock_ist >= self.available_timestamp_ist


class ReplayClock:
    """
    Monotonic causal clock controlling simulated time.
    Strictly forbids time regression and enforces causality invariants.
    """

    def __init__(self, start_time_ist: datetime):
        self.current_time_ist: datetime = start_time_ist
        self.ticks_stepped: int = 0

    def step_to(self, target_time_ist: datetime) -> None:
        if target_time_ist < self.current_time_ist:
            raise UnsortedReplayStreamError(
                f"UNSORTED_REPLAY_STREAM: ReplayClock cannot step backwards in time "
                f"({target_time_ist.isoformat()} < {self.current_time_ist.isoformat()})"
            )
        self.current_time_ist = target_time_ist
        self.ticks_stepped += 1


@dataclass
class ReplayExecutionSummary:
    mode: ReplayMode
    session_id: str
    total_events_processed: int
    total_pulses_dispatched: int
    observations_captured: List[Dict[str, Any]]
    telemetry_checkpoints: List[Dict[str, Any]]
    shutdown_report: Dict[str, Any]
    causality_violations: int = 0
    option_execution_replay: str = "AVAILABLE"  # Or "UNAVAILABLE" for pure OHLCV bar replay
    read_only: bool = True
    broker_write_authority: bool = False
    order_authority: bool = False
    orders_placed: int = 0


class FaultInjector:
    """
    Deterministic chaos mutator for FAULT_INJECTION_REPLAY.
    Mutates specific events to verify fail-closed root-cause telemetry.
    """

    @staticmethod
    def delay_quote(event: ReplayEvent, delay_seconds: float) -> ReplayEvent:
        """Simulates latency drift by setting source timestamp far in the past."""
        data = dict(event.symbol_data)
        data["option_last_tick_age_sec"] = delay_seconds
        data["last_tick_age_sec"] = delay_seconds
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def swap_option_type(event: ReplayEvent) -> ReplayEvent:
        """Mutates CE to PE or vice versa."""
        data = dict(event.symbol_data)
        curr = str(data.get("option_type") or "").upper()
        swapped = "PE" if curr == "CE" else "CE"
        data["option_type"] = swapped
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def mutate_strike(event: ReplayEvent, strike_delta: float = 100.0) -> ReplayEvent:
        """Offsets the strike price away from the resolved ATM strike."""
        data = dict(event.symbol_data)
        if "strike_price" in data and data["strike_price"] is not None:
            data["strike_price"] = float(data["strike_price"]) + strike_delta
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def mutate_expiry(event: ReplayEvent, corrupt_expiry: str = "2026-12-31") -> ReplayEvent:
        """Sets an invalid or mismatched expiry."""
        data = dict(event.symbol_data)
        data["expiry"] = corrupt_expiry
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def cross_depth(event: ReplayEvent) -> ReplayEvent:
        """Injects crossed depth (ask < bid)."""
        data = dict(event.symbol_data)
        data["best_bid"] = 150.0
        data["best_ask"] = 140.0
        data["bid_qty"] = 100
        data["ask_qty"] = 100
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def set_session_health(event: ReplayEvent, health: str) -> ReplayEvent:
        """Injects session state e.g. HALTED or CIRCUIT_BREAKER."""
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=event.symbol_data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=health,
        )

    @staticmethod
    def remove_futures_key(event: ReplayEvent) -> ReplayEvent:
        """Purges authoritative futures contract key."""
        data = dict(event.symbol_data)
        data.pop("selected_futures_contract_key", None)
        data.pop("contract_key", None)
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def wrong_futures_contract(event: ReplayEvent, wrong_key: str = "NIFTY_WRONG_FUT") -> ReplayEvent:
        """Injects a mismatched futures contract key to simulate rollover failure."""
        data = dict(event.symbol_data)
        data["selected_futures_contract_key"] = wrong_key
        data["contract_key"] = wrong_key
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def missing_source_timestamp(event: ReplayEvent) -> ReplayEvent:
        """Removes exchange/source timestamp to simulate clock loss."""
        data = dict(event.symbol_data)
        data.pop("exchange_timestamp", None)
        data.pop("source_timestamp", None)
        data.pop("last_trade_time", None)
        data.pop("source_timestamp_epoch", None)
        data.pop("ts_epoch", None)
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def missing_expiry(event: ReplayEvent) -> ReplayEvent:
        """Removes expiry metadata from option quote."""
        data = dict(event.symbol_data)
        data.pop("expiry", None)
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def wrong_underlying(event: ReplayEvent, wrong_underlying: str = "BANKNIFTY") -> ReplayEvent:
        """Sets an invalid underlying key (e.g. BANKNIFTY instead of NIFTY)."""
        data = dict(event.symbol_data)
        data["underlying"] = wrong_underlying
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def zero_bid_qty(event: ReplayEvent) -> ReplayEvent:
        """Sets bid quantity to 0."""
        data = dict(event.symbol_data)
        data["bid_qty"] = 0
        data["bid_quantity"] = 0
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def zero_ask_qty(event: ReplayEvent) -> ReplayEvent:
        """Sets ask quantity to 0."""
        data = dict(event.symbol_data)
        data["ask_qty"] = 0
        data["ask_quantity"] = 0
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def nan_bid(event: ReplayEvent) -> ReplayEvent:
        """Sets best bid to float('nan')."""
        data = dict(event.symbol_data)
        data["best_bid"] = float("nan")
        data["bid"] = float("nan")
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def inf_ask(event: ReplayEvent) -> ReplayEvent:
        """Sets best ask to float('inf')."""
        data = dict(event.symbol_data)
        data["best_ask"] = float("inf")
        data["ask"] = float("inf")
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def feed_degraded(event: ReplayEvent) -> ReplayEvent:
        """Sets feed_ok=False."""
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=event.symbol_data,
            session_id=event.session_id,
            feed_ok=False,
            websocket_ok=event.websocket_ok,
            session_health=event.session_health,
        )

    @staticmethod
    def websocket_degraded(event: ReplayEvent) -> ReplayEvent:
        """Sets websocket_ok=False."""
        return ReplayEvent(
            event_timestamp_ist=event.event_timestamp_ist,
            available_timestamp_ist=event.available_timestamp_ist,
            symbol_data=event.symbol_data,
            session_id=event.session_id,
            feed_ok=event.feed_ok,
            websocket_ok=False,
            session_health=event.session_health,
        )


class ParquetBarReplaySource:
    """
    Causal Replay Source for canonical 1-minute OHLCV datasets (e.g. data/nifty_ohlc_wfa.parquet).
    Enforces strict bar completion semantics:
      A 1-minute bar starting at HH:MM:00 IST is completed and available at HH:MM:00 + 60s.
    """

    def __init__(
        self,
        parquet_path: Path | str,
        session_dates: Optional[Sequence[date | str]] = None,
        symbol: str = "NIFTY 50",
        instrument_type: str = "INDEX",
        segment: str = "INDICES",
    ):
        self.parquet_path = Path(parquet_path)
        self.session_dates = {str(d)[:10] for d in session_dates} if session_dates else None
        self.symbol = symbol
        self.instrument_type = instrument_type
        self.segment = segment

    def stream_events(self) -> Iterator[ReplayEvent]:
        import pandas as pd
        if not self.parquet_path.exists():
            raise FileNotFoundError(f"Parquet bar file not found: {self.parquet_path}")

        df = pd.read_parquet(self.parquet_path)

        # Filter symbol if present
        if "symbol" in df.columns:
            df = df[df["symbol"] == self.symbol]

        # Convert timestamp to IST datetime
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Filter session dates if specified
        if self.session_dates:
            df["_date_str"] = df["timestamp"].dt.strftime("%Y-%m-%d")
            df = df[df["_date_str"].isin(self.session_dates)]
            df = df.drop(columns=["_date_str"])

        df = df.sort_values("timestamp", ascending=True)

        for _, row in df.iterrows():
            ts = row["timestamp"]
            if ts.tzinfo is None:
                dt_ist = ts.replace(tzinfo=IST_TZ)
            else:
                dt_ist = ts.astimezone(IST_TZ)

            available_ts = dt_ist + timedelta(seconds=60)
            open_p = float(row["open"])
            high_p = float(row["high"]) if "high" in row else open_p
            low_p = float(row["low"]) if "low" in row else open_p
            close_p = float(row["close"])
            vol = int(row["volume"]) if "volume" in row and not pd.isna(row["volume"]) else 0

            sym_data = {
                "symbol": self.symbol,
                "instrument_type": self.instrument_type,
                "segment": self.segment,
                "bar_open": open_p,
                "bar_high": high_p,
                "bar_low": low_p,
                "bar_close": close_p,
                "bar_volume": vol,
                "bar_timestamp_epoch": dt_ist.timestamp(),
                "bar_timestamp_ist": dt_ist.isoformat(),
                "exchange_timestamp": available_ts.isoformat(),
                "option_last_tick_age_sec": 0.05,
            }

            yield ReplayEvent(
                event_timestamp_ist=dt_ist,
                available_timestamp_ist=available_ts,
                symbol_data=sym_data,
                session_id=dt_ist.strftime("%Y-%m-%d"),
                feed_ok=True,
                websocket_ok=True,
                session_health="NORMAL",
            )


class UpstoxTickReplaySource:
    """
    Causal Replay Source for real Upstox stitched tick/depth parquet files.
    Streams tick-by-tick Level 1 depth quotes in strict monotonic causality.
    """

    def __init__(
        self,
        parquet_path: Path | str,
        target_symbols: Optional[Sequence[str]] = None,
        max_events: Optional[int] = None,
    ):
        self.parquet_path = Path(parquet_path)
        self.target_symbols = set(target_symbols) if target_symbols else None
        self.max_events = max_events

    def stream_events(self) -> Iterator[ReplayEvent]:
        import pyarrow.dataset as ds
        if not self.parquet_path.exists():
            raise FileNotFoundError(f"Upstox stitched parquet file not found: {self.parquet_path}")

        dataset = ds.dataset(self.parquet_path, format="parquet")

        filter_expr = None
        if self.target_symbols:
            filter_expr = ds.field("symbol").isin(list(self.target_symbols))

        scanner = dataset.scanner(filter=filter_expr)

        yielded_count = 0
        for batch in scanner.to_batches():
            df_b = batch.to_pandas()
            df_b = df_b.sort_values("ts", ascending=True)

            for _, row in df_b.iterrows():
                ts_epoch = float(row["ts"])
                if ts_epoch <= 0 or not math.isfinite(ts_epoch):
                    continue

                dt_ist = datetime.fromtimestamp(ts_epoch, tz=IST_TZ)
                # Parse recorded depth JSON. Missing/unparseable quantities remain UNKNOWN;
                # never synthesize executable depth.
                raw_depth = row.get("depth")
                bid_qty: Optional[int] = None
                ask_qty: Optional[int] = None
                if isinstance(raw_depth, str) and raw_depth.strip():
                    try:
                        d_dict = json.loads(raw_depth)
                        bids = d_dict.get("bids", [])
                        asks = d_dict.get("asks", [])
                        if bids and bids[0].get("quantity") is not None:
                            bid_qty = int(bids[0]["quantity"])
                        if asks and asks[0].get("quantity") is not None:
                            ask_qty = int(asks[0]["quantity"])
                    except Exception:
                        bid_qty = None
                        ask_qty = None

                raw_sym = str(row["symbol"])
                inst_type = "INDEX"
                seg = "INDICES"
                opt_type = None
                strike_val = None
                exp_str = None

                if " CE " in raw_sym or " PE " in raw_sym:
                    inst_type = "OPT"
                    seg = "NFO-OPT"
                    parts = raw_sym.strip().split()
                    if len(parts) >= 4:
                        opt_type = parts[2].upper()
                        try:
                            strike_val = float(parts[1])
                        except Exception:
                            strike_val = None
                        if len(parts) >= 6:
                            # e.g. "15 SEP 26" -> standard format
                            exp_str = f"{parts[3]} {parts[4]} {parts[5]}"

                sym_data = {
                    "symbol": raw_sym,
                    "instrument_type": inst_type,
                    "segment": seg,
                    "best_bid": float(row["bid"]) if "bid" in row and not pd.isna(row["bid"]) else 0.0,
                    "best_ask": float(row["ask"]) if "ask" in row and not pd.isna(row["ask"]) else 0.0,
                    "bid_qty": bid_qty,
                    "ask_qty": ask_qty,
                    "underlying": "NIFTY" if "NIFTY" in raw_sym else None,
                    "strike_price": strike_val,
                    "option_type": opt_type,
                    "expiry": exp_str,
                    "exchange_timestamp": dt_ist.isoformat(),
                    "source_timestamp_epoch": ts_epoch,
                    # The stitched capture does not establish broker-local receipt latency.
                    # Keep freshness UNKNOWN unless an explicit receipt field exists.
                    "option_last_tick_age_sec": None,
                    "receipt_timestamp_authority": "UNAVAILABLE",
                    "depth_quantity_authority": "RECORDED" if (bid_qty is not None and ask_qty is not None) else "UNAVAILABLE",
                }

                # Use a recorded local receipt timestamp only when the dataset actually has one.
                receipt_epoch = None
                for receipt_col in ("receipt_ts", "received_ts", "received_epoch", "receipt_timestamp_epoch"):
                    if receipt_col in row and not pd.isna(row[receipt_col]):
                        try:
                            receipt_epoch = float(row[receipt_col])
                            if not math.isfinite(receipt_epoch) or receipt_epoch <= 0:
                                receipt_epoch = None
                        except Exception:
                            receipt_epoch = None
                        if receipt_epoch is not None:
                            break
                available_dt = datetime.fromtimestamp(receipt_epoch, tz=IST_TZ) if receipt_epoch is not None else dt_ist
                if receipt_epoch is not None:
                    sym_data["option_last_tick_age_sec"] = max(0.0, receipt_epoch - ts_epoch)
                    sym_data["receipt_timestamp_authority"] = "RECORDED"

                yield ReplayEvent(
                    event_timestamp_ist=dt_ist,
                    available_timestamp_ist=available_dt,
                    symbol_data=sym_data,
                    session_id=dt_ist.strftime("%Y-%m-%d"),
                    feed_ok=True,
                    websocket_ok=True,
                    session_health="NORMAL",
                )
                yielded_count += 1
                if self.max_events and yielded_count >= self.max_events:
                    return


@dataclass(frozen=True)
class OpeningDriveReplayCapability:
    full_end_to_end_available: bool
    missing_primitives: Tuple[str, ...]


def assess_opening_drive_replay_capability(events: Sequence[ReplayEvent]) -> OpeningDriveReplayCapability:
    """Determine whether a recorded stream can drive Opening Drive without manual state priming."""
    have_fut_0915 = False
    have_fut_0920 = False
    have_spot_0920 = False
    have_option = False
    for ev in events:
        d = ev.symbol_data
        inst = str(d.get("instrument_type") or "").upper()
        seg = str(d.get("segment") or "").upper()
        bar_ts = d.get("bar_timestamp_ist")
        if not bar_ts and d.get("bar_timestamp_epoch") is not None:
            try:
                bar_ts = datetime.fromtimestamp(float(d["bar_timestamp_epoch"]), tz=IST_TZ).isoformat()
            except Exception:
                bar_ts = None
        bar_time = None
        if bar_ts:
            try:
                bar_time = datetime.fromisoformat(str(bar_ts)).astimezone(IST_TZ).time()
            except Exception:
                bar_time = None
        if inst in ("FUT", "FUTURES") or seg in ("NFO-FUT", "NSE-FUT"):
            have_fut_0915 = have_fut_0915 or bar_time == dtime(9, 15)
            have_fut_0920 = have_fut_0920 or bar_time == dtime(9, 20)
        elif inst in ("INDEX", "SPOT") or seg in ("INDICES", "NSE-INDICES"):
            have_spot_0920 = have_spot_0920 or bar_time == dtime(9, 20)
        elif inst in ("OPT", "OPTION", "CE", "PE") or seg in ("NFO-OPT", "NSE-OPT"):
            have_option = True

    missing: List[str] = []
    if not have_fut_0915:
        missing.append("FUTURES_0915_BAR")
    if not have_fut_0920:
        missing.append("FUTURES_0920_BAR")
    if not have_spot_0920:
        missing.append("SPOT_0920_BAR")
    if not have_option:
        missing.append("OPTION_TICKS")
    return OpeningDriveReplayCapability(full_end_to_end_available=not missing, missing_primitives=tuple(missing))


class GovernedMarketReplayEngine:
    """
    Canonical Governed Market Replay Engine.
    Streams recorded events through StrategyMarketSnapshotBuilder -> StrategyShadowAdapterRegistry.
    """

    def __init__(
        self,
        session_id: str,
        source_sha: str,
        evidence_root: Path | str,
        mode: ReplayMode = ReplayMode.EXACT_REPLAY,
        opening_drive_prev_contract_key: Optional[str] = None,
        opening_drive_prev_close_1529: Optional[float] = None,
        opening_drive_target_expiry: Optional[str] = None,
        overnight_prev_daily_close: Optional[float] = None,
        overnight_prev_sma200: Optional[float] = None,
        option_execution_available: bool = True,
    ):
        self.session_id = session_id
        self.source_sha = source_sha
        self.evidence_root = Path(evidence_root)
        self.mode = mode
        self.option_execution_available = option_execution_available

        # Safety Invariants
        self.read_only: bool = True
        self.broker_write_authority: bool = False
        self.order_authority: bool = False
        self.orders_placed: int = 0

        # Registry under test
        self.registry = StrategyShadowAdapterRegistry(
            session_id=self.session_id,
            source_sha=self.source_sha,
            evidence_root=self.evidence_root,
            opening_drive_prev_contract_key=opening_drive_prev_contract_key,
            opening_drive_prev_close_1529=opening_drive_prev_close_1529,
            opening_drive_target_expiry=opening_drive_target_expiry,
            overnight_prev_daily_close=overnight_prev_daily_close,
            overnight_prev_sma200=overnight_prev_sma200,
        )

        self.clock: Optional[ReplayClock] = None
        self.observations_captured: List[Dict[str, Any]] = []
        self.causality_violations: int = 0
        self.pulses_dispatched: int = 0

    def replay_session(
        self,
        events: Sequence[ReplayEvent],
        pulse_frequency_seconds: float = 60.0,
    ) -> ReplayExecutionSummary:
        """
        Executes causal market replay across a sequence of ReplayEvents.
        """
        if not events:
            raise ValueError("No events supplied to replay_session")

        # Initialize clock with first event's available time
        self.clock = ReplayClock(start_time_ist=events[0].available_timestamp_ist)

        total_events = 0
        for idx, ev in enumerate(events):
            # 1. Monotonic clock advance and strict stream ordering enforcement
            if ev.available_timestamp_ist < self.clock.current_time_ist:
                raise UnsortedReplayStreamError(
                    f"UNSORTED_REPLAY_STREAM at event {idx}: available_timestamp "
                    f"({ev.available_timestamp_ist.isoformat()}) is earlier than current replay clock "
                    f"({self.clock.current_time_ist.isoformat()})"
                )
            if ev.available_timestamp_ist > self.clock.current_time_ist:
                self.clock.step_to(ev.available_timestamp_ist)

            # 2. Strict Causality Check
            if not ev.is_causally_valid(self.clock.current_time_ist):
                self.causality_violations += 1
                logger.error(
                    "CAUSALITY_VIOLATION at event %d: clock=%s < available=%s",
                    idx,
                    self.clock.current_time_ist.isoformat(),
                    ev.available_timestamp_ist.isoformat(),
                )
                continue

            total_events += 1

            # 3. Formulate canonical pulse payload
            pulse_id = f"REPLAY_PULSE_{self.pulses_dispatched + 1:06d}"

            class ReplayPulseMock:
                def __init__(self, p_id: str, ts_epoch: float):
                    self.pulse_id = p_id
                    self.timestamp_epoch = ts_epoch

            current_epoch = self.clock.current_time_ist.timestamp()
            pulse_obj = ReplayPulseMock(pulse_id, current_epoch)

            feed_truth = {
                "feed_ok": ev.feed_ok,
                "websocket_ok": ev.websocket_ok,
                "context": {
                    "session_id": ev.session_id,
                    "session_health": ev.session_health,
                },
                "symbols": [ev.symbol_data],
            }

            # 4. Dispatch through canonical registry
            res = self.registry.on_pulse(
                pulse=pulse_obj,
                market_snapshot={"market_open": True},
                feed_health_truth=feed_truth,
            )
            self.pulses_dispatched += 1
            if res:
                self.observations_captured.extend(res)

        # 5. Shutdown and evidence sealing
        shutdown_rep = self.registry.on_session_shutdown()

        # Load telemetry checkpoints emitted
        telemetry: List[Dict[str, Any]] = []
        if self.registry.checkpoints_path.is_file():
            with self.registry.checkpoints_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        telemetry.append(json.loads(line.strip()))

        return ReplayExecutionSummary(
            mode=self.mode,
            session_id=self.session_id,
            total_events_processed=total_events,
            total_pulses_dispatched=self.pulses_dispatched,
            observations_captured=list(self.observations_captured),
            telemetry_checkpoints=telemetry,
            shutdown_report=shutdown_rep,
            causality_violations=self.causality_violations,
            option_execution_replay="AVAILABLE" if self.option_execution_available else "UNAVAILABLE",
            read_only=True,
            broker_write_authority=False,
            order_authority=False,
            orders_placed=0,
        )


class DualReplayReconciler:
    """
    Reconciles online replay observations with post-session reference runner output.
    Ensures: ONLINE_REPLAY == AFTER_SESSION_REFERENCE
    """

    @staticmethod
    def reconcile_opening_drive(
        online_obs: Mapping[str, Any],
        reference_obs: Mapping[str, Any],
    ) -> Tuple[bool, List[str]]:
        """
        Compares all causal fields between online replay and offline reference.
        """
        discrepancies: List[str] = []

        keys_to_compare = [
            ("candidate_id", "candidate_id"),
            ("signal_side", "signal_side"),
            ("strike", "strike"),
            ("option_type", "option_type"),
            ("entry_fill", "entry_fill"),
            ("exit_fill", "exit_fill"),
        ]

        for on_k, ref_k in keys_to_compare:
            on_v = online_obs.get(on_k)
            ref_v = reference_obs.get(ref_k)
            if on_v != ref_v:
                discrepancies.append(f"FIELD_MISMATCH: {on_k} (online={on_v} vs reference={ref_v})")

        # Numeric gross PnL check with tolerance
        if "gross_pnl_pts" in online_obs and "gross_pnl_pts" in reference_obs:
            diff = abs(float(online_obs["gross_pnl_pts"]) - float(reference_obs["gross_pnl_pts"]))
            if diff > 1e-4:
                discrepancies.append(
                    f"PNL_MISMATCH: online={online_obs['gross_pnl_pts']} vs reference={reference_obs['gross_pnl_pts']}"
                )

        match = (len(discrepancies) == 0)
        return match, discrepancies

    @staticmethod
    def reconcile_opening_drive_against_reference_runner(
        online_obs: Mapping[str, Any],
        prev_session_df: Any,
        curr_session_df: Any,
        capture_dir: str,
    ) -> Tuple[bool, List[str], Optional[Mapping[str, Any]]]:
        """Run the frozen after-session reference independently and reconcile its output."""
        from dataclasses import asdict
        from core.paper_shadow.run_intraday_opening_drive_shadow import run_intraday_shadow_for_session

        ref = run_intraday_shadow_for_session(
            prev_session_df=prev_session_df,
            curr_session_df=curr_session_df,
            capture_dir=capture_dir,
            verification_mode="REPLAY_INDEPENDENT_REFERENCE",
        )
        if ref is None:
            return False, ["REFERENCE_RUNNER_RETURNED_NONE"], None
        ref_dict = asdict(ref)
        normalized_ref = {
            "candidate_id": ref_dict.get("candidate_id"),
            "signal_side": "BUY_CE" if ref_dict.get("signal_side") == "LONG" else ("BUY_PE" if ref_dict.get("signal_side") == "SHORT" else ref_dict.get("signal_side")),
            "strike": ref_dict.get("atm_strike"),
            "option_type": "CE" if ref_dict.get("signal_side") == "LONG" else ("PE" if ref_dict.get("signal_side") == "SHORT" else None),
            "entry_fill": ref_dict.get("entry_fill"),
            "exit_fill": ref_dict.get("exit_fill"),
            "gross_pnl_pts": ref_dict.get("gross_premium_pts"),
        }
        matched, discrepancies = DualReplayReconciler.reconcile_opening_drive(online_obs, normalized_ref)
        return matched, discrepancies, ref_dict
