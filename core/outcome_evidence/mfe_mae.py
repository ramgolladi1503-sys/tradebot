from typing import List, Optional
from .evidence_models import ReplayCandidate, OptionTracePoint, MfeMaeEvidence


class MfeMaeCalculator:
    """Computes Maximum Favorable and Adverse Excursions for an outcome window."""

    def calculate(
        self, candidate: ReplayCandidate, traces: List[OptionTracePoint], exit_time: Optional[float]
    ) -> Optional[MfeMaeEvidence]:
        if not traces or candidate.entry_price <= 0:
            return None

        # Determine risk amount for R calculations
        is_long = candidate.target_price > candidate.entry_price
        risk = abs(candidate.entry_price - candidate.stop_price)
        if risk == 0:
            risk = 1.0  # fallback to avoid division by zero
            
        mfe_price = candidate.entry_price
        mae_price = candidate.entry_price
        time_to_mfe = 0.0
        time_to_mae = 0.0
        max_drawdown = 0.0
        
        start_time = traces[0].timestamp
        
        peak_pnl = 0.0
        
        for trace in traces:
            if exit_time and trace.timestamp > exit_time:
                break
                
            pnl = (trace.ltp - candidate.entry_price) if is_long else (candidate.entry_price - trace.ltp)
            
            if is_long:
                if trace.ltp > mfe_price:
                    mfe_price = trace.ltp
                    time_to_mfe = trace.timestamp - start_time
                if trace.ltp < mae_price:
                    mae_price = trace.ltp
                    time_to_mae = trace.timestamp - start_time
            else:
                if trace.ltp < mfe_price:
                    mfe_price = trace.ltp
                    time_to_mfe = trace.timestamp - start_time
                if trace.ltp > mae_price:
                    mae_price = trace.ltp
                    time_to_mae = trace.timestamp - start_time
                    
            if pnl > peak_pnl:
                peak_pnl = pnl
            dd = peak_pnl - pnl
            if dd > max_drawdown:
                max_drawdown = dd

        mfe_points = abs(mfe_price - candidate.entry_price) if mfe_price != candidate.entry_price else 0.0
        mae_points = abs(mae_price - candidate.entry_price) if mae_price != candidate.entry_price else 0.0
        
        # Determine actual sign depending on direction (long/short logic already captured magnitude in points, MFE is always positive, MAE is negative PnL or positive adverse magnitude)
        # We define mfe_points as strictly positive favorable excursion, and mae_points as strictly positive adverse excursion magnitude.

        # If price never went favorable, mfe_points = 0.
        # If it never went adverse, mae_points = 0.
        
        # Realized R
        exit_price = traces[-1].ltp
        if exit_time:
            for t in reversed(traces):
                if t.timestamp <= exit_time:
                    exit_price = t.ltp
                    break
        
        realized_pnl = (exit_price - candidate.entry_price) if is_long else (candidate.entry_price - exit_price)

        return MfeMaeEvidence(
            mfe_points=mfe_points,
            mae_points=mae_points,
            mfe_r=mfe_points / risk,
            mae_r=mae_points / risk,
            realized_r=realized_pnl / risk,
            max_drawdown=max_drawdown,
            time_to_mfe=time_to_mfe,
            time_to_mae=time_to_mae,
            hold_duration=(exit_time - start_time) if exit_time else (traces[-1].timestamp - start_time)
        )
