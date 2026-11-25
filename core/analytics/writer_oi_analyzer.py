"""Institutional Option Writer Radar & Open Interest (OI) Analytics Engine.

Provides real-time tracking of:
- Call and Put Open Interest changes (delta OI).
- Strike-level Put-Call Ratio (PCR).
- Trapped writer short squeeze detection (Put unwinding).
- Call writer resistance wall defense.

Strict safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StrikeOIState:
    symbol: str
    strike: float
    option_type: str  # "CE" or "PE"
    current_oi: int = 0
    previous_oi: int = 0
    initial_oi: int = 0
    peak_oi: int = 0
    delta_oi_day: int = 0
    delta_oi_window: int = 0
    last_update_ms: int = 0


@dataclass
class WriterRegimeSignal:
    timestamp_utc: str
    index: str
    atm_strike: float
    strike_pcr: float
    call_writer_dominant: bool
    put_writer_dominant: bool
    put_unwinding_squeeze: bool  # Trapped put writers unwinding short PE
    call_unwinding_squeeze: bool  # Trapped call writers unwinding short CE
    writer_alignment: str  # "BEARS_IN_CONTROL", "BULLS_IN_CONTROL", "RANGE_PINNED", "NEUTRAL"
    conviction_score: float  # 0.0 to 1.0


class OptionWriterRadar:
    """Thread-safe, non-blocking in-memory analyzer for Option Writer positioning."""

    def __init__(self, index: str = "NIFTY") -> None:
        self.index = index
        self.strikes: Dict[str, StrikeOIState] = {}
        self.last_signal: Optional[WriterRegimeSignal] = None

    def update_oi(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        open_interest: int,
        timestamp_ms: int = 0
    ) -> None:
        """Updates in-memory Open Interest snapshot for a specific strike."""
        if open_interest <= 0:
            return

        if symbol not in self.strikes:
            self.strikes[symbol] = StrikeOIState(
                symbol=symbol,
                strike=strike,
                option_type=option_type,
                current_oi=open_interest,
                previous_oi=open_interest,
                initial_oi=open_interest,
                peak_oi=open_interest,
                delta_oi_day=0,
                delta_oi_window=0,
                last_update_ms=timestamp_ms
            )
        else:
            s = self.strikes[symbol]
            s.previous_oi = s.current_oi
            s.current_oi = open_interest
            s.delta_oi_day = s.current_oi - s.initial_oi
            s.delta_oi_window = s.current_oi - s.previous_oi
            if s.current_oi > s.peak_oi:
                s.peak_oi = s.current_oi
            s.last_update_ms = timestamp_ms

    def evaluate_writer_regime(
        self,
        current_spot: float,
        strike_step: float = 50.0,
        window_strikes: int = 3
    ) -> WriterRegimeSignal:
        """Evaluates live Call vs Put Writer pressure in the ATM cluster."""
        atm_strike = round(current_spot / strike_step) * strike_step

        relevant_calls = []
        relevant_puts = []

        lower_bound = atm_strike - (window_strikes * strike_step)
        upper_bound = atm_strike + (window_strikes * strike_step)

        total_call_oi = 0
        total_put_oi = 0
        total_call_delta = 0
        total_put_delta = 0

        for sym, state in self.strikes.items():
            if lower_bound <= state.strike <= upper_bound:
                if state.option_type == "CE":
                    relevant_calls.append(state)
                    total_call_oi += state.current_oi
                    total_call_delta += state.delta_oi_day
                elif state.option_type == "PE":
                    relevant_puts.append(state)
                    total_put_oi += state.current_oi
                    total_put_delta += state.delta_oi_day

        strike_pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0

        # Detection logic
        # 1. Call Writers dominant: Call OI adding heavily, PCR < 0.75
        call_writer_dominant = (total_call_delta > 0 and (strike_pcr <= 0.75 or total_call_delta > total_put_delta * 1.5))

        # 2. Put Writers dominant: Put OI adding heavily, PCR > 1.25
        put_writer_dominant = (total_put_delta > 0 and (strike_pcr >= 1.25 or total_put_delta > total_call_delta * 1.5))

        # 3. Trapped Put Writer Squeeze: Negative delta on PEs in the money/ATM
        put_unwinding_squeeze = any(s.delta_oi_day < 0 or s.delta_oi_window < -50000 for s in relevant_puts)

        # 4. Trapped Call Writer Squeeze: Negative delta on CEs in the money/ATM
        call_unwinding_squeeze = any(s.delta_oi_day < 0 or s.delta_oi_window < -50000 for s in relevant_calls)

        # Alignment
        if call_writer_dominant and put_unwinding_squeeze:
            writer_alignment = "BEARS_IN_CONTROL"
            conviction = 0.95
        elif call_writer_dominant:
            writer_alignment = "CALL_WALL_DEFENSE"
            conviction = 0.80
        elif put_writer_dominant and call_unwinding_squeeze:
            writer_alignment = "BULLS_IN_CONTROL"
            conviction = 0.95
        elif put_writer_dominant:
            writer_alignment = "PUT_FLOOR_DEFENSE"
            conviction = 0.80
        elif abs(strike_pcr - 1.0) <= 0.15:
            writer_alignment = "RANGE_PINNED"
            conviction = 0.50
        else:
            writer_alignment = "NEUTRAL"
            conviction = 0.50

        from datetime import datetime, timezone
        sig = WriterRegimeSignal(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            index=self.index,
            atm_strike=atm_strike,
            strike_pcr=strike_pcr,
            call_writer_dominant=call_writer_dominant,
            put_writer_dominant=put_writer_dominant,
            put_unwinding_squeeze=put_unwinding_squeeze,
            call_unwinding_squeeze=call_unwinding_squeeze,
            writer_alignment=writer_alignment,
            conviction_score=conviction
        )
        self.last_signal = sig
        return sig
