"""Sentinel Real-Time Forensic Decision Journal & Post-Market Digest Engine.

Zero Disk I/O In-Memory Logging & Shadow Barrier Path Evaluator.

Key Features & Invariants:
1. Producer Invariant: Zero disk I/O on streaming tick thread. Uses a thread-safe
   bounded queue (queue.Queue(maxsize=10000)). producer uses put_nowait(); if full,
   drops and increments dropped counter, never blocking low-latency streaming ingest.
2. Consumer Invariant: Dedicated background daemon worker `SentinelJournalWriter`
   periodically flushes batches to append-only JSONL files at
   `logs/sentinel_decision_journal_YYYYMMDD.jsonl`.
3. Slotted Dataclasses:
   - VetoRecord: Captures all suppressed signals (spread veto, wall veto, macro veto,
     frictional hurdle veto, low confidence suppression, etc.)
   - TradeExecutionRecord: Captures genuine BUY triggers with discrete lot sizing and execution price.
   - TradeExitAttributionRecord: Captures APM exits with granular reason attribution and PnL.
   - ShadowBarrierOutcomeRecord: Evaluates what would have happened if a vetoed setup was taken.
   - DailyForensicSummary: Session aggregate digest of capital saved, missed alpha, and exit efficiency.
4. ShadowBarrierPathEvaluator: Strictly steps forward tick-by-tick in memory starting
   strictly AFTER entry timestamp (zero lookahead). Tracks virtual TP and SL barriers
   to classify True Positive (Capital Saved vs bad trade) vs False Positive (Missed Alpha).
5. Non-negotiable Trading Safety: read_only=True, is_order_action=False, broker_api_called=False.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slotted Record Dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class VetoRecord:
    record_type: str = "VETO"
    record_id: str = ""
    timestamp_ms: int = 0
    wall_time_str: str = ""
    index_name: str = ""
    symbol: str = ""
    direction: str = ""  # "CE" or "PE"
    setup_reason: str = ""
    veto_reason: str = ""  # e.g., "SPREAD_EXPANDED", "ADVERSE_WALL", "NIFTY_FRICTIONAL_HURDLE", "LOW_CONFIDENCE", "MACRO_DIVERGENCE"
    spot_price: float = 0.0
    option_ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_pts: float = 0.0
    spread_ratio: float = 0.0
    nominal_target_pts: float = 0.0
    nominal_sl_pts: float = 0.0
    confidence_score: int = 0
    confidence_grade: str = ""
    sizing_tier: str = ""


@dataclass(slots=True, frozen=True)
class TradeExecutionRecord:
    record_type: str = "EXECUTION"
    record_id: str = ""
    position_id: str = ""
    timestamp_ms: int = 0
    wall_time_str: str = ""
    index_name: str = ""
    symbol: str = ""
    direction: str = ""
    setup_reason: str = ""
    spot_price: float = 0.0
    option_ltp: float = 0.0
    fill_price: float = 0.0
    fill_mode: str = ""
    spread_savings: float = 0.0
    target_pts: float = 0.0
    sl_pts: float = 0.0
    confidence_score: int = 0
    confidence_grade: str = ""
    lots: int = 0
    lot_size: int = 0
    total_quantity: int = 0
    sizing_tier: str = ""


@dataclass(slots=True, frozen=True)
class TradeExitAttributionRecord:
    record_type: str = "EXIT"
    record_id: str = ""
    position_id: str = ""
    timestamp_ms: int = 0
    wall_time_str: str = ""
    index_name: str = ""
    symbol: str = ""
    direction: str = ""
    entry_price_spot: float = 0.0
    exit_price_spot: float = 0.0
    entry_price_opt: float = 0.0
    exit_price_opt: float = 0.0
    opt_pnl_pts: float = 0.0
    spot_pnl_pts: float = 0.0
    exit_reason: str = ""
    holding_duration_seconds: float = 0.0
    max_spot_excursion: float = 0.0
    max_opt_excursion: float = 0.0
    target_1_hit: bool = False
    target_2_hit: bool = False
    half_booked: bool = False
    trail_locked: bool = False
    realized_pnl_inr: float = 0.0


@dataclass(slots=True)
class ShadowBarrierOutcomeRecord:
    record_type: str = "SHADOW_OUTCOME"
    record_id: str = ""
    veto_record_id: str = ""
    entry_timestamp_ms: int = 0
    entry_time_str: str = ""
    resolution_timestamp_ms: int = 0
    resolution_time_str: str = ""
    index_name: str = ""
    symbol: str = ""
    direction: str = ""
    veto_reason: str = ""
    entry_opt_ltp: float = 0.0
    target_barrier_opt: float = 0.0
    sl_barrier_opt: float = 0.0
    entry_spot: float = 0.0
    target_barrier_spot: float = 0.0
    sl_barrier_spot: float = 0.0
    outcome: str = "PENDING"  # "HIT_SL_FIRST", "HIT_TP_FIRST", "EXPIRED_EOD", "PENDING"
    classification: str = "PENDING"  # "TRUE_POSITIVE_SAVED_CAPITAL", "FALSE_POSITIVE_MISSED_ALPHA", "NEUTRAL_CHOP"
    simulated_pnl_pts: float = 0.0
    simulated_capital_saved_or_lost_inr: float = 0.0
    max_favorable_excursion_pts: float = 0.0
    max_adverse_excursion_pts: float = 0.0
    tick_count_evaluated: int = 0


@dataclass(slots=True)
class DailyForensicSummary:
    record_type: str = "DAILY_SUMMARY"
    session_date: str = ""
    total_vetoes: int = 0
    vetoes_by_reason: Dict[str, int] = field(default_factory=dict)
    total_executions: int = 0
    total_exits: int = 0
    resolved_shadow_barriers: int = 0
    pending_shadow_barriers: int = 0
    true_positive_capital_saved_count: int = 0
    false_positive_missed_alpha_count: int = 0
    neutral_chop_count: int = 0
    capital_saved_inr: float = 0.0
    missed_alpha_inr: float = 0.0
    net_veto_defense_benefit_inr: float = 0.0
    executed_total_pnl_inr: float = 0.0
    win_rate_executed_pct: float = 0.0
    exit_attribution_counts: Dict[str, int] = field(default_factory=dict)
    generation_time_str: str = ""


# ---------------------------------------------------------------------------
# Shadow Barrier Path Evaluator
# ---------------------------------------------------------------------------

class ShadowBarrierPathEvaluator:
    """In-memory forward path tracker evaluating vetoed setups tick-by-tick.

    Strict Invariants:
    1. Zero Lookahead: Only evaluates ticks where tick_timestamp_ms > entry_timestamp_ms.
    2. Conservative Intrabar Resolution: If both SL and TP are hit on the exact same tick,
       pessimistically treats SL as hit first.
    3. Classification:
       - HIT_SL_FIRST: TRUE_POSITIVE_SAVED_CAPITAL (the veto protected capital).
       - HIT_TP_FIRST: FALSE_POSITIVE_MISSED_ALPHA (the veto prevented a winning trade).
       - EXPIRED_EOD: NEUTRAL_CHOP (trade timed out with neither barrier reached).
    """

    def __init__(self, default_lot_size_nifty: int = 65, default_lot_size_other: int = 30):
        self._pending_barriers: Dict[str, ShadowBarrierOutcomeRecord] = {}
        self._completed_barriers: List[ShadowBarrierOutcomeRecord] = []
        self._lock = threading.Lock()
        self.default_lot_size_nifty = default_lot_size_nifty
        self.default_lot_size_other = default_lot_size_other

    def register_veto(self, veto: VetoRecord) -> Optional[ShadowBarrierOutcomeRecord]:
        """Registers a vetoed candidate for forward path tracking."""
        if veto.option_ltp <= 0 and veto.spot_price <= 0:
            return None

        # Build barrier targets in option premium space
        entry_opt = veto.option_ltp
        # If option LTP is valid, barriers are set in option points
        # Target = entry + target_pts * delta (approx 0.5 for ATM if not given)
        # Or if nominal_target_pts given:
        opt_target_pts = veto.nominal_target_pts if veto.nominal_target_pts > 0 else 15.0
        opt_sl_pts = veto.nominal_sl_pts if veto.nominal_sl_pts > 0 else 12.0

        target_opt = entry_opt + opt_target_pts
        sl_opt = max(0.5, entry_opt - opt_sl_pts)

        # Also store spot barriers
        is_ce = (veto.direction == "CE")
        target_spot = veto.spot_price + opt_target_pts if is_ce else veto.spot_price - opt_target_pts
        sl_spot = veto.spot_price - opt_sl_pts if is_ce else veto.spot_price + opt_sl_pts

        rec_id = f"SHADOW_{veto.record_id or int(time.time() * 1000)}"
        record = ShadowBarrierOutcomeRecord(
            record_id=rec_id,
            veto_record_id=veto.record_id,
            entry_timestamp_ms=veto.timestamp_ms,
            entry_time_str=veto.wall_time_str,
            index_name=veto.index_name,
            symbol=veto.symbol,
            direction=veto.direction,
            veto_reason=veto.veto_reason,
            entry_opt_ltp=entry_opt,
            target_barrier_opt=round(target_opt, 2),
            sl_barrier_opt=round(sl_opt, 2),
            entry_spot=veto.spot_price,
            target_barrier_spot=round(target_spot, 2),
            sl_barrier_spot=round(sl_spot, 2),
            outcome="PENDING",
            classification="PENDING",
            simulated_pnl_pts=0.0,
            simulated_capital_saved_or_lost_inr=0.0,
            max_favorable_excursion_pts=0.0,
            max_adverse_excursion_pts=0.0,
            tick_count_evaluated=0,
        )

        with self._lock:
            self._pending_barriers[rec_id] = record
        return record

    def on_tick(
        self,
        symbol: str,
        current_opt_ltp: float,
        timestamp_ms: int,
        wall_time_str: str = "",
        current_spot: float = 0.0,
    ) -> List[ShadowBarrierOutcomeRecord]:
        """Evaluates incoming option tick against all pending shadow barriers for this symbol."""
        if current_opt_ltp <= 0:
            return []

        resolved: List[ShadowBarrierOutcomeRecord] = []
        with self._lock:
            pending_keys = list(self._pending_barriers.keys())
            for key in pending_keys:
                rec = self._pending_barriers.get(key)
                if rec is None or rec.symbol != symbol:
                    continue

                # Strict zero lookahead invariant
                if timestamp_ms <= rec.entry_timestamp_ms:
                    continue

                rec.tick_count_evaluated += 1

                # Calculate excursions
                gain_pts = current_opt_ltp - rec.entry_opt_ltp
                if gain_pts > rec.max_favorable_excursion_pts:
                    rec.max_favorable_excursion_pts = round(gain_pts, 2)
                if (-gain_pts) > rec.max_adverse_excursion_pts:
                    rec.max_adverse_excursion_pts = round(-gain_pts, 2)

                lot_size = self.default_lot_size_nifty if "NIFTY" in rec.index_name and "BANK" not in rec.index_name else self.default_lot_size_other

                # Check SL barrier hit
                sl_hit = (current_opt_ltp <= rec.sl_barrier_opt)
                # Check TP barrier hit
                tp_hit = (current_opt_ltp >= rec.target_barrier_opt)

                if sl_hit and tp_hit:
                    # Conservative Intrabar Resolution contract: SL takes precedence
                    rec.outcome = "HIT_SL_FIRST"
                    rec.classification = "TRUE_POSITIVE_SAVED_CAPITAL"
                    rec.resolution_timestamp_ms = timestamp_ms
                    rec.resolution_time_str = wall_time_str
                    rec.simulated_pnl_pts = round(rec.sl_barrier_opt - rec.entry_opt_ltp, 2)
                    # Capital saved is the avoided loss (positive rupee value saved)
                    rec.simulated_capital_saved_or_lost_inr = round(abs(rec.simulated_pnl_pts) * lot_size, 2)
                    self._completed_barriers.append(rec)
                    del self._pending_barriers[key]
                    resolved.append(rec)
                elif sl_hit:
                    rec.outcome = "HIT_SL_FIRST"
                    rec.classification = "TRUE_POSITIVE_SAVED_CAPITAL"
                    rec.resolution_timestamp_ms = timestamp_ms
                    rec.resolution_time_str = wall_time_str
                    rec.simulated_pnl_pts = round(rec.sl_barrier_opt - rec.entry_opt_ltp, 2)
                    rec.simulated_capital_saved_or_lost_inr = round(abs(rec.simulated_pnl_pts) * lot_size, 2)
                    self._completed_barriers.append(rec)
                    del self._pending_barriers[key]
                    resolved.append(rec)
                elif tp_hit:
                    rec.outcome = "HIT_TP_FIRST"
                    rec.classification = "FALSE_POSITIVE_MISSED_ALPHA"
                    rec.resolution_timestamp_ms = timestamp_ms
                    rec.resolution_time_str = wall_time_str
                    rec.simulated_pnl_pts = round(rec.target_barrier_opt - rec.entry_opt_ltp, 2)
                    # Missed alpha is positive profit forgone
                    rec.simulated_capital_saved_or_lost_inr = round(rec.simulated_pnl_pts * lot_size, 2)
                    self._completed_barriers.append(rec)
                    del self._pending_barriers[key]
                    resolved.append(rec)

        return resolved

    def finalize_eod(self, current_time_str: str = "15:30:00", current_prices: Optional[Dict[str, float]] = None) -> List[ShadowBarrierOutcomeRecord]:
        """Finalizes any remaining pending barriers at end of market session."""
        prices = current_prices or {}
        resolved: List[ShadowBarrierOutcomeRecord] = []
        with self._lock:
            pending_keys = list(self._pending_barriers.keys())
            for key in pending_keys:
                rec = self._pending_barriers.pop(key)
                rec.outcome = "EXPIRED_EOD"
                rec.resolution_time_str = current_time_str
                last_price = prices.get(rec.symbol, rec.entry_opt_ltp)
                pnl = round(last_price - rec.entry_opt_ltp, 2)
                rec.simulated_pnl_pts = pnl
                lot_size = self.default_lot_size_nifty if "NIFTY" in rec.index_name and "BANK" not in rec.index_name else self.default_lot_size_other
                rec.simulated_capital_saved_or_lost_inr = round(pnl * lot_size, 2)
                if pnl < -1.0:
                    rec.classification = "TRUE_POSITIVE_SAVED_CAPITAL"
                elif pnl > 1.0:
                    rec.classification = "FALSE_POSITIVE_MISSED_ALPHA"
                else:
                    rec.classification = "NEUTRAL_CHOP"
                self._completed_barriers.append(rec)
                resolved.append(rec)
        return resolved

    def get_all_records(self) -> Tuple[List[ShadowBarrierOutcomeRecord], List[ShadowBarrierOutcomeRecord]]:
        with self._lock:
            return list(self._completed_barriers), list(self._pending_barriers.values())


# ---------------------------------------------------------------------------
# Background Async Daemon Writer
# ---------------------------------------------------------------------------

class SentinelJournalWriter(threading.Thread):
    """Dedicated background daemon thread consuming records from an in-memory queue
    and writing append-only JSONL files.
    """

    def __init__(
        self,
        record_queue: queue.Queue,
        logs_dir: Path,
        flush_interval_seconds: float = 0.5,
    ):
        super().__init__(name="SentinelJournalWriter", daemon=True)
        self.record_queue = record_queue
        self.logs_dir = Path(logs_dir)
        self.flush_interval_seconds = flush_interval_seconds
        self._running = True
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        batch: List[Dict[str, Any]] = []
        last_flush = time.time()

        while self._running or not self.record_queue.empty():
            try:
                # Wait for next item with short timeout
                item = self.record_queue.get(timeout=0.1)
                batch.append(item)
                self.record_queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error getting from journal queue: {e}")

            # Flush batch if buffer has items and either batch size >= 50 or time threshold passed
            now = time.time()
            if batch and (len(batch) >= 50 or (now - last_flush) >= self.flush_interval_seconds or not self._running):
                self._flush_batch(batch)
                batch.clear()
                last_flush = now

        # Final drain
        if batch:
            self._flush_batch(batch)
            batch.clear()

    def _flush_batch(self, batch: List[Dict[str, Any]]) -> None:
        if not batch:
            return
        today_str = datetime.now().strftime("%Y%m%d")
        filepath = self.logs_dir / f"sentinel_decision_journal_{today_str}.jsonl"
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                for record in batch:
                    f.write(json.dumps(record, default=str) + "\n")
                f.flush()
        except Exception as e:
            logger.error(f"Failed to flush journal batch to {filepath}: {e}")


# ---------------------------------------------------------------------------
# Primary Manager: SentinelRealtimeJournal
# ---------------------------------------------------------------------------

class SentinelRealtimeJournal:
    """Real-Time Forensic Decision Journal & Post-Market Digest Engine.

    Guarantees:
    - Zero lock contention / disk delay on calling stream thread.
    - Thread-safe put_nowait with overflow counter.
    - Automatic shadow barrier path evaluation.
    - Full telemetry and end-of-day summary compilation.
    """

    def __init__(
        self,
        logs_dir: Path = Path("logs"),
        queue_maxsize: int = 10000,
        enable_writer_thread: bool = True,
    ):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.queue: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self.dropped_records_count: int = 0
        self.evaluator = ShadowBarrierPathEvaluator()

        # In-memory history cache for dashboard & summary
        self.veto_history: List[VetoRecord] = []
        self.execution_history: List[TradeExecutionRecord] = []
        self.exit_history: List[TradeExitAttributionRecord] = []
        self._mem_lock = threading.Lock()

        # Background writer thread
        self.writer: Optional[SentinelJournalWriter] = None
        if enable_writer_thread:
            self.writer = SentinelJournalWriter(self.queue, self.logs_dir)
            self.writer.start()

        # Safety Invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False

    def close(self) -> None:
        """Stops the daemon writer thread cleanly and flushes remaining queue."""
        if self.writer is not None:
            self.writer.stop()
            self.writer.join(timeout=2.0)

    def _enqueue(self, record_dict: Dict[str, Any]) -> bool:
        """Enqueues record with zero disk I/O; drops if queue is full."""
        try:
            self.queue.put_nowait(record_dict)
            return True
        except queue.Full:
            self.dropped_records_count += 1
            logger.warning(f"Journal queue is full ({self.queue.maxsize}). Dropping record.")
            return False

    def record_veto(
        self,
        index_name: str,
        symbol: str,
        direction: str,
        setup_reason: str,
        veto_reason: str,
        spot_price: float,
        option_ltp: float,
        bid: float = 0.0,
        ask: float = 0.0,
        spread_pts: float = 0.0,
        spread_ratio: float = 0.0,
        nominal_target_pts: float = 15.0,
        nominal_sl_pts: float = 12.0,
        confidence_score: int = 0,
        confidence_grade: str = "",
        sizing_tier: str = "",
        timestamp_ms: Optional[int] = None,
        wall_time_str: Optional[str] = None,
    ) -> VetoRecord:
        """Non-blocking call to record a vetoed trade setup."""
        now_dt = datetime.now()
        ts_ms = timestamp_ms or int(now_dt.timestamp() * 1000)
        t_str = wall_time_str or now_dt.strftime("%H:%M:%S")
        rec_id = f"VETO_{index_name}_{now_dt.strftime('%H%M%S%f')}"

        record = VetoRecord(
            record_id=rec_id,
            timestamp_ms=ts_ms,
            wall_time_str=t_str,
            index_name=index_name,
            symbol=symbol,
            direction=direction,
            setup_reason=setup_reason,
            veto_reason=veto_reason,
            spot_price=spot_price,
            option_ltp=option_ltp,
            bid=bid,
            ask=ask,
            spread_pts=spread_pts,
            spread_ratio=spread_ratio,
            nominal_target_pts=nominal_target_pts,
            nominal_sl_pts=nominal_sl_pts,
            confidence_score=confidence_score,
            confidence_grade=confidence_grade,
            sizing_tier=sizing_tier,
        )

        with self._mem_lock:
            self.veto_history.append(record)

        # Register with Shadow Barrier Evaluator
        shadow_rec = self.evaluator.register_veto(record)
        if shadow_rec is not None:
            self._enqueue(asdict(shadow_rec))

        self._enqueue(asdict(record))
        return record

    def record_execution(
        self,
        position_id: str,
        index_name: str,
        symbol: str,
        direction: str,
        setup_reason: str,
        spot_price: float,
        option_ltp: float,
        fill_price: float,
        fill_mode: str = "MIDPOINT_PASSIVE",
        spread_savings: float = 0.0,
        target_pts: float = 15.0,
        sl_pts: float = 12.0,
        confidence_score: int = 0,
        confidence_grade: str = "",
        lots: int = 1,
        lot_size: int = 65,
        total_quantity: int = 65,
        sizing_tier: str = "FULL_SIZE",
        timestamp_ms: Optional[int] = None,
        wall_time_str: Optional[str] = None,
    ) -> TradeExecutionRecord:
        """Non-blocking call to record an executed trade entry."""
        now_dt = datetime.now()
        ts_ms = timestamp_ms or int(now_dt.timestamp() * 1000)
        t_str = wall_time_str or now_dt.strftime("%H:%M:%S")
        rec_id = f"EXEC_{position_id}_{ts_ms}"

        record = TradeExecutionRecord(
            record_id=rec_id,
            position_id=position_id,
            timestamp_ms=ts_ms,
            wall_time_str=t_str,
            index_name=index_name,
            symbol=symbol,
            direction=direction,
            setup_reason=setup_reason,
            spot_price=spot_price,
            option_ltp=option_ltp,
            fill_price=fill_price,
            fill_mode=fill_mode,
            spread_savings=spread_savings,
            target_pts=target_pts,
            sl_pts=sl_pts,
            confidence_score=confidence_score,
            confidence_grade=confidence_grade,
            lots=lots,
            lot_size=lot_size,
            total_quantity=total_quantity,
            sizing_tier=sizing_tier,
        )

        with self._mem_lock:
            self.execution_history.append(record)

        self._enqueue(asdict(record))
        return record

    def record_exit(
        self,
        position_id: str,
        index_name: str,
        symbol: str,
        direction: str,
        entry_price_spot: float,
        exit_price_spot: float,
        entry_price_opt: float,
        exit_price_opt: float,
        opt_pnl_pts: float,
        spot_pnl_pts: float,
        exit_reason: str,
        holding_duration_seconds: float = 0.0,
        max_spot_excursion: float = 0.0,
        max_opt_excursion: float = 0.0,
        target_1_hit: bool = False,
        target_2_hit: bool = False,
        half_booked: bool = False,
        trail_locked: bool = False,
        total_quantity: int = 65,
        timestamp_ms: Optional[int] = None,
        wall_time_str: Optional[str] = None,
    ) -> TradeExitAttributionRecord:
        """Non-blocking call to record an APM exit and attribution."""
        now_dt = datetime.now()
        ts_ms = timestamp_ms or int(now_dt.timestamp() * 1000)
        t_str = wall_time_str or now_dt.strftime("%H:%M:%S")
        rec_id = f"EXIT_{position_id}_{ts_ms}"

        realized_inr = round(opt_pnl_pts * total_quantity, 2)

        record = TradeExitAttributionRecord(
            record_id=rec_id,
            position_id=position_id,
            timestamp_ms=ts_ms,
            wall_time_str=t_str,
            index_name=index_name,
            symbol=symbol,
            direction=direction,
            entry_price_spot=entry_price_spot,
            exit_price_spot=exit_price_spot,
            entry_price_opt=entry_price_opt,
            exit_price_opt=exit_price_opt,
            opt_pnl_pts=opt_pnl_pts,
            spot_pnl_pts=spot_pnl_pts,
            exit_reason=exit_reason,
            holding_duration_seconds=holding_duration_seconds,
            max_spot_excursion=max_spot_excursion,
            max_opt_excursion=max_opt_excursion,
            target_1_hit=target_1_hit,
            target_2_hit=target_2_hit,
            half_booked=half_booked,
            trail_locked=trail_locked,
            realized_pnl_inr=realized_inr,
        )

        with self._mem_lock:
            self.exit_history.append(record)

        self._enqueue(asdict(record))
        return record

    def on_option_tick(
        self,
        symbol: str,
        current_opt_ltp: float,
        timestamp_ms: int,
        wall_time_str: str = "",
        current_spot: float = 0.0,
    ) -> List[ShadowBarrierOutcomeRecord]:
        """Steps forward shadow barrier evaluation for option ticks."""
        resolved = self.evaluator.on_tick(
            symbol=symbol,
            current_opt_ltp=current_opt_ltp,
            timestamp_ms=timestamp_ms,
            wall_time_str=wall_time_str,
            current_spot=current_spot,
        )
        for r in resolved:
            self._enqueue(asdict(r))
        return resolved

    def generate_daily_summary(
        self,
        session_date_str: Optional[str] = None,
        current_prices: Optional[Dict[str, float]] = None,
    ) -> DailyForensicSummary:
        """Compiles end-of-day summary, finalizes pending shadow barriers at close,
        and writes DailyForensicSummary.
        """
        s_date = session_date_str or datetime.now().strftime("%Y-%m-%d")
        # Finalize any pending barriers
        finalized = self.evaluator.finalize_eod(current_prices=current_prices)
        for r in finalized:
            self._enqueue(asdict(r))

        completed_barriers, pending_barriers = self.evaluator.get_all_records()

        vetoes_by_reason: Dict[str, int] = {}
        for v in self.veto_history:
            vetoes_by_reason[v.veto_reason] = vetoes_by_reason.get(v.veto_reason, 0) + 1

        exits_by_reason: Dict[str, int] = {}
        exec_pnl = 0.0
        winning_exits = 0
        for e in self.exit_history:
            exits_by_reason[e.exit_reason] = exits_by_reason.get(e.exit_reason, 0) + 1
            exec_pnl += e.realized_pnl_inr
            if e.opt_pnl_pts > 0:
                winning_exits += 1

        tp_count = 0
        fp_count = 0
        neutral_count = 0
        capital_saved_inr = 0.0
        missed_alpha_inr = 0.0

        for b in completed_barriers:
            if b.classification == "TRUE_POSITIVE_SAVED_CAPITAL":
                tp_count += 1
                capital_saved_inr += b.simulated_capital_saved_or_lost_inr
            elif b.classification == "FALSE_POSITIVE_MISSED_ALPHA":
                fp_count += 1
                missed_alpha_inr += b.simulated_capital_saved_or_lost_inr
            else:
                neutral_count += 1

        net_defense_benefit = round(capital_saved_inr - missed_alpha_inr, 2)
        win_rate = (winning_exits / len(self.exit_history) * 100.0) if self.exit_history else 0.0

        summary = DailyForensicSummary(
            session_date=s_date,
            total_vetoes=len(self.veto_history),
            vetoes_by_reason=vetoes_by_reason,
            total_executions=len(self.execution_history),
            total_exits=len(self.exit_history),
            resolved_shadow_barriers=len(completed_barriers),
            pending_shadow_barriers=len(pending_barriers),
            true_positive_capital_saved_count=tp_count,
            false_positive_missed_alpha_count=fp_count,
            neutral_chop_count=neutral_count,
            capital_saved_inr=round(capital_saved_inr, 2),
            missed_alpha_inr=round(missed_alpha_inr, 2),
            net_veto_defense_benefit_inr=net_defense_benefit,
            executed_total_pnl_inr=round(exec_pnl, 2),
            win_rate_executed_pct=round(win_rate, 1),
            exit_attribution_counts=exits_by_reason,
            generation_time_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        self._enqueue(asdict(summary))
        return summary
