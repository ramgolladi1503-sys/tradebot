"""Stage 2 Option Strike Reversal Execution Replay.

Replays options intraday execution with:
- "Blue Line" entry trigger (reclaim / breakout of pre-open reference level)
- Strict next-bar fill at open + half-spread + slippage
- Risk-Reward (R:R) >= 2.0 (e.g. stop = 10 pts, target = 20 pts)
- Full statutory costs (STT on sell, GST, stamp duty on buy, exchange, sebi, brokerage)
- Conservative stop precedence (if both TP and SL hit within same bar, SL wins)
- Strictly rejects missing minute data during holding periods
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional, Union
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TrailingStopConfig:
    """Configuration for breakeven / profit trailing stop."""
    enabled: bool = True
    trigger_r_multiple: float = 1.0
    friction_buffer_points: float = 1.0

    def validate(self) -> None:
        if self.trigger_r_multiple <= 0:
            raise ValueError(f"trigger_r_multiple must be positive, got {self.trigger_r_multiple}")
        if self.friction_buffer_points < 0:
            raise ValueError(f"friction_buffer_points must be non-negative, got {self.friction_buffer_points}")


@dataclass(frozen=True)
class StatutoryCosts:
    """Statutory and broker fee schedule for options trading."""
    brokerage_per_order_inr: float = 20.0
    gst_rate: float = 0.18
    exchange_rate_on_turnover: float = 0.0005
    sebi_rate_on_turnover: float = 0.000001
    stamp_buy_rate: float = 0.00003
    stt_sell_rate: float = 0.000625  # Standard post-budget rate or dated schedule
    half_spread_premium_points: float = 0.25
    slippage_premium_points_per_side: float = 0.25

    def validate(self) -> None:
        for k, v in asdict(self).items():
            if v < 0:
                raise ValueError(f"StatutoryCosts field {k} must be non-negative, got {v}")

    def compute_fees(self, buy_premium: float, sell_premium: float, lot_size: int) -> float:
        """Calculate complete round-trip statutory costs + brokerage."""
        buy_val = buy_premium * lot_size
        sell_val = sell_premium * lot_size
        turnover = buy_val + sell_val

        exchange = turnover * self.exchange_rate_on_turnover
        sebi = turnover * self.sebi_rate_on_turnover
        brokerage = 2.0 * self.brokerage_per_order_inr
        gst = self.gst_rate * (brokerage + exchange + sebi)
        stamp = buy_val * self.stamp_buy_rate
        stt = sell_val * self.stt_sell_rate

        return float(brokerage + exchange + sebi + gst + stamp + stt)


@dataclass(frozen=True)
class ReversalTrade:
    """Completed reversal execution trade."""
    date: str
    expiry: str
    strike: float
    option_type: str
    lot_size: int
    signal_time: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    target_price: float
    stop_price: float
    exit_reason: str  # 'TP', 'SL', 'TIME'
    gross_pnl_points: float
    gross_pnl_inr: float
    total_fees_inr: float
    net_pnl_inr: float
    holding_minutes: int
    reward_risk_ratio: float


@dataclass(frozen=True)
class ReversalReplayResult:
    """Aggregate result of an execution replay."""
    status: str  # 'TRADE', 'NO_SIGNAL', 'REJECT', 'SKIP'
    reason: Optional[str] = None
    trade: Optional[ReversalTrade] = None


class ReversalReplayEngine:
    """Execution replay engine enforcing causal fills, R:R >= 2.0, and cost modeling."""

    def __init__(self, costs: Optional[StatutoryCosts] = None) -> None:
        self.costs = costs or StatutoryCosts()
        self.costs.validate()

    def replay_session(
        self,
        bars_df: pd.DataFrame,
        reference_level: float,
        date: str,
        expiry: str,
        strike: float,
        option_type: str,
        lot_size: int = 50,
        stop_points: float = 10.0,
        target_points: float = 20.0,
        max_hold_minutes: int = 45,
        start_time: str = "09:20",
        end_signal_time: str = "14:15",
        trailing_stop: Optional[TrailingStopConfig] = None,
    ) -> ReversalReplayResult:
        """Execute intraday reversal replay on 1-minute option candles.

        Trigger condition:
        Candle i-1 Close <= reference_level AND Candle i Close > reference_level (Blue line reclaim).

        Execution:
        Fill entry at Candle i+1 Open + half_spread + slippage.
        Stop: entry_fill - stop_points.
        Target: entry_fill + target_points.
        Enforces target_points / stop_points >= 2.0.
        Trailing stop: optionally moves stop to breakeven + buffer once trigger_r_multiple is achieved.
        """
        if stop_points <= 0 or target_points <= 0:
            raise ValueError("stop_points and target_points must be positive")
        if target_points / stop_points < 2.0 - 1e-6:
            raise ValueError(
                f"R:R requirement violated: target ({target_points}) / stop ({stop_points}) "
                f"= {target_points / stop_points:.2f} < 2.0"
            )
        if reference_level <= 0:
            raise ValueError(f"reference_level must be positive, got {reference_level}")
        if lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {lot_size}")
        if trailing_stop is not None:
            trailing_stop.validate()

        df = bars_df.copy()
        if 'timestamp' not in df.columns:
            raise ValueError("bars_df must contain 'timestamp'")

        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        df = df.sort_values('timestamp').reset_index(drop=True)
        if len(df) < 5:
            return ReversalReplayResult(status='SKIP', reason='insufficient candle count')

        n = len(df)
        fees = self.costs

        for i in range(1, n - 1):
            ts = df.at[i, 'timestamp']
            ts_str = ts.strftime('%H:%M')
            if ts_str < start_time:
                continue
            if ts_str > end_signal_time:
                break

            prev = df.iloc[i - 1]
            cur = df.iloc[i]

            # Invariant check: contiguous 1-minute steps
            if ts - prev.timestamp != pd.Timedelta(minutes=1):
                continue

            # Blue Line Reclaim: prior candle closed at/below level, current closed strictly above
            if not (prev.close <= reference_level < cur.close):
                continue

            # Signal confirmed on close of candle i!
            # Entry fills on open of candle i+1
            entry_bar = df.iloc[i + 1]
            if entry_bar.timestamp - ts != pd.Timedelta(minutes=1):
                return ReversalReplayResult(
                    status='REJECT',
                    reason=f'missing next-minute entry bar after signal at {ts}',
                )

            entry_fill = float(
                entry_bar.open + fees.half_spread_premium_points + fees.slippage_premium_points_per_side
            )
            initial_stop_price = max(0.05, entry_fill - stop_points)
            current_stop_price = initial_stop_price
            target_price = entry_fill + target_points

            trailing_active = trailing_stop is not None and trailing_stop.enabled
            trailing_trigger_premium = (
                entry_fill + (trailing_stop.trigger_r_multiple * stop_points)
                if trailing_active and trailing_stop is not None
                else None
            )

            exit_reason: Optional[str] = None
            raw_exit_price: Optional[float] = None
            exit_time_val = None
            holding_count = 0

            limit_idx = min(i + max_hold_minutes, n - 1)
            for j in range(i + 1, limit_idx + 1):
                holding_count += 1
                candle = df.iloc[j]
                if j > i + 1 and (candle.timestamp - df.iloc[j - 1].timestamp != pd.Timedelta(minutes=1)):
                    return ReversalReplayResult(
                        status='REJECT',
                        reason=f'missing minute candle during trade holding at {candle.timestamp}',
                    )

                hit_sl = candle.low <= current_stop_price
                hit_tp = candle.high >= target_price

                # Conservative stop precedence: SL wins if both occur in same bar
                if hit_sl:
                    exit_reason = 'SL'
                    # Slippage/gap on stop: if opened below stop, fill at open, else fill at stop
                    raw_exit_price = min(current_stop_price, float(candle.open))
                    exit_time_val = candle.timestamp
                    break
                elif hit_tp:
                    exit_reason = 'TP'
                    raw_exit_price = target_price
                    exit_time_val = candle.timestamp
                    break
                else:
                    # Check if trailing stop should be ratcheted for subsequent bars
                    if (
                        trailing_active
                        and trailing_trigger_premium is not None
                        and trailing_stop is not None
                        and candle.high >= trailing_trigger_premium
                    ):
                        breakeven_stop = entry_fill + trailing_stop.friction_buffer_points
                        if breakeven_stop > current_stop_price:
                            current_stop_price = breakeven_stop

                    if holding_count >= max_hold_minutes:
                        exit_reason = 'TIME'
                        raw_exit_price = float(candle.close)
                        exit_time_val = candle.timestamp
                        break

            if exit_reason is None:
                # Incomplete holding window at end of data
                return ReversalReplayResult(
                    status='REJECT',
                    reason='incomplete holding window before session close',
                )

            # Apply exit spread and slippage
            exit_fill = max(
                0.05,
                raw_exit_price - fees.half_spread_premium_points - fees.slippage_premium_points_per_side,
            )

            pnl_pts = exit_fill - entry_fill
            gross_pnl = pnl_pts * lot_size
            total_fees = fees.compute_fees(entry_fill, exit_fill, lot_size)
            net_pnl = gross_pnl - total_fees

            trade = ReversalTrade(
                date=date,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=lot_size,
                signal_time=ts.strftime('%H:%M:%S'),
                entry_time=entry_bar.timestamp.strftime('%H:%M:%S'),
                exit_time=exit_time_val.strftime('%H:%M:%S'),
                entry_price=round(entry_fill, 2),
                exit_price=round(exit_fill, 2),
                target_price=round(target_price, 2),
                stop_price=round(initial_stop_price, 2),
                exit_reason=exit_reason,
                gross_pnl_points=round(pnl_pts, 2),
                gross_pnl_inr=round(gross_pnl, 2),
                total_fees_inr=round(total_fees, 2),
                net_pnl_inr=round(net_pnl, 2),
                holding_minutes=holding_count,
                reward_risk_ratio=round(target_points / stop_points, 2),
            )
            return ReversalReplayResult(status='TRADE', trade=trade)

        return ReversalReplayResult(status='NO_SIGNAL')
