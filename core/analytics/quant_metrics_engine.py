"""Sentinel Quantitative Metrics Engine.

Calculates multi-session quantitative performance metrics, statutory and frictional
cost attribution, root-cause taxonomy categorization, regime attribution, and
bootstrap confidence intervals for win rate and expectancy.

Preserves Trading Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- status = "NO_CERTIFIED_EDGE"
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from .multi_session_aggregator import NormalizedTrade

# Indian Derivatives Cost Model Parameters (Options):
# STT: 0.10% on sell-side option premium (Post-2024 revised rate)
# Exchange Turnover: 0.0505% (or 0.035% standard NSE options premium fee)
# SEBI Charges: ₹10 per crore = 0.0001% (0.000001) on total premium turnover
# Stamp Duty: 0.003% on buy-side option premium
# Brokerage: ₹20 per executed leg (₹40 round-trip)
# GST: 18% on (brokerage + exchange + sebi)
# Slippage: default 0.5 points spread-crossing buffer

STT_RATE_OPTIONS = 0.0010  # 0.10% on sell premium
EXCHANGE_TURNOVER_RATE = 0.000505  # 0.0505% (50.5 per lakh) or 0.00035
SEBI_RATE = 0.000001  # 0.0001%
STAMP_DUTY_RATE = 0.00003  # 0.003%
BROKERAGE_PER_LEG = 20.0
GST_RATE = 0.18
DEFAULT_SLIPPAGE_PTS = 0.50

# Index lot sizes
LOT_SIZES = {
    "NIFTY": 50,  # Standard NIFTY 50 lot size
    "SENSEX": 20,  # Standard BSE SENSEX lot size (re-indexed 20/25)
}


@dataclass(frozen=True)
class TradeCostBreakdown:
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    slippage_cost: float
    total_frictional_cost: float
    frictional_cost_pts: float
    lot_size: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradeAccounting:
    trade: NormalizedTrade
    gross_pnl_pts: float
    gross_pnl_rupees: float
    costs: TradeCostBreakdown
    net_pnl_pts: float
    net_pnl_rupees: float
    root_cause: str  # "CHOP_DRAG", "TREND_CAPTURE", "PREMATURE_STOP", "RUNNER_TRAILING", "EOD_LIQUIDATION", "UNKNOWN"
    point_in_time_gear: str  # "GEAR_1_RANGE", "GEAR_2_TREND"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.trade.position_id,
            "symbol": self.trade.symbol,
            "underlying": self.trade.underlying,
            "direction": self.trade.direction,
            "entry_time": self.trade.entry_time,
            "exit_time": self.trade.exit_time,
            "entry_price": self.trade.entry_price,
            "exit_price": self.trade.exit_price,
            "opt_entry_ltp": self.trade.opt_entry_ltp,
            "opt_exit_ltp": self.trade.opt_exit_ltp,
            "gross_pnl_pts": self.gross_pnl_pts,
            "gross_pnl_rupees": self.gross_pnl_rupees,
            "net_pnl_pts": self.net_pnl_pts,
            "net_pnl_rupees": self.net_pnl_rupees,
            "costs": self.costs.to_dict(),
            "root_cause": self.root_cause,
            "point_in_time_gear": self.point_in_time_gear,
            "exit_reason": self.trade.exit_reason,
            "is_in_flight": self.trade.is_in_flight,
        }


@dataclass
class BootstrapConfidenceInterval:
    metric_name: str
    sample_value: float
    bootstrap_mean: float
    standard_error: float
    ci_95_lower: float
    ci_95_upper: float
    ci_99_lower: float
    ci_99_upper: float
    num_resamples: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SummaryQuantKPIs:
    total_trades: int
    completed_trades: int
    in_flight_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    gross_pnl_rupees: float
    net_pnl_rupees: float
    total_frictional_costs: float
    profit_factor: float
    win_loss_ratio: float
    avg_win_rupees: float
    avg_loss_rupees: float
    expectancy_rupees: float
    max_drawdown_rupees: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    status: str = "NO_CERTIFIED_EDGE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QuantMetricsEngine:
    """Computes statutory deductions, quant ratios, root cause taxonomy, and bootstrap CIs."""

    def __init__(
        self,
        stt_rate: float = STT_RATE_OPTIONS,
        exchange_rate: float = EXCHANGE_TURNOVER_RATE,
        sebi_rate: float = SEBI_RATE,
        stamp_duty_rate: float = STAMP_DUTY_RATE,
        brokerage_per_leg: float = BROKERAGE_PER_LEG,
        gst_rate: float = GST_RATE,
        slippage_pts: float = DEFAULT_SLIPPAGE_PTS,
    ) -> None:
        self.stt_rate = stt_rate
        self.exchange_rate = exchange_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.brokerage_per_leg = brokerage_per_leg
        self.gst_rate = gst_rate
        self.slippage_pts = slippage_pts

    def calculate_trade_costs(
        self,
        trade: NormalizedTrade,
        lot_size: Optional[int] = None,
    ) -> TradeCostBreakdown:
        """Calculate complete statutory charges and slippage for an options trade."""
        if lot_size is None:
            lot_size = LOT_SIZES.get(trade.underlying, 50)

        entry_ltp = trade.opt_entry_ltp if trade.opt_entry_ltp is not None else 0.0
        exit_ltp = trade.opt_exit_ltp if trade.opt_exit_ltp is not None else entry_ltp

        # 1. Brokerage (2 legs = entry + exit)
        legs = 2 if not trade.is_in_flight else 1
        brokerage = self.brokerage_per_leg * legs

        # 2. STT: on option premium sell side only
        # For long option buyers, sell happens at exit.
        sell_turnover = exit_ltp * lot_size
        stt = sell_turnover * self.stt_rate if not trade.is_in_flight else 0.0

        # 3. Exchange turnover charges: on total premium turnover (buy + sell)
        total_turnover = (entry_ltp + exit_ltp) * lot_size
        exchange_charges = total_turnover * self.exchange_rate

        # 4. SEBI turnover charges: 0.0001% on total turnover
        sebi_charges = total_turnover * self.sebi_rate

        # 5. Stamp duty: on buy side premium only
        buy_turnover = entry_ltp * lot_size
        stamp_duty = buy_turnover * self.stamp_duty_rate

        # 6. GST: 18% on (brokerage + exchange + sebi)
        gst = (brokerage + exchange_charges + sebi_charges) * self.gst_rate

        # 7. Slippage: bid-ask spread crossing buffer
        slippage_cost = (self.slippage_pts * 2.0) * lot_size
        total_frictional = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + slippage_cost
        frictional_pts = total_frictional / lot_size if lot_size > 0 else 0.0

        return TradeCostBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_charges=round(exchange_charges, 2),
            sebi_charges=round(sebi_charges, 2),
            stamp_duty=round(stamp_duty, 2),
            gst=round(gst, 2),
            slippage_cost=round(slippage_cost, 2),
            total_frictional_cost=round(total_frictional, 2),
            frictional_cost_pts=round(frictional_pts, 2),
            lot_size=lot_size,
        )

    def classify_root_cause(self, trade: NormalizedTrade) -> str:
        """Classify trade exit into root-cause taxonomy:
        - Chop Drag: stopped out or scratch pnl in low efficiency / range regime
        - Trend Capture: positive trend capture meeting target or major gain
        - Premature Stop: stopped out with minor loss despite significant favorable excursion
        - Runner Trailing: runner locked in profit trailing exit
        - EOD Liquidation: liquidated at end of day (or crash recovery fail-closed)
        """
        reason = str(trade.exit_reason or "").upper()
        pnl = trade.opt_pnl_pts if trade.opt_pnl_pts is not None else 0.0
        peak = trade.opt_peak_hwm if trade.opt_peak_hwm is not None else 0.0
        entry = trade.opt_entry_ltp if trade.opt_entry_ltp is not None else 0.0
        gear = trade.session_gear

        if "CRASH_RECOVERY" in reason or "LIQUIDATED" in reason or "EOD" in reason:
            return "EOD_LIQUIDATION"

        raw = trade.raw_payload or {}
        is_half_booked = bool(raw.get("half_booked") or raw.get("target_1_hit"))
        if is_half_booked and entry and peak and trade.opt_exit_ltp is not None:
            # Check blended PnL for root-cause classification
            blended_pnl = 0.5 * max(0.0, float(peak) - float(entry)) + 0.5 * (float(trade.opt_exit_ltp) - float(entry))
        else:
            blended_pnl = pnl

        if "RUNNER_HWM" in reason:
            if blended_pnl > 0 or is_half_booked:
                return "Runner Trailing"
            else:
                return "Chop Drag"

        if "TARGET" in reason:
            return "Trend Capture"

        # Check premature stop: was up significantly (e.g. >= 8 pts) but stopped out with <= 0
        max_excursion = (peak - entry) if peak and entry else 0.0
        if ("STOP" in reason or "SL" in reason) and max_excursion >= 8.0 and pnl <= 2.0:
            return "Premature Stop"

        if pnl > 10.0:
            return "Trend Capture"

        if "TRAILING_STOP_HIT" in reason:
            if pnl >= 5.0:
                return "Runner Trailing"
            elif pnl >= 0.0:
                return "Trend Capture"
            else:
                return "Chop Drag"

        if ("STOP_LOSS" in reason or "OPTION_NATIVE_STOP_LOSS" in reason) and pnl < 0:
            if gear == "GEAR_1_RANGE":
                return "Chop Drag"
            return "Premature Stop" if max_excursion > 5.0 else "Chop Drag"

        return "Chop Drag" if pnl <= 0 else "Trend Capture"

    def process_trades(self, trades: Sequence[NormalizedTrade]) -> List[TradeAccounting]:
        """Convert normalized trades to complete trade accounting ledgers."""
        accountings: List[TradeAccounting] = []
        for t in trades:
            lot_size = LOT_SIZES.get(t.underlying, 50)
            costs = self.calculate_trade_costs(t, lot_size=lot_size)

            # Option PnL takes precedence; fall back to spot pnl if option ltp not available
            raw = t.raw_payload or {}
            is_half_booked = bool(raw.get("half_booked") or raw.get("target_1_hit"))
            
            if is_half_booked and t.opt_entry_ltp is not None and t.opt_peak_hwm is not None and t.opt_exit_ltp is not None:
                # Blended APM accounting: 50% booked at Target / Peak gain, 50% exited at trailing stop
                target_gain_pts = max(0.0, float(t.opt_peak_hwm) - float(t.opt_entry_ltp))
                runner_exit_pts = float(t.opt_exit_ltp) - float(t.opt_entry_ltp)
                gross_pnl_pts = 0.5 * target_gain_pts + 0.5 * runner_exit_pts
            else:
                gross_pnl_pts = (
                    t.opt_pnl_pts
                    if t.opt_pnl_pts is not None
                    else (t.pnl_pts if t.pnl_pts is not None else 0.0)
                )
            gross_pnl_rupees = gross_pnl_pts * lot_size
            net_pnl_rupees = gross_pnl_rupees - costs.total_frictional_cost
            net_pnl_pts = net_pnl_rupees / lot_size if lot_size > 0 else 0.0

            root_cause = self.classify_root_cause(t)
            point_in_time_gear = t.session_gear

            accountings.append(
                TradeAccounting(
                    trade=t,
                    gross_pnl_pts=round(gross_pnl_pts, 2),
                    gross_pnl_rupees=round(gross_pnl_rupees, 2),
                    costs=costs,
                    net_pnl_pts=round(net_pnl_pts, 2),
                    net_pnl_rupees=round(net_pnl_rupees, 2),
                    root_cause=root_cause,
                    point_in_time_gear=point_in_time_gear,
                )
            )
        return accountings

    def compute_summary_kpis(self, accountings: Sequence[TradeAccounting]) -> SummaryQuantKPIs:
        """Compute complete quant summary KPIs across accountings."""
        total = len(accountings)
        if total == 0:
            return SummaryQuantKPIs(
                total_trades=0,
                completed_trades=0,
                in_flight_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                gross_pnl_rupees=0.0,
                net_pnl_rupees=0.0,
                total_frictional_costs=0.0,
                profit_factor=0.0,
                win_loss_ratio=0.0,
                avg_win_rupees=0.0,
                avg_loss_rupees=0.0,
                expectancy_rupees=0.0,
                max_drawdown_rupees=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                status="NO_CERTIFIED_EDGE",
            )

        completed = [a for a in accountings if not a.trade.is_in_flight]
        in_flight = [a for a in accountings if a.trade.is_in_flight]

        # Use net pnl for realized statistics
        wins = [a.net_pnl_rupees for a in completed if a.net_pnl_rupees > 0]
        losses = [a.net_pnl_rupees for a in completed if a.net_pnl_rupees < 0]

        winning_count = len(wins)
        losing_count = len(losses)
        n_completed = len(completed)
        win_rate = (winning_count / n_completed * 100.0) if n_completed > 0 else 0.0

        gross_pnl = sum(a.gross_pnl_rupees for a in completed)
        net_pnl = sum(a.net_pnl_rupees for a in completed)
        total_costs = sum(a.costs.total_frictional_cost for a in completed)

        sum_wins = sum(wins)
        sum_losses = abs(sum(losses))
        profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

        avg_win = (sum_wins / winning_count) if winning_count > 0 else 0.0
        avg_loss = (sum_losses / losing_count) if losing_count > 0 else 0.0
        win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        expectancy = (net_pnl / n_completed) if n_completed > 0 else 0.0

        # Max Drawdown calculation
        cumulative_curve = []
        running = 0.0
        peak = 0.0
        max_dd = 0.0
        for a in completed:
            running += a.net_pnl_rupees
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
            cumulative_curve.append(running)

        max_dd_pct = (max_dd / peak * 100.0) if peak > 0 else 0.0

        # Daily Sharpe & Sortino calculation
        # Group completed trades by date
        daily_pnl: Dict[str, float] = {}
        for a in completed:
            day = a.trade.entry_time[:10]
            daily_pnl[day] = daily_pnl.get(day, 0.0) + a.net_pnl_rupees

        daily_returns = list(daily_pnl.values())
        if len(daily_returns) > 1:
            mean_ret = float(np.mean(daily_returns))
            std_ret = float(np.std(daily_returns, ddof=1))
            sharpe = (mean_ret / std_ret * math.sqrt(252.0)) if std_ret > 1e-6 else 0.0

            # Downside semivariance for Sortino
            downside = [r for r in daily_returns if r < 0]
            if downside:
                downside_std = math.sqrt(sum(d**2 for d in downside) / len(downside))
                sortino = (mean_ret / downside_std * math.sqrt(252.0)) if downside_std > 1e-6 else 0.0
            else:
                sortino = 99.0 if mean_ret > 0 else 0.0
        else:
            sharpe = 0.0
            sortino = 0.0

        calmar = (net_pnl / max_dd) if max_dd > 0 else 0.0

        return SummaryQuantKPIs(
            total_trades=total,
            completed_trades=n_completed,
            in_flight_trades=len(in_flight),
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate_pct=round(win_rate, 2),
            gross_pnl_rupees=round(gross_pnl, 2),
            net_pnl_rupees=round(net_pnl, 2),
            total_frictional_costs=round(total_costs, 2),
            profit_factor=round(profit_factor, 2),
            win_loss_ratio=round(win_loss_ratio, 2),
            avg_win_rupees=round(avg_win, 2),
            avg_loss_rupees=round(avg_loss, 2),
            expectancy_rupees=round(expectancy, 2),
            max_drawdown_rupees=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            status="NO_CERTIFIED_EDGE",
        )

    def bootstrap_confidence_intervals(
        self,
        accountings: Sequence[TradeAccounting],
        n_resamples: int = 2000,
        random_seed: int = 42,
    ) -> Dict[str, BootstrapConfidenceInterval]:
        """Compute bootstrap confidence intervals for win rate and expectancy."""
        completed = [a for a in accountings if not a.trade.is_in_flight]
        if len(completed) < 2:
            return {}

        np.random.seed(random_seed)
        net_pnls = np.array([a.net_pnl_rupees for a in completed], dtype=np.float64)
        is_win = (net_pnls > 0).astype(np.float64)
        n = len(completed)

        boot_win_rates = np.zeros(n_resamples, dtype=np.float64)
        boot_expectancies = np.zeros(n_resamples, dtype=np.float64)

        for i in range(n_resamples):
            indices = np.random.choice(n, size=n, replace=True)
            resampled_pnl = net_pnls[indices]
            resampled_win = is_win[indices]
            boot_win_rates[i] = np.mean(resampled_win) * 100.0
            boot_expectancies[i] = np.mean(resampled_pnl)

        # Win Rate CI
        sample_win_rate = float(np.mean(is_win) * 100.0)
        win_se = float(np.std(boot_win_rates, ddof=1))
        win_ci_95 = (float(np.percentile(boot_win_rates, 2.5)), float(np.percentile(boot_win_rates, 97.5)))
        win_ci_99 = (float(np.percentile(boot_win_rates, 0.5)), float(np.percentile(boot_win_rates, 99.5)))

        # Expectancy CI
        sample_expectancy = float(np.mean(net_pnls))
        exp_se = float(np.std(boot_expectancies, ddof=1))
        exp_ci_95 = (float(np.percentile(boot_expectancies, 2.5)), float(np.percentile(boot_expectancies, 97.5)))
        exp_ci_99 = (float(np.percentile(boot_expectancies, 0.5)), float(np.percentile(boot_expectancies, 99.5)))

        return {
            "win_rate": BootstrapConfidenceInterval(
                metric_name="win_rate_pct",
                sample_value=round(sample_win_rate, 2),
                bootstrap_mean=round(float(np.mean(boot_win_rates)), 2),
                standard_error=round(win_se, 2),
                ci_95_lower=round(win_ci_95[0], 2),
                ci_95_upper=round(win_ci_95[1], 2),
                ci_99_lower=round(win_ci_99[0], 2),
                ci_99_upper=round(win_ci_99[1], 2),
                num_resamples=n_resamples,
            ),
            "expectancy": BootstrapConfidenceInterval(
                metric_name="expectancy_rupees",
                sample_value=round(sample_expectancy, 2),
                bootstrap_mean=round(float(np.mean(boot_expectancies)), 2),
                standard_error=round(exp_se, 2),
                ci_95_lower=round(exp_ci_95[0], 2),
                ci_95_upper=round(exp_ci_95[1], 2),
                ci_99_lower=round(exp_ci_99[0], 2),
                ci_99_upper=round(exp_ci_99[1], 2),
                num_resamples=n_resamples,
            ),
        }
