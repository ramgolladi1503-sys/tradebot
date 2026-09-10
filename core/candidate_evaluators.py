"""Deterministic Frozen Strategy Evaluators for C1 and C2.

Contracts:
- Candidate 1 (C1): ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE
  Window: 09:30:00 to 14:45:00 IST.
  Predicate: rolling_15m_return_bps > +50.0.
  Reason codes: C1_OUT_OF_WINDOW, C1_MEMORY_NOT_READY, C1_STALE_MEMORY, C1_IMPULSE_BELOW_THRESHOLD, C1_QUALIFIED.

- Candidate 2 (C2): ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT
  Signal bar: Exactly completed 15:12:00 IST bar.
  Predicate: day_trend_at_1512_bps >= +50.0.
  Reason codes: C2_PRE_SIGNAL, C2_MEMORY_NOT_READY, C2_1512_BAR_MISSING, C2_STALE_MEMORY, C2_TREND_BELOW_THRESHOLD, C2_QUALIFIED, C2_POST_SIGNAL_WINDOW.

Preserves:
  broker_write_authority = False
  order_authority = False
  paper_authorized = False
  live_authorized = False
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Mapping

from core.market_session_store import MarketMemorySnapshot
from core.observability.candidate_attribution import (
    CandidateEmptyClass,
    StrategyEvaluationAttribution,
)


class C1ReasonCode(str, enum.Enum):
    C1_OUT_OF_WINDOW = "C1_OUT_OF_WINDOW"
    C1_MEMORY_NOT_READY = "C1_MEMORY_NOT_READY"
    C1_STALE_MEMORY = "C1_STALE_MEMORY"
    C1_IMPULSE_BELOW_THRESHOLD = "C1_IMPULSE_BELOW_THRESHOLD"
    C1_QUALIFIED = "C1_QUALIFIED"


class C2ReasonCode(str, enum.Enum):
    C2_PRE_SIGNAL = "C2_PRE_SIGNAL"
    C2_MEMORY_NOT_READY = "C2_MEMORY_NOT_READY"
    C2_1512_BAR_MISSING = "C2_1512_BAR_MISSING"
    C2_STALE_MEMORY = "C2_STALE_MEMORY"
    C2_TREND_BELOW_THRESHOLD = "C2_TREND_BELOW_THRESHOLD"
    C2_QUALIFIED = "C2_QUALIFIED"
    C2_POST_SIGNAL_WINDOW = "C2_POST_SIGNAL_WINDOW"


@dataclass(frozen=True)
class CandidateEmission:
    """Canonical candidate emitted upon qualification."""

    candidate_id: str
    strategy_id: str
    symbol: str
    signal_timestamp: str
    entry_boundary: str
    exit_boundary: str
    stop_rule: str
    trace_id: str
    features: Mapping[str, float]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    is_order_action: bool = False  # is_order_action=false
    broker_write_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["features"] = dict(self.features)
        data["metadata"] = dict(self.metadata)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


@dataclass(frozen=True)
class EvaluatorResult:
    candidate_id: str
    strategy_id: str
    evaluation_timestamp: str
    trace_id: str
    memory_watermark: float
    input_value: float
    threshold: float
    operator: str
    window_state: str
    decision: str  # QUALIFIED | NO_SIGNAL | SKIPPED
    reason_code: str
    qualified: bool
    candidate: CandidateEmission | None = None
    attribution: StrategyEvaluationAttribution | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "evaluation_timestamp": self.evaluation_timestamp,
            "trace_id": self.trace_id,
            "memory_watermark": self.memory_watermark,
            "input_value": self.input_value,
            "threshold": self.threshold,
            "operator": self.operator,
            "window_state": self.window_state,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "qualified": self.qualified,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "attribution": self.attribution.to_dict() if self.attribution else None,
            "is_order_action": False,
            "broker_write_authority": False,
        }


def _parse_time_from_ts(ts_str: str) -> dtime:
    """Extract local time (HH:MM:SS) from ISO string."""
    # Example format: 2026-09-10 09:30:00+05:30 or 2026-09-10T09:30:00+05:30
    clean = ts_str.replace("T", " ")
    parts = clean.split(" ")
    time_part = parts[1] if len(parts) > 1 else parts[0]
    # Remove timezone offset if present
    base_time = time_part.split("+")[0].split("-")[0]
    h, m, s = [int(x) for x in base_time.split(":")[:3]]
    return dtime(hour=h, minute=m, second=s)


def evaluate_c1(
    memory: MarketMemorySnapshot,
    as_of_timestamp: str | None = None,
    trace_id: str | None = None,
) -> EvaluatorResult:
    """Evaluate frozen Candidate 1: ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE.

    Rules:
    - Signal window: 09:30:00 to 14:45:00 IST.
    - Qualification rule: rolling_15m_return_bps > +50.0.
    """
    ts_str = as_of_timestamp or memory.as_of_timestamp
    t_id = trace_id or memory.trace_id
    t = _parse_time_from_ts(ts_str)

    window_start = dtime(9, 30, 0)
    window_end = dtime(14, 45, 0)

    # 1. Freshness check
    if memory.freshness_watermark <= 0.0:
        attr = StrategyEvaluationAttribution(
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            invoked=True,
            input_ready=True,
            input_fresh=False,
            evaluation_status="REJECTED_STALE",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.INPUT_STALE.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.rolling_15m_return_bps,
            threshold=50.0,
            operator=">",
            window_state="STALE_INPUT",
            decision="NO_SIGNAL",
            reason_code=C1ReasonCode.C1_STALE_MEMORY.value,
            qualified=False,
            attribution=attr,
        )

    # 2. Window check: 09:30:00 <= t <= 14:45:00
    in_window = window_start <= t <= window_end
    if not in_window:
        attr = StrategyEvaluationAttribution(
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="OUT_OF_WINDOW",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.rolling_15m_return_bps,
            threshold=50.0,
            operator=">",
            window_state="OUT_OF_WINDOW",
            decision="NO_SIGNAL",
            reason_code=C1ReasonCode.C1_OUT_OF_WINDOW.value,
            qualified=False,
            attribution=attr,
        )

    # 3. History check: requires at least 15 bars
    if memory.rolling_1m_bars_count <= 15:
        attr = StrategyEvaluationAttribution(
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            invoked=True,
            input_ready=False,
            input_fresh=True,
            evaluation_status="MEMORY_NOT_READY",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.INPUT_NOT_READY.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.rolling_15m_return_bps,
            threshold=50.0,
            operator=">",
            window_state="MEMORY_WARMUP",
            decision="NO_SIGNAL",
            reason_code=C1ReasonCode.C1_MEMORY_NOT_READY.value,
            qualified=False,
            attribution=attr,
        )

    # 4. Strict frozen evaluation: rolling_15m_return_bps > +50.0
    val = float(memory.rolling_15m_return_bps)
    is_qualified = val > 50.0

    if is_qualified:
        cand = CandidateEmission(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            symbol=memory.symbol,
            signal_timestamp=ts_str,
            entry_boundary="Open[t+1] on NIFTY Futures",
            exit_boundary="15:10:00 IST close on NIFTY Futures",
            stop_rule="Fixed 40 bps below entry futures open",
            trace_id=t_id,
            features={
                "rolling_15m_return_bps": val,
                "current_price": memory.current_price,
                "distance_from_open_bps": memory.distance_from_session_open_bps,
                "realized_vol_15m": memory.realized_vol_15m,
            },
        )
        attr = StrategyEvaluationAttribution(
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="QUALIFIED",
            candidate_count_before_filters=1,
            candidate_count_after_filters=1,
            candidate_count_after_risk=1,
            candidate_count_after_ranking=1,
            terminal_reason_code=CandidateEmptyClass.CANDIDATE_CREATED.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=val,
            threshold=50.0,
            operator=">",
            window_state="ACTIVE_IN_WINDOW",
            decision="QUALIFIED",
            reason_code=C1ReasonCode.C1_QUALIFIED.value,
            qualified=True,
            candidate=cand,
            attribution=attr,
        )
    else:
        attr = StrategyEvaluationAttribution(
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="EVALUATED_NO_SIGNAL",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            strategy_id="C1_INTRADAY_15M_IMPULSE",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=val,
            threshold=50.0,
            operator=">",
            window_state="ACTIVE_IN_WINDOW",
            decision="NO_SIGNAL",
            reason_code=C1ReasonCode.C1_IMPULSE_BELOW_THRESHOLD.value,
            qualified=False,
            attribution=attr,
        )


def evaluate_c2(
    memory: MarketMemorySnapshot,
    as_of_timestamp: str | None = None,
    trace_id: str | None = None,
) -> EvaluatorResult:
    """Evaluate frozen Candidate 2: ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT.

    Rules:
    - Signal bar: Exactly completed 15:12:00 IST bar.
    - Qualification rule: (close_1512 - session_open) / session_open * 10000 >= +50.0.
    """
    ts_str = as_of_timestamp or memory.as_of_timestamp
    t_id = trace_id or memory.trace_id
    t = _parse_time_from_ts(ts_str)

    target_bar_time = dtime(15, 12, 0)

    # 1. Freshness check
    if memory.freshness_watermark <= 0.0:
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=True,
            input_fresh=False,
            evaluation_status="REJECTED_STALE",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.INPUT_STALE.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.distance_from_session_open_bps,
            threshold=50.0,
            operator=">=",
            window_state="STALE_INPUT",
            decision="NO_SIGNAL",
            reason_code=C2ReasonCode.C2_STALE_MEMORY.value,
            qualified=False,
            attribution=attr,
        )

    # 2. Timing check: Pre-signal, exact bar, or post-signal
    if t < target_bar_time:
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="DORMANT_PRE_SIGNAL",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.distance_from_session_open_bps,
            threshold=50.0,
            operator=">=",
            window_state="DORMANT_PRE_SIGNAL",
            decision="NO_SIGNAL",
            reason_code=C2ReasonCode.C2_PRE_SIGNAL.value,
            qualified=False,
            attribution=attr,
        )

    if t > target_bar_time:
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="POST_SIGNAL_WINDOW",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=memory.distance_from_session_open_bps,
            threshold=50.0,
            operator=">=",
            window_state="POST_SIGNAL_WINDOW",
            decision="NO_SIGNAL",
            reason_code=C2ReasonCode.C2_POST_SIGNAL_WINDOW.value,
            qualified=False,
            attribution=attr,
        )

    # 3. Exact 15:12 evaluation
    if memory.session_open is None or memory.session_open <= 0:
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=False,
            input_fresh=True,
            evaluation_status="SESSION_OPEN_MISSING",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.INPUT_NOT_READY.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=0.0,
            threshold=50.0,
            operator=">=",
            window_state="ERROR_MISSING_SESSION_OPEN",
            decision="NO_SIGNAL",
            reason_code=C2ReasonCode.C2_MEMORY_NOT_READY.value,
            qualified=False,
            attribution=attr,
        )

    val = float(memory.distance_from_session_open_bps)
    is_qualified = val >= 50.0

    if is_qualified:
        cand = CandidateEmission(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            symbol=memory.symbol,
            signal_timestamp=ts_str,
            entry_boundary="15:14:00 IST open on NIFTY Futures",
            exit_boundary="Next-session 09:15:00 IST open on NIFTY Futures",
            stop_rule="UNKNOWN (Next-Session 09:15 Open Exit)",
            trace_id=t_id,
            features={
                "day_trend_at_1512_bps": val,
                "session_open": memory.session_open,
                "close_1512": memory.current_price,
            },
        )
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="QUALIFIED",
            candidate_count_before_filters=1,
            candidate_count_after_filters=1,
            candidate_count_after_risk=1,
            candidate_count_after_ranking=1,
            terminal_reason_code=CandidateEmptyClass.CANDIDATE_CREATED.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=val,
            threshold=50.0,
            operator=">=",
            window_state="SIGNAL_BAR_EVALUATED",
            decision="QUALIFIED",
            reason_code=C2ReasonCode.C2_QUALIFIED.value,
            qualified=True,
            candidate=cand,
            attribution=attr,
        )
    else:
        attr = StrategyEvaluationAttribution(
            strategy_id="C2_OVERNIGHT_TREND",
            invoked=True,
            input_ready=True,
            input_fresh=True,
            evaluation_status="EVALUATED_NO_SIGNAL",
            candidate_count_before_filters=0,
            candidate_count_after_filters=0,
            candidate_count_after_risk=0,
            candidate_count_after_ranking=0,
            terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
        )
        return EvaluatorResult(
            candidate_id="ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            strategy_id="C2_OVERNIGHT_TREND",
            evaluation_timestamp=ts_str,
            trace_id=t_id,
            memory_watermark=memory.freshness_watermark,
            input_value=val,
            threshold=50.0,
            operator=">=",
            window_state="SIGNAL_BAR_EVALUATED",
            decision="NO_SIGNAL",
            reason_code=C2ReasonCode.C2_TREND_BELOW_THRESHOLD.value,
            qualified=False,
            attribution=attr,
        )
