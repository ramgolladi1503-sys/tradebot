from typing import List, Optional
from .evidence_types import OutcomeStatus, ExitReason
from .evidence_models import ReplayCandidate, OptionTracePoint, OutcomeWindow, ReplayOutcome


class OutcomeResolver:
    """Resolves whether a target, stop, or time-stop was hit given a candidate and an option trace."""

    def resolve(self, candidate: ReplayCandidate, traces: List[OptionTracePoint]) -> ReplayOutcome:
        if not traces:
            return self._build_empty_outcome(candidate, OutcomeStatus.NO_TRACE_DATA, ExitReason.UNKNOWN)

        if candidate.target_price <= 0 or candidate.stop_price <= 0:
            return self._build_empty_outcome(
                candidate, OutcomeStatus.INSUFFICIENT_CANDIDATE_FIELDS, ExitReason.UNKNOWN
            )

        start_time = traces[0].timestamp
        
        # We need to find the exact tick where the stop or target was hit.
        # Target usually hit if high >= target. For LTP, we assume LTP crossed.
        # We assume long bias for now, but should ideally handle short bias if needed.
        # The prompt implies: "resolve target hit, stop hit, both hit ambiguity, neither hit, time-stop exit"
        
        target_hit_tick: Optional[OptionTracePoint] = None
        stop_hit_tick: Optional[OptionTracePoint] = None
        time_stop_tick: Optional[OptionTracePoint] = None
        end_tick: Optional[OptionTracePoint] = None

        is_long = candidate.target_price > candidate.entry_price

        for trace in traces:
            end_tick = trace
            if candidate.time_stop and trace.timestamp >= candidate.time_stop:
                time_stop_tick = trace
                break

            if is_long:
                if trace.ltp >= candidate.target_price and not target_hit_tick:
                    target_hit_tick = trace
                if trace.ltp <= candidate.stop_price and not stop_hit_tick:
                    stop_hit_tick = trace
            else:
                if trace.ltp <= candidate.target_price and not target_hit_tick:
                    target_hit_tick = trace
                if trace.ltp >= candidate.stop_price and not stop_hit_tick:
                    stop_hit_tick = trace

            if target_hit_tick and stop_hit_tick:
                break
            if target_hit_tick or stop_hit_tick:
                break

        if target_hit_tick and stop_hit_tick:
            if target_hit_tick.timestamp == stop_hit_tick.timestamp:
                return self._build_outcome(
                    OutcomeStatus.AMBIGUOUS_BOTH_HIT, ExitReason.UNKNOWN, 
                    target_hit_tick.timestamp, target_hit_tick.ltp, candidate, traces
                )
            elif target_hit_tick.timestamp < stop_hit_tick.timestamp:
                return self._build_outcome(
                    OutcomeStatus.TARGET_HIT, ExitReason.TARGET, 
                    target_hit_tick.timestamp, target_hit_tick.ltp, candidate, traces
                )
            else:
                return self._build_outcome(
                    OutcomeStatus.STOP_HIT, ExitReason.STOP, 
                    stop_hit_tick.timestamp, stop_hit_tick.ltp, candidate, traces
                )
                
        if target_hit_tick:
            return self._build_outcome(
                OutcomeStatus.TARGET_HIT, ExitReason.TARGET, 
                target_hit_tick.timestamp, target_hit_tick.ltp, candidate, traces
            )
            
        if stop_hit_tick:
            return self._build_outcome(
                OutcomeStatus.STOP_HIT, ExitReason.STOP, 
                stop_hit_tick.timestamp, stop_hit_tick.ltp, candidate, traces
            )
            
        if time_stop_tick:
            return self._build_outcome(
                OutcomeStatus.TIME_STOP, ExitReason.TIME_STOP, 
                time_stop_tick.timestamp, time_stop_tick.ltp, candidate, traces
            )
            
        return self._build_outcome(
            OutcomeStatus.OPEN_AT_END, ExitReason.END_OF_WINDOW, 
            end_tick.timestamp if end_tick else start_time, 
            end_tick.ltp if end_tick else candidate.entry_price, candidate, traces
        )
        
    def _build_empty_outcome(self, candidate: ReplayCandidate, status: OutcomeStatus, exit_reason: ExitReason) -> ReplayOutcome:
        return ReplayOutcome(
            status=status,
            exit_reason=exit_reason,
            exit_time=None,
            exit_price=None,
            gross_pnl=0.0,
            window=OutcomeWindow(start_time=candidate.timestamp, end_time=candidate.timestamp, duration_seconds=0.0),
            mfe_mae=None
        )
        
    def _build_outcome(self, status: OutcomeStatus, exit_reason: ExitReason, exit_time: float, exit_price: float, candidate: ReplayCandidate, traces: List[OptionTracePoint]) -> ReplayOutcome:
        start_time = traces[0].timestamp
        window = OutcomeWindow(
            start_time=start_time,
            end_time=exit_time,
            duration_seconds=exit_time - start_time
        )
        is_long = candidate.target_price > candidate.entry_price
        gross_pnl = (exit_price - candidate.entry_price) if is_long else (candidate.entry_price - exit_price)
        
        return ReplayOutcome(
            status=status,
            exit_reason=exit_reason,
            exit_time=exit_time,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            window=window,
            mfe_mae=None
        )
