#!/usr/bin/env python3
"""
Governed Strategy Shadow Adapter Architecture
Strictly non-trading, read-only shadow observer adapters adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- orders_placed = 0
- orders_modified = 0
- orders_cancelled = 0

Authoritative binding from central Market Spine / Pulse to frozen strategy candidates:
1. INTRADAY_OPENING_DRIVE_V1 (PR #924)
2. S1_MOMENTUM_OVERNIGHT_V1 (PR #925)
3. S4_MONDAY_OVERNIGHT_V1 (PR #925)
"""

from __future__ import annotations
import abc
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dtime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

from core.candidate_audits.intraday_opening_drive import (
    CANDIDATE_ID as OPENING_DRIVE_ID,
    CANDIDATE_FINGERPRINT as OPENING_DRIVE_FINGERPRINT,
    calculate_spot_atm_strike,
    IST_TZ,
)
from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S1_SCHEDULE_SHA256,
    CANDIDATE_S4_ID,
    CANDIDATE_S4_SCHEDULE_SHA256,
    evaluate_overnight_signal,
    OvernightSignalResult,
    load_and_validate_frozen_spec,
)
from core.read_only_observers.overnight_drift_observer import (
    TamperEvidentLedgerManager,
    ObserverLifecycleState,
    calculate_internal_quote_freshness,
)

logger = logging.getLogger(__name__)


import math

# ---------------------------------------------------------------------------
# Canonical Snapshot Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Level1Depth:
    bid_price: float
    bid_qty: Optional[int]
    ask_price: float
    ask_qty: Optional[int]

    def is_valid(self) -> bool:
        return (
            math.isfinite(self.bid_price)
            and math.isfinite(self.ask_price)
            and self.bid_price > 0.0
            and self.ask_price > 0.0
            and self.ask_price >= self.bid_price
            and self.bid_qty is not None
            and self.ask_qty is not None
            and self.bid_qty > 0
            and self.ask_qty > 0
        )


@dataclass(frozen=True)
class Bar1M:
    timestamp_ist: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class StrategyMarketSnapshotV1:
    session_id: str
    instrument_key: str
    trading_symbol: str
    instrument_class: Literal["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTION"]
    receipt_timestamp_ist: datetime
    source_timestamp_ist: Optional[datetime] = None
    age_ms: Optional[float] = None
    feed_health: Literal["HEALTHY", "DEGRADED", "STALE", "HALTED"] = "HEALTHY"
    session_health: Literal["NORMAL", "HALTED", "CIRCUIT_BREAKER", "POST_CLOSE"] = "NORMAL"

    # Depth and Bars
    l1_depth: Optional[Level1Depth] = None
    last_completed_1m_bar: Optional[Bar1M] = None

    # Derivatives metadata
    authoritative_contract_key: Optional[str] = None
    underlying_key: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[Literal["CE", "PE"]] = None
    lot_size: Optional[int] = None

    def central_feed_valid(self, max_central_age_ms: float = 5000.0) -> bool:
        if self.session_health in ("HALTED", "CIRCUIT_BREAKER"):
            return False
        if self.feed_health != "HEALTHY":
            return False
        if self.source_timestamp_ist is None:
            return False
        if self.age_ms is None or not math.isfinite(self.age_ms):
            return False
        return self.age_ms <= max_central_age_ms


@dataclass(frozen=True)
class CheckpointTelemetry:
    pulse_id: str
    candidate_id: str
    checkpoint_name: str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    root_cause: Optional[str] = None
    designed_threshold: Optional[str] = None
    observed_value: Optional[str] = None

    def log_format(self) -> str:
        if self.status == "PASS":
            return f"PULSE_ID={self.pulse_id} CANDIDATE_ID={self.candidate_id} CHECKPOINT={self.checkpoint_name} STATUS=PASS"
        return (
            f"PULSE_ID={self.pulse_id} CANDIDATE_ID={self.candidate_id} CHECKPOINT={self.checkpoint_name} "
            f"STATUS=FAIL ROOT_CAUSE={self.root_cause} DESIGNED={self.designed_threshold} OBSERVED={self.observed_value}"
        )


# ---------------------------------------------------------------------------
# Base Shadow Adapter
# ---------------------------------------------------------------------------

class StrategyShadowAdapter(abc.ABC):
    def __init__(self, candidate_id: str, candidate_digest: str, max_quote_age_ms: float):
        self.candidate_id = candidate_id
        self.candidate_digest = candidate_digest
        self.max_quote_age_ms = max_quote_age_ms
        self.read_only: bool = True
        self.broker_write_authority: bool = False
        self.order_authority: bool = False
        self.orders_placed: int = 0
        self.telemetry_history: List[CheckpointTelemetry] = []

    def record_checkpoint(
        self,
        pulse_id: str,
        checkpoint_name: str,
        status: Literal["PASS", "FAIL", "SKIPPED"],
        root_cause: Optional[str] = None,
        designed: Optional[str] = None,
        observed: Optional[str] = None,
    ) -> CheckpointTelemetry:
        telemetry = CheckpointTelemetry(
            pulse_id=pulse_id,
            candidate_id=self.candidate_id,
            checkpoint_name=checkpoint_name,
            status=status,
            root_cause=root_cause,
            designed_threshold=designed,
            observed_value=observed,
        )
        self.telemetry_history.append(telemetry)
        return telemetry

    @abc.abstractmethod
    def on_market_pulse(self, pulse_id: str, snapshot: StrategyMarketSnapshotV1) -> Optional[Dict[str, Any]]:
        """Processes incoming canonical snapshot pulse in a strictly read-only manner."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Intraday Opening Drive Shadow Adapter (PR #924)
# ---------------------------------------------------------------------------

class IntradayOpeningDriveShadowAdapter(StrategyShadowAdapter):
    """
    Online event adapter for INTRADAY_OPENING_DRIVE_V1.
    Receives StrategyMarketSnapshotV1 from central market spine.
    Strictly observes option quotes >09:22:00 for entry and >11:01:00 for exit.
    """

    def __init__(
        self,
        prev_futures_contract_key: Optional[str] = None,
        prev_close_1529: Optional[float] = None,
        target_expiry: Optional[str] = None,
        max_quote_age_ms: float = 2000.0,
    ):
        super().__init__(
            candidate_id=OPENING_DRIVE_ID,
            candidate_digest=OPENING_DRIVE_FINGERPRINT,
            max_quote_age_ms=max_quote_age_ms,
        )
        self.prev_futures_contract_key = prev_futures_contract_key
        self.prev_close_1529 = prev_close_1529
        self.target_expiry = target_expiry

        # State tracking
        self.futures_open_0915: Optional[float] = None
        self.futures_close_0920: Optional[float] = None
        self.curr_futures_contract_key: Optional[str] = None
        self.signal_side: Optional[Literal["BUY_CE", "BUY_PE"]] = None
        self.signal_qualified: bool = False
        self.resolved_atm_strike: Optional[int] = None
        self.resolved_option_type: Optional[Literal["CE", "PE"]] = None
        self.resolved_option_instrument_key: Optional[str] = None

        # Shadow Observation captures
        self.shadow_entry_observed: bool = False
        self.shadow_entry_price: Optional[float] = None
        self.shadow_entry_ts: Optional[str] = None
        self.shadow_exit_observed: bool = False
        self.shadow_exit_price: Optional[float] = None
        self.shadow_exit_ts: Optional[str] = None
        self.observation_finalized: bool = False

    def on_market_pulse(self, pulse_id: str, snapshot: StrategyMarketSnapshotV1) -> Optional[Dict[str, Any]]:
        # 1. Central feed health check
        if not snapshot.central_feed_valid():
            self.record_checkpoint(
                pulse_id=pulse_id,
                checkpoint_name="FEED_RECEIVED",
                status="FAIL",
                root_cause="MISSING_SOURCE_TIMESTAMP" if (snapshot.source_timestamp_ist is None or snapshot.age_ms is None) else "CENTRAL_FEED_UNHEALTHY_OR_STALE",
                designed="feed_health==HEALTHY and central_age<=5000ms",
                observed=f"health={snapshot.feed_health}, age_ms={snapshot.age_ms}",
            )
            return None

        # 2. Local freshness SLA check
        if snapshot.age_ms is None or snapshot.age_ms > self.max_quote_age_ms:
            self.record_checkpoint(
                pulse_id=pulse_id,
                checkpoint_name="FEED_RECEIVED",
                status="FAIL",
                root_cause="QUOTE_EXCEEDS_LOCAL_SLA" if snapshot.age_ms is not None else "MISSING_SOURCE_TIMESTAMP",
                designed=f"age_ms<={self.max_quote_age_ms}",
                observed=str(snapshot.age_ms),
            )
            return None

        self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="FEED_RECEIVED", status="PASS")
        t = snapshot.source_timestamp_ist.time()

        # Handle NIFTY Futures
        if snapshot.instrument_class == "INDEX_FUTURES":
            self.curr_futures_contract_key = snapshot.authoritative_contract_key

            # Checkpoint: Futures contract authority & continuity
            if not self.curr_futures_contract_key or (
                self.prev_futures_contract_key is not None
                and self.curr_futures_contract_key != self.prev_futures_contract_key
            ):
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="FUTURES_CONTRACT_AUTH",
                    status="FAIL",
                    root_cause="CONTRACT_MISMATCH_OR_ROLLOVER",
                    designed=f"curr=={self.prev_futures_contract_key}",
                    observed=str(self.curr_futures_contract_key),
                )
                return None
            self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="FUTURES_CONTRACT_AUTH", status="PASS")

            # Capture 09:15 open and 09:20 close
            if snapshot.last_completed_1m_bar:
                bar_t = snapshot.last_completed_1m_bar.timestamp_ist.time()
                if bar_t == dtime(9, 15):
                    self.futures_open_0915 = snapshot.last_completed_1m_bar.open
                elif bar_t == dtime(9, 20):
                    self.futures_close_0920 = snapshot.last_completed_1m_bar.close
                    # Evaluate Drive Signal
                    if self.prev_close_1529 and self.futures_open_0915 and self.futures_close_0920:
                        gap = self.futures_open_0915 - self.prev_close_1529
                        drive = self.futures_close_0920 - self.futures_open_0915
                        if gap > 30.0 and drive > 20.0:
                            self.signal_side = "BUY_CE"
                            self.resolved_option_type = "CE"
                            self.signal_qualified = True
                        elif gap < -30.0 and drive < -20.0:
                            self.signal_side = "BUY_PE"
                            self.resolved_option_type = "PE"
                            self.signal_qualified = True
                        else:
                            self.signal_qualified = False

                        self.record_checkpoint(
                            pulse_id=pulse_id,
                            checkpoint_name="SIGNAL_EVALUATED",
                            status="PASS",
                            observed=f"qualified={self.signal_qualified}, side={self.signal_side}",
                        )

        # Handle NIFTY Spot (ATM resolution at 09:20)
        elif snapshot.instrument_class == "INDEX_SPOT" and self.signal_qualified:
            if snapshot.last_completed_1m_bar and snapshot.last_completed_1m_bar.timestamp_ist.time() == dtime(9, 20):
                spot_close = snapshot.last_completed_1m_bar.close
                self.resolved_atm_strike = calculate_spot_atm_strike(spot_close)
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="SPOT_ATM_RESOLVED",
                    status="PASS",
                    observed=f"strike={self.resolved_atm_strike}",
                )

        # Handle Option Depth (Entry observation > 09:22:00, Exit > 11:01:00)
        elif snapshot.instrument_class == "INDEX_OPTION" and self.signal_qualified and not self.observation_finalized:
            # 1. Option contract identity gating
            if self.resolved_atm_strike is None or self.resolved_option_type is None:
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="OPTION_CONTRACT_VERIFIED",
                    status="FAIL",
                    root_cause="ATM_OR_OPTION_TYPE_NOT_RESOLVED",
                    designed="resolved_atm_strike and resolved_option_type are set",
                    observed=f"strike={self.resolved_atm_strike}, type={self.resolved_option_type}",
                )
                return None

            # Fail closed on missing structured option metadata
            if snapshot.strike_price is None or snapshot.option_type is None:
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="OPTION_CONTRACT_VERIFIED",
                    status="FAIL",
                    root_cause="MISSING_OPTION_METADATA",
                    designed="strike_price and option_type are not None",
                    observed=f"strike={snapshot.strike_price}, type={snapshot.option_type}",
                )
                return None

            # Verify underlying key
            if snapshot.underlying_key and snapshot.underlying_key != "NIFTY":
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="OPTION_CONTRACT_VERIFIED",
                    status="FAIL",
                    root_cause="OPTION_UNDERLYING_MISMATCH",
                    designed="NIFTY",
                    observed=str(snapshot.underlying_key),
                )
                return None

            # Verify contract strike match
            if float(snapshot.strike_price) != float(self.resolved_atm_strike):
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="OPTION_CONTRACT_VERIFIED",
                    status="FAIL",
                    root_cause="OPTION_STRIKE_MISMATCH",
                    designed=str(self.resolved_atm_strike),
                    observed=str(snapshot.strike_price),
                )
                return None

            # Verify contract option type match
            if snapshot.option_type != self.resolved_option_type:
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="OPTION_CONTRACT_VERIFIED",
                    status="FAIL",
                    root_cause="OPTION_TYPE_MISMATCH",
                    designed=str(self.resolved_option_type),
                    observed=str(snapshot.option_type),
                )
                return None

            # Verify target expiry match if specified
            if self.target_expiry is not None:
                if snapshot.expiry_date is None:
                    self.record_checkpoint(
                        pulse_id=pulse_id,
                        checkpoint_name="OPTION_CONTRACT_VERIFIED",
                        status="FAIL",
                        root_cause="MISSING_EXPIRY_METADATA",
                        designed=self.target_expiry,
                        observed="None",
                    )
                    return None
                if snapshot.expiry_date != self.target_expiry:
                    self.record_checkpoint(
                        pulse_id=pulse_id,
                        checkpoint_name="OPTION_CONTRACT_VERIFIED",
                        status="FAIL",
                        root_cause="OPTION_EXPIRY_MISMATCH",
                        designed=self.target_expiry,
                        observed=str(snapshot.expiry_date),
                    )
                    return None

            self.record_checkpoint(
                pulse_id=pulse_id,
                checkpoint_name="OPTION_CONTRACT_VERIFIED",
                status="PASS",
                observed=f"contract={snapshot.trading_symbol}, strike={self.resolved_atm_strike}, type={self.resolved_option_type}",
            )

            if snapshot.l1_depth and snapshot.l1_depth.is_valid():
                # Entry window: strictly after 09:22:00
                if not self.shadow_entry_observed and t > dtime(9, 22):
                    self.shadow_entry_observed = True
                    self.shadow_entry_price = snapshot.l1_depth.ask_price  # Long buys at ask
                    self.shadow_entry_ts = snapshot.source_timestamp_ist.isoformat()
                    self.record_checkpoint(
                        pulse_id=pulse_id,
                        checkpoint_name="SHADOW_ENTRY_SEALED",
                        status="PASS",
                        observed=f"entry_ask={self.shadow_entry_price}",
                    )
                # Exit window: strictly after 11:01:00
                elif self.shadow_entry_observed and not self.shadow_exit_observed and t > dtime(11, 1):
                    self.shadow_exit_observed = True
                    self.shadow_exit_price = snapshot.l1_depth.bid_price  # Long sells at bid
                    self.shadow_exit_ts = snapshot.source_timestamp_ist.isoformat()
                    self.observation_finalized = True
                    self.record_checkpoint(
                        pulse_id=pulse_id,
                        checkpoint_name="SHADOW_EXIT_SEALED",
                        status="PASS",
                        observed=f"exit_bid={self.shadow_exit_price}",
                    )
                    return {
                        "candidate_id": self.candidate_id,
                        "fingerprint": self.candidate_digest,
                        "signal_side": self.signal_side,
                        "strike": self.resolved_atm_strike,
                        "option_type": self.resolved_option_type,
                        "entry_time": self.shadow_entry_ts,
                        "entry_fill": self.shadow_entry_price,
                        "exit_time": self.shadow_exit_ts,
                        "exit_fill": self.shadow_exit_price,
                        "gross_pnl_pts": (self.shadow_exit_price - self.shadow_entry_price) if (self.shadow_entry_price and self.shadow_exit_price) else 0.0,
                        "read_only": True,
                        "broker_write_authority": False,
                        "order_authority": False,
                        "orders_placed": 0,
                    }
        return None


# ---------------------------------------------------------------------------
# Overnight Drift Shadow Adapter (PR #925)
# ---------------------------------------------------------------------------

class OvernightDriftShadowAdapter(StrategyShadowAdapter):
    """
    Online event adapter for S1_MOMENTUM_OVERNIGHT_V1 & S4_MONDAY_OVERNIGHT_V1.
    Handles cross-session persistence via TamperEvidentLedgerManager.
    """

    def __init__(
        self,
        candidate_id: str,
        schedule_sha256: str,
        prev_daily_close: float,
        prev_sma200: float,
        sub_ledger_dir: str = "runtime/prospective_observations/overnight_drift",
        max_quote_age_ms: float = 5000.0,
    ):
        super().__init__(
            candidate_id=candidate_id,
            candidate_digest=schedule_sha256,
            max_quote_age_ms=max_quote_age_ms,
        )
        self.prev_daily_close = prev_daily_close
        self.prev_sma200 = prev_sma200
        self.sub_ledger = "S1_ONLY" if candidate_id == CANDIDATE_S1_ID else "S4_ONLY"
        self.candidate_spec = load_and_validate_frozen_spec(candidate_id)
        self.ledger_manager = TamperEvidentLedgerManager(
            ledger_dir=sub_ledger_dir,
        )

        # State
        self.current_session_date: Optional[str] = None
        self.session_open_0915: Optional[float] = None
        self.bar_1520_close: Optional[float] = None
        self.signal_result: Optional[OvernightSignalResult] = None
        self.macro_frozen: bool = False

    def on_market_pulse(self, pulse_id: str, snapshot: StrategyMarketSnapshotV1) -> Optional[Dict[str, Any]]:
        # 1. Central feed health check
        if not snapshot.central_feed_valid(self.max_quote_age_ms):
            self.record_checkpoint(
                pulse_id=pulse_id,
                checkpoint_name="SESSION_AUTHORITY",
                status="FAIL",
                root_cause="FEED_DEGRADED_OR_STALE",
                designed=f"feed_health==HEALTHY and central_age<={self.max_quote_age_ms}",
                observed=f"health={snapshot.feed_health}, age={snapshot.age_ms}",
            )
            return None

        t = snapshot.source_timestamp_ist.time()
        session_dt = snapshot.source_timestamp_ist.date()
        session_date_str = session_dt.isoformat()

        # Reset session-scoped state on date transition across multi-session replays or live days
        if self.current_session_date != session_date_str:
            self.current_session_date = session_date_str
            self.session_open_0915 = None
            self.bar_1520_close = None
            self.signal_result = None
            self.macro_frozen = False

        # Step A: Check if any previous session is in OVERNIGHT_PENDING and finalize using 09:15 open if available
        finalization_result: Optional[Dict[str, Any]] = None
        if snapshot.last_completed_1m_bar and snapshot.last_completed_1m_bar.timestamp_ist.time() == dtime(9, 15):
            self.session_open_0915 = snapshot.last_completed_1m_bar.open
            self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="NEXT_SESSION_0915_OPEN", status="PASS")

            # Reconstruct any pending overnight sessions across the entire ledger
            ledger_path = self.ledger_manager._get_ledger_path(self.sub_ledger)
            if os.path.exists(ledger_path):
                pending_entries: Dict[str, Dict[str, Any]] = {}
                with open(ledger_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line.strip())
                        s_key = f"{entry['sub_ledger']}|{entry['candidate_id']}|{entry['session_date']}"
                        if entry.get("lifecycle_state") == ObserverLifecycleState.OVERNIGHT_PENDING.value:
                            pending_entries[s_key] = entry
                        elif entry.get("lifecycle_state") in [
                            ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED.value,
                            ObserverLifecycleState.OBSERVATION_FINALIZED.value,
                            ObserverLifecycleState.OBSERVATION_INVALID.value,
                        ] and s_key in pending_entries:
                            del pending_entries[s_key]

                # Finalize all pending sessions
                for s_key, last_entry in pending_entries.items():
                    prev_session_date = last_entry["session_date"]
                    prev_decision_ts = last_entry["decision_timestamp_ist"]
                    prev_macro = last_entry["macro_uptrend"]
                    prev_gain = last_entry["day_gain_pct"]
                    prev_is_mon = last_entry["is_monday"]
                    prev_qual = last_entry["qualified"]
                    prev_quote_src = last_entry.get("quote_source_timestamp_ist")
                    prev_quote_rec = last_entry.get("quote_receipt_timestamp_ist")
                    prev_bid = last_entry.get("best_bid")
                    prev_ask = last_entry.get("best_ask")

                    # 1. Advance to NEXT_SESSION_OPEN_CAPTURED
                    self.ledger_manager.append_observation(
                        sub_ledger=self.sub_ledger,
                        target_state=ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED,
                        candidate_spec=self.candidate_spec,
                        schedule_sha256=self.candidate_digest,
                        session_date=prev_session_date,
                        decision_ts=prev_decision_ts,
                        macro_uptrend=prev_macro,
                        day_gain_pct=prev_gain,
                        is_monday=prev_is_mon,
                        qualified=prev_qual,
                        quote_source_ts=prev_quote_src,
                        quote_receipt_ts=prev_quote_rec,
                        best_bid=prev_bid,
                        best_ask=prev_ask,
                        next_session_open=self.session_open_0915,
                    )
                    # 2. Advance to OBSERVATION_FINALIZED
                    rec_final = self.ledger_manager.append_observation(
                        sub_ledger=self.sub_ledger,
                        target_state=ObserverLifecycleState.OBSERVATION_FINALIZED,
                        candidate_spec=self.candidate_spec,
                        schedule_sha256=self.candidate_digest,
                        session_date=prev_session_date,
                        decision_ts=prev_decision_ts,
                        macro_uptrend=prev_macro,
                        day_gain_pct=prev_gain,
                        is_monday=prev_is_mon,
                        qualified=prev_qual,
                        quote_source_ts=prev_quote_src,
                        quote_receipt_ts=prev_quote_rec,
                        best_bid=prev_bid,
                        best_ask=prev_ask,
                        next_session_open=self.session_open_0915,
                    )
                    self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="OBSERVATION_FINALIZED", status="PASS")
                    finalization_result = {
                        "candidate_id": self.candidate_id,
                        "schedule_sha256": self.candidate_digest,
                        "action": "FINALIZED",
                        "sequence_number": rec_final.sequence_number,
                        "record_hash": rec_final.record_hash,
                        "net_pnl_pts": rec_final.net_pnl_pts,
                        "read_only": True,
                        "broker_write_authority": False,
                        "order_authority": False,
                        "orders_placed": 0,
                    }

        # Step B: Pre-session / Morning Macro Freeze for current session
        if not self.macro_frozen:
            macro_uptrend = self.prev_daily_close > self.prev_sma200
            session_key = f"{self.sub_ledger}|{self.candidate_id}|{session_date_str}"
            curr_state = self.ledger_manager.get_persisted_session_state(self.sub_ledger, session_key)
            if curr_state == ObserverLifecycleState.PRE_SESSION:
                self.ledger_manager.append_observation(
                    sub_ledger=self.sub_ledger,
                    target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
                    candidate_spec=self.candidate_spec,
                    schedule_sha256=self.candidate_digest,
                    session_date=session_date_str,
                    decision_ts="09:00:00",
                    macro_uptrend=macro_uptrend,
                    day_gain_pct=0.0,
                    is_monday=(session_dt.weekday() == 0),
                    qualified=False,
                )
            self.macro_frozen = True
            self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="SESSION_AUTHORITY", status="PASS")

        if finalization_result is not None:
            return finalization_result


        # Step C: Handle 15:20 completed bar for signal evaluation
        if snapshot.last_completed_1m_bar and snapshot.last_completed_1m_bar.timestamp_ist.time() == dtime(15, 20):
            self.bar_1520_close = snapshot.last_completed_1m_bar.close
            if self.session_open_0915:
                sig = evaluate_overnight_signal(
                    session_date=session_date_str,
                    dow=session_dt.strftime("%A"),
                    prev_close=self.prev_daily_close,
                    prev_sma200=self.prev_sma200,
                    day_open=self.session_open_0915,
                    price_1520=self.bar_1520_close,
                )
                self.signal_result = sig
                is_qual = sig.s1_qualified if self.candidate_id == CANDIDATE_S1_ID else sig.s4_qualified

                # Append SIGNAL_SEALED_1520
                self.ledger_manager.append_observation(
                    sub_ledger=self.sub_ledger,
                    target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
                    candidate_spec=self.candidate_spec,
                    schedule_sha256=self.candidate_digest,
                    session_date=session_date_str,
                    decision_ts="15:20:00",
                    macro_uptrend=sig.is_uptrend,
                    day_gain_pct=sig.day_gain_pct,
                    is_monday=(session_dt.weekday() == 0),
                    qualified=is_qual,
                )
                # Append QUALIFIED or NOT_QUALIFIED
                target_state = ObserverLifecycleState.QUALIFIED if is_qual else ObserverLifecycleState.NOT_QUALIFIED
                self.ledger_manager.append_observation(
                    sub_ledger=self.sub_ledger,
                    target_state=target_state,
                    candidate_spec=self.candidate_spec,
                    schedule_sha256=self.candidate_digest,
                    session_date=session_date_str,
                    decision_ts="15:20:00",
                    macro_uptrend=sig.is_uptrend,
                    day_gain_pct=sig.day_gain_pct,
                    is_monday=(session_dt.weekday() == 0),
                    qualified=is_qual,
                )
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="SIGNAL_EVALUATED",
                    status="PASS",
                    observed=f"qualified={is_qual}",
                )

        # Step D: Handle 15:21 Depth Arrival Quote
        is_qual = False
        if self.signal_result:
            is_qual = self.signal_result.s1_qualified if self.candidate_id == CANDIDATE_S1_ID else self.signal_result.s4_qualified

        if (
            is_qual
            and snapshot.l1_depth
            and snapshot.l1_depth.is_valid()
            and dtime(15, 20) < t <= dtime(15, 22)
        ):
            quote_src = snapshot.source_timestamp_ist.isoformat()
            quote_rec = snapshot.receipt_timestamp_ist.isoformat()
            freshness_ms = calculate_internal_quote_freshness(quote_src, quote_rec)

            if freshness_ms is None or freshness_ms > self.max_quote_age_ms:
                self.record_checkpoint(
                    pulse_id=pulse_id,
                    checkpoint_name="ARRIVAL_1521_DEPTH_VALID",
                    status="FAIL",
                    root_cause="STALE_ARRIVAL_QUOTE",
                    designed=f"freshness_ms<={self.max_quote_age_ms}",
                    observed=str(freshness_ms),
                )
                return None

            self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="ARRIVAL_1521_DEPTH_VALID", status="PASS")

            # Append ARRIVAL_CAPTURED_1521
            rec_arrival = self.ledger_manager.append_observation(
                sub_ledger=self.sub_ledger,
                target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
                candidate_spec=self.candidate_spec,
                schedule_sha256=self.candidate_digest,
                session_date=session_date_str,
                decision_ts="15:20:00",
                macro_uptrend=self.signal_result.is_uptrend,
                day_gain_pct=self.signal_result.day_gain_pct,
                is_monday=(session_dt.weekday() == 0),
                qualified=is_qual,
                quote_source_ts=quote_src,
                quote_receipt_ts=quote_rec,
                best_bid=snapshot.l1_depth.bid_price,
                best_ask=snapshot.l1_depth.ask_price,
                validation_notes="Governed Pulse Strategy Shadow Adapter Capture",
            )

            # Append OVERNIGHT_PENDING
            rec_pending = self.ledger_manager.append_observation(
                sub_ledger=self.sub_ledger,
                target_state=ObserverLifecycleState.OVERNIGHT_PENDING,
                candidate_spec=self.candidate_spec,
                schedule_sha256=self.candidate_digest,
                session_date=session_date_str,
                decision_ts="15:20:00",
                macro_uptrend=self.signal_result.is_uptrend,
                day_gain_pct=self.signal_result.day_gain_pct,
                is_monday=(session_dt.weekday() == 0),
                qualified=is_qual,
                quote_source_ts=quote_src,
                quote_receipt_ts=quote_rec,
                best_bid=snapshot.l1_depth.bid_price,
                best_ask=snapshot.l1_depth.ask_price,
            )

            self.record_checkpoint(pulse_id=pulse_id, checkpoint_name="OVERNIGHT_STATE_COMMITTED", status="PASS")
            return {
                "candidate_id": self.candidate_id,
                "schedule_sha256": self.candidate_digest,
                "action": "COMMITTED_ARRIVAL",
                "sequence_number": rec_pending.sequence_number,
                "record_hash": rec_pending.record_hash,
                "lifecycle_state": rec_pending.lifecycle_state,
                "read_only": True,
                "broker_write_authority": False,
                "order_authority": False,
                "orders_placed": 0,
            }

        return None


# ---------------------------------------------------------------------------
# Governed Strategy Shadow Adapter Registry & Snapshot Builder
# ---------------------------------------------------------------------------

class StrategyMarketSnapshotBuilder:
    """
    Transforms canonical runtime cycle data (pulse, feed_health_truth, market_snapshot)
    into normalized StrategyMarketSnapshotV1 instances without private feed derivation.
    """

    @staticmethod
    def build_snapshots(
        pulse_id: str,
        timestamp_ist: datetime,
        market_snapshot: Optional[Mapping[str, Any]],
        feed_health_truth: Optional[Mapping[str, Any]],
    ) -> List[StrategyMarketSnapshotV1]:
        snapshots: List[StrategyMarketSnapshotV1] = []
        if not isinstance(feed_health_truth, Mapping):
            return snapshots

        symbols_data = feed_health_truth.get("symbols", [])
        if not isinstance(symbols_data, list):
            return snapshots

        context = feed_health_truth.get("context", {}) if isinstance(feed_health_truth.get("context"), Mapping) else {}
        session_id = str(context.get("session_id") or "UNKNOWN_SESSION")
        feed_ok = bool(feed_health_truth.get("feed_ok", False))
        websocket_ok = bool(feed_health_truth.get("websocket_ok", False))
        feed_health_status = "HEALTHY" if (feed_ok and websocket_ok) else "DEGRADED"

        # Parse session health if present
        session_health_raw = str(context.get("session_health") or context.get("session_state") or "NORMAL").upper()
        session_health_status: Literal["NORMAL", "HALTED", "CIRCUIT_BREAKER", "POST_CLOSE"] = "NORMAL"
        if session_health_raw in ("HALTED", "CIRCUIT_BREAKER", "POST_CLOSE"):
            session_health_status = session_health_raw

        for sym in symbols_data:
            if not isinstance(sym, Mapping):
                continue
            symbol_name = str(sym.get("symbol") or "")
            instrument_type = str(sym.get("instrument_type") or "").upper()
            segment = str(sym.get("segment") or "").upper()
            token = str(sym.get("instrument_token") or "")

            # Map instrument class using authoritative metadata only; never guess from symbol substrings
            inst_class: Optional[Literal["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTION"]] = None
            if instrument_type in ("FUT", "FUTURES") or segment in ("NFO-FUT", "NSE-FUT"):
                inst_class = "INDEX_FUTURES"
            elif instrument_type in ("OPT", "OPTION", "CE", "PE") or segment in ("NFO-OPT", "NSE-OPT"):
                inst_class = "INDEX_OPTION"
            elif instrument_type in ("INDEX", "SPOT") or segment in ("INDICES", "NSE-INDICES") or symbol_name in ("NIFTY 50", "NIFTY"):
                inst_class = "INDEX_SPOT"
            else:
                continue  # Skip unclassified instrument fail-closed without guessing

            # Derive depth (strictly non-synthetic quantities, math.isfinite check)
            depth = None
            raw_bid = sym.get("best_bid") if sym.get("best_bid") is not None else sym.get("bid")
            raw_ask = sym.get("best_ask") if sym.get("best_ask") is not None else sym.get("ask")
            raw_bid_q = sym.get("bid_quantity") if sym.get("bid_quantity") is not None else sym.get("bid_qty")
            raw_ask_q = sym.get("ask_quantity") if sym.get("ask_quantity") is not None else sym.get("ask_qty")

            bid = float(raw_bid) if raw_bid is not None else 0.0
            ask = float(raw_ask) if raw_ask is not None else 0.0
            bid_q = int(raw_bid_q) if raw_bid_q is not None else None
            ask_q = int(raw_ask_q) if raw_ask_q is not None else None

            if bid > 0.0 and ask > 0.0 and bid_q is not None and ask_q is not None:
                d = Level1Depth(bid_price=bid, bid_qty=bid_q, ask_price=ask, ask_qty=ask_q)
                if d.is_valid():
                    depth = d

            # Derive completed bar: require authoritative bar timestamp, never synthesize from pulse time
            bar = None
            if sym.get("bar_close") is not None and sym.get("bar_open") is not None:
                raw_bar_ts = (
                    sym.get("bar_timestamp_ist")
                    or sym.get("bar_timestamp")
                )
                bar_ts = None
                if isinstance(raw_bar_ts, datetime):
                    bar_ts = raw_bar_ts
                elif isinstance(raw_bar_ts, str):
                    try:
                        bar_ts = datetime.fromisoformat(raw_bar_ts)
                    except Exception:
                        bar_ts = None
                elif sym.get("bar_timestamp_epoch") is not None:
                    try:
                        bar_ts = datetime.fromtimestamp(float(sym["bar_timestamp_epoch"]), tz=IST_TZ)
                    except Exception:
                        bar_ts = None

                # Fallback to pulse interval end only if specifically provided as bar boundary
                if bar_ts is None and sym.get("interval_end_epoch") is not None:
                    try:
                        bar_ts = datetime.fromtimestamp(float(sym["interval_end_epoch"]), tz=IST_TZ)
                    except Exception:
                        bar_ts = None

                # If no authoritative bar timestamp exists, do not construct a Bar1M
                if bar_ts is not None:
                    bar = Bar1M(
                        timestamp_ist=bar_ts,
                        open=float(sym["bar_open"]),
                        high=float(sym.get("bar_high", sym["bar_close"])),
                        low=float(sym.get("bar_low", sym["bar_open"])),
                        close=float(sym["bar_close"]),
                        volume=int(sym.get("bar_volume", 0)),
                    )

            # Age computation: fail-closed if missing / null (do not default to 0.0)
            raw_age_sec = sym.get("option_last_tick_age_sec")
            if raw_age_sec is None:
                raw_age_sec = sym.get("last_tick_age_sec")
            if raw_age_sec is None:
                raw_age_sec = sym.get("age_sec")

            age_ms = float(raw_age_sec) * 1000.0 if raw_age_sec is not None else None

            # Source timestamp vs Receipt timestamp (never synthesize source timestamp from receipt time)
            source_ts = None
            raw_src_ts = sym.get("exchange_timestamp") or sym.get("source_timestamp") or sym.get("last_trade_time")
            if isinstance(raw_src_ts, datetime):
                source_ts = raw_src_ts
            elif isinstance(raw_src_ts, str):
                try:
                    source_ts = datetime.fromisoformat(raw_src_ts)
                except Exception:
                    source_ts = None
            elif sym.get("source_timestamp_epoch") is not None or sym.get("ts_epoch") is not None:
                try:
                    epoch_val = float(sym.get("source_timestamp_epoch") or sym.get("ts_epoch"))
                    source_ts = datetime.fromtimestamp(epoch_val, tz=IST_TZ)
                except Exception:
                    source_ts = None

            # Structured Option Metadata
            strike_val = float(sym["strike_price"]) if sym.get("strike_price") is not None else None
            opt_type_raw = str(sym.get("option_type") or "").upper()
            opt_type_val: Optional[Literal["CE", "PE"]] = "CE" if opt_type_raw == "CE" else ("PE" if opt_type_raw == "PE" else None)

            snap = StrategyMarketSnapshotV1(
                session_id=session_id,
                instrument_key=token or symbol_name,
                trading_symbol=symbol_name,
                instrument_class=inst_class,
                source_timestamp_ist=source_ts,
                receipt_timestamp_ist=timestamp_ist,
                age_ms=age_ms,
                feed_health=feed_health_status,
                session_health=session_health_status,
                l1_depth=depth,
                last_completed_1m_bar=bar,
                authoritative_contract_key=str(sym.get("selected_futures_contract_key") or sym.get("contract_key") or symbol_name),
                underlying_key=str(sym.get("underlying") or "NIFTY") if inst_class != "INDEX_SPOT" else None,
                expiry_date=str(sym.get("expiry")) if sym.get("expiry") is not None else None,
                strike_price=strike_val,
                option_type=opt_type_val,
                lot_size=int(sym["lot_size"]) if sym.get("lot_size") is not None else None,
            )
            snapshots.append(snap)

        return snapshots


class StrategyShadowAdapterRegistry:
    """
    Governed registry for read-only paper shadow observers.
    Instantiated once per session; dispatches canonical cycle_pulse events.
    Strictly isolated from TradeBuilder, OrderRouter, RiskGate, and Broker Adapters.
    """

    def __init__(
        self,
        session_id: str,
        source_sha: str,
        evidence_root: Path | str,
        opening_drive_prev_contract_key: Optional[str] = None,
        opening_drive_prev_close_1529: Optional[float] = None,
        opening_drive_target_expiry: Optional[str] = None,
        overnight_prev_daily_close: Optional[float] = None,
        overnight_prev_sma200: Optional[float] = None,
    ):
        self.session_id = session_id
        self.source_sha = source_sha
        self.evidence_root = Path(evidence_root)
        self.read_only: bool = True
        self.broker_write_authority: bool = False
        self.order_authority: bool = False
        self.orders_placed: int = 0
        self.orders_modified: int = 0
        self.orders_cancelled: int = 0

        # Directories
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.checkpoints_path = self.evidence_root / "checkpoints.jsonl"
        self.registry_manifest_path = self.evidence_root / "registry.json"

        # Initialize adapters with strict fingerprint verification
        self.adapters: Dict[str, StrategyShadowAdapter] = {}
        self.disabled_strategies: Dict[str, str] = {}

        # 1. Opening Drive
        if opening_drive_prev_contract_key and opening_drive_prev_close_1529 is not None:
            self.adapters[OPENING_DRIVE_ID] = IntradayOpeningDriveShadowAdapter(
                prev_futures_contract_key=opening_drive_prev_contract_key,
                prev_close_1529=opening_drive_prev_close_1529,
                target_expiry=opening_drive_target_expiry,
            )
        else:
            reason = "MISSING_T_MINUS_1_FUTURES_PREREQUISITES"
            self.disabled_strategies[OPENING_DRIVE_ID] = f"DISABLED_FAIL_CLOSED: {reason}"
            logger.warning("Strategy %s disabled fail-closed: %s", OPENING_DRIVE_ID, reason)

        # 2. S1 Overnight & 3. S4 Overnight
        if overnight_prev_daily_close is not None and overnight_prev_sma200 is not None:
            s1_dir = str(self.evidence_root / CANDIDATE_S1_ID)
            self.adapters[CANDIDATE_S1_ID] = OvernightDriftShadowAdapter(
                candidate_id=CANDIDATE_S1_ID,
                schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
                prev_daily_close=overnight_prev_daily_close,
                prev_sma200=overnight_prev_sma200,
                sub_ledger_dir=s1_dir,
            )

            s4_dir = str(self.evidence_root / CANDIDATE_S4_ID)
            self.adapters[CANDIDATE_S4_ID] = OvernightDriftShadowAdapter(
                candidate_id=CANDIDATE_S4_ID,
                schedule_sha256=CANDIDATE_S4_SCHEDULE_SHA256,
                prev_daily_close=overnight_prev_daily_close,
                prev_sma200=overnight_prev_sma200,
                sub_ledger_dir=s4_dir,
            )
        else:
            reason = "MISSING_T_MINUS_1_OVERNIGHT_PREREQUISITES"
            self.disabled_strategies[CANDIDATE_S1_ID] = f"DISABLED_FAIL_CLOSED: {reason}"
            self.disabled_strategies[CANDIDATE_S4_ID] = f"DISABLED_FAIL_CLOSED: {reason}"
            logger.warning("Overnight strategies disabled fail-closed: %s", reason)

        self._write_registry_manifest()

    def _write_registry_manifest(self) -> None:
        manifest = {
            "session_id": self.session_id,
            "source_sha": self.source_sha,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
            "shadow_strategy_ids": list(self.adapters.keys()),
            "disabled_strategies": dict(self.disabled_strategies),
            "adapters": {
                cid: {
                    "candidate_digest": adapter.candidate_digest,
                    "max_quote_age_ms": adapter.max_quote_age_ms,
                    "mode": "RESEARCH_SHADOW",
                }
                for cid, adapter in self.adapters.items()
            },
        }
        with open(self.registry_manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    def on_pulse(
        self,
        pulse: Any,
        market_snapshot: Optional[Mapping[str, Any]],
        feed_health_truth: Optional[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Processes incoming cycle pulse, normalizes snapshots, and dispatches to registered shadow observers."""
        pulse_id = getattr(pulse, "pulse_id", str(pulse))
        t_epoch = getattr(pulse, "timestamp_epoch", datetime.now(timezone.utc).timestamp())
        timestamp_ist = datetime.fromtimestamp(t_epoch, tz=IST_TZ)

        snapshots = StrategyMarketSnapshotBuilder.build_snapshots(
            pulse_id=pulse_id,
            timestamp_ist=timestamp_ist,
            market_snapshot=market_snapshot,
            feed_health_truth=feed_health_truth,
        )

        results: List[Dict[str, Any]] = []
        for snap in snapshots:
            for strat_id, adapter in self.adapters.items():
                res = adapter.on_market_pulse(pulse_id=pulse_id, snapshot=snap)
                if res:
                    results.append(res)
                    # Persist observation under strategy subdirectory
                    strat_dir = self.evidence_root / strat_id
                    strat_dir.mkdir(parents=True, exist_ok=True)
                    with (strat_dir / "observations.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps(res, sort_keys=True) + "\n")

        # Flush telemetry checkpoints to evidence
        self._flush_checkpoints()
        return results

    def _flush_checkpoints(self) -> None:
        with open(self.checkpoints_path, "a", encoding="utf-8") as f:
            for strat_id, adapter in self.adapters.items():
                while adapter.telemetry_history:
                    cp = adapter.telemetry_history.pop(0)
                    f.write(
                        json.dumps(
                            {
                                "session_id": self.session_id,
                                "source_sha": self.source_sha,
                                "pulse_id": cp.pulse_id,
                                "candidate_id": cp.candidate_id,
                                "checkpoint_name": cp.checkpoint_name,
                                "status": cp.status,
                                "root_cause": cp.root_cause,
                                "designed": cp.designed_threshold,
                                "observed": cp.observed_value,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )

    def on_session_shutdown(self) -> Dict[str, Any]:
        """Called upon runtime shutdown to seal evidence and report cross-session pending states."""
        try:
            self._flush_checkpoints()
            report = {
                "session_id": self.session_id,
                "source_sha": self.source_sha,
                "shutdown_at": datetime.now(timezone.utc).isoformat(),
                "read_only": True,
                "broker_write_authority": False,
                "order_authority": False,
                "orders_placed": 0,
                "strategy_statuses": {},
                "disabled_strategies": dict(self.disabled_strategies),
            }
            for strat_id, disabled_reason in self.disabled_strategies.items():
                report["strategy_statuses"][strat_id] = disabled_reason

            for strat_id, adapter in self.adapters.items():
                if isinstance(adapter, OvernightDriftShadowAdapter):
                    ledger_path = adapter.ledger_manager._get_ledger_path(adapter.sub_ledger)
                    curr_state = ObserverLifecycleState.PRE_SESSION
                    if os.path.exists(ledger_path):
                        with open(ledger_path, "r") as f:
                            lines = [line.strip() for line in f if line.strip()]
                        if lines:
                            curr_state = ObserverLifecycleState(json.loads(lines[-1]).get("lifecycle_state", "PRE_SESSION"))
                    status = "EXPECTED_CROSS_SESSION_PENDING" if curr_state == ObserverLifecycleState.OVERNIGHT_PENDING else curr_state.value
                elif isinstance(adapter, IntradayOpeningDriveShadowAdapter):
                    status = "FINALIZED" if adapter.observation_finalized else "NO_OBSERVATION"
                else:
                    status = "COMPLETED"
                report["strategy_statuses"][strat_id] = status

            with (self.evidence_root / "shutdown_report.json").open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, sort_keys=True)
            return report
        except Exception as exc:
            seal_fail_path = self.evidence_root / "STRATEGY_SHADOW_EVIDENCE_SEAL_FAIL"
            try:
                seal_fail_path.write_text(f"EXCEPTION: {type(exc).__name__}: {str(exc)}\n", encoding="utf-8")
            except Exception:
                pass
            raise


def load_canonical_t1_prerequisites(
    session_date: str,
    launch_plan: Optional[Mapping[str, Any]] = None,
    data_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Loads canonical T-1 market facts for strategy shadow adapters without requiring manual environment variables.
    Lookup precedence:
    1. Explicit environment overrides (if set by operator)
    2. launch_plan["t1_facts"] / launch_plan["preflight_facts"] / launch_plan metadata
    3. Persisted disk manifest in data_dir or runtime/sessions / runtime/preflight

    Returns a dict containing:
    - opening_drive_prev_contract_key: Optional[str]
    - opening_drive_prev_close_1529: Optional[float]
    - opening_drive_target_expiry: Optional[str]
    - overnight_prev_daily_close: Optional[float]
    - overnight_prev_sma200: Optional[float]
    """
    res: Dict[str, Any] = {
        "opening_drive_prev_contract_key": None,
        "opening_drive_prev_close_1529": None,
        "opening_drive_target_expiry": None,
        "overnight_prev_daily_close": None,
        "overnight_prev_sma200": None,
    }

    # 1. Inspect launch_plan
    if isinstance(launch_plan, Mapping):
        facts = (
            launch_plan.get("t1_facts")
            or launch_plan.get("preflight_facts")
            or launch_plan.get("strategy_prerequisites")
            or {}
        )
        if isinstance(facts, Mapping):
            if facts.get("opening_drive_prev_contract_key"):
                res["opening_drive_prev_contract_key"] = str(facts["opening_drive_prev_contract_key"])
            elif facts.get("prev_futures_contract_key"):
                res["opening_drive_prev_contract_key"] = str(facts["prev_futures_contract_key"])

            if facts.get("opening_drive_prev_close_1529") is not None:
                res["opening_drive_prev_close_1529"] = float(facts["opening_drive_prev_close_1529"])
            elif facts.get("prev_close_1529") is not None:
                res["opening_drive_prev_close_1529"] = float(facts["prev_close_1529"])

            if facts.get("opening_drive_target_expiry"):
                res["opening_drive_target_expiry"] = str(facts["opening_drive_target_expiry"])
            elif facts.get("target_expiry"):
                res["opening_drive_target_expiry"] = str(facts["target_expiry"])

            if facts.get("overnight_prev_daily_close") is not None:
                res["overnight_prev_daily_close"] = float(facts["overnight_prev_daily_close"])
            elif facts.get("prev_daily_close") is not None:
                res["overnight_prev_daily_close"] = float(facts["prev_daily_close"])

            if facts.get("overnight_prev_sma200") is not None:
                res["overnight_prev_sma200"] = float(facts["overnight_prev_sma200"])
            elif facts.get("prev_sma200") is not None:
                res["overnight_prev_sma200"] = float(facts["prev_sma200"])

        # Also check top-level keys in launch_plan
        if res["opening_drive_prev_contract_key"] is None and launch_plan.get("selected_futures_contract_key"):
            res["opening_drive_prev_contract_key"] = str(launch_plan["selected_futures_contract_key"])
        if res["opening_drive_target_expiry"] is None and launch_plan.get("target_expiry"):
            res["opening_drive_target_expiry"] = str(launch_plan["target_expiry"])

    # 2. Inspect persisted disk manifest if still missing
    search_dirs: List[Path] = []
    if data_dir is not None:
        search_dirs.append(Path(data_dir))
    search_dirs.extend([
        Path("runtime/preflight"),
        Path("runtime/sessions"),
        Path("runtime/truth"),
    ])

    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue
        # Check files matching session_date or t1_facts
        candidate_files = [
            s_dir / f"t1_prerequisites_{session_date}.json",
            s_dir / "t1_prerequisites.json",
            s_dir / f"preflight_{session_date}.json",
        ]
        for c_file in candidate_files:
            if c_file.is_file():
                try:
                    with c_file.open("r", encoding="utf-8") as f:
                        disk_facts = json.load(f)
                    if isinstance(disk_facts, Mapping):
                        if res["opening_drive_prev_contract_key"] is None and disk_facts.get("opening_drive_prev_contract_key"):
                            res["opening_drive_prev_contract_key"] = str(disk_facts["opening_drive_prev_contract_key"])
                        if res["opening_drive_prev_close_1529"] is None and disk_facts.get("opening_drive_prev_close_1529") is not None:
                            res["opening_drive_prev_close_1529"] = float(disk_facts["opening_drive_prev_close_1529"])
                        if res["opening_drive_target_expiry"] is None and disk_facts.get("opening_drive_target_expiry"):
                            res["opening_drive_target_expiry"] = str(disk_facts["opening_drive_target_expiry"])
                        if res["overnight_prev_daily_close"] is None and disk_facts.get("overnight_prev_daily_close") is not None:
                            res["overnight_prev_daily_close"] = float(disk_facts["overnight_prev_daily_close"])
                        if res["overnight_prev_sma200"] is None and disk_facts.get("overnight_prev_sma200") is not None:
                            res["overnight_prev_sma200"] = float(disk_facts["overnight_prev_sma200"])
                except Exception as exc:
                    logger.warning("Failed reading T-1 manifest from %s: %s", c_file, exc)

    # 3. Environment overrides take precedence if explicitly populated
    if os.environ.get("OPENING_DRIVE_PREV_FUTURES_KEY"):
        res["opening_drive_prev_contract_key"] = os.environ["OPENING_DRIVE_PREV_FUTURES_KEY"]
    if "OPENING_DRIVE_PREV_CLOSE_1529" in os.environ:
        try:
            res["opening_drive_prev_close_1529"] = float(os.environ["OPENING_DRIVE_PREV_CLOSE_1529"])
        except ValueError:
            pass
    if os.environ.get("OPENING_DRIVE_TARGET_EXPIRY"):
        res["opening_drive_target_expiry"] = os.environ["OPENING_DRIVE_TARGET_EXPIRY"]
    if "OVERNIGHT_PREV_DAILY_CLOSE" in os.environ:
        try:
            res["overnight_prev_daily_close"] = float(os.environ["OVERNIGHT_PREV_DAILY_CLOSE"])
        except ValueError:
            pass
    if "OVERNIGHT_PREV_SMA200" in os.environ:
        try:
            res["overnight_prev_sma200"] = float(os.environ["OVERNIGHT_PREV_SMA200"])
        except ValueError:
            pass

    return res
