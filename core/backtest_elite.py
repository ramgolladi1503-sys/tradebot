import numpy as np
import pandas as pd
from dataclasses import dataclass, replace
from typing import List, Dict, Any, Optional

from strategies.trade_builder import TradeBuilder
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from core.feature_builder import add_indicators
from core.option_chain import fetch_option_chain
from core.filters import get_bias
from config import config as cfg


@dataclass
class EliteBacktestConfig:
    vol_target: float = 0.002
    entry_window: int = 3
    horizon: int = 5
    slippage_bps: float = 1.0
    fee_per_trade: float = 0.0
    spread_bps: float = 1.0
    use_synth_chain: bool = True
    starting_capital: float = 100000.0
    target_atr_mult: float = 1.5
    stop_atr_mult: float = 1.0
    allowed_time_start: str = "09:15"
    allowed_time_end: str = "15:30"
    trailing_stop_activation_mult: float = 0.0
    trailing_stop_trail_mult: float = 0.0


class VectorizedBacktestEngine:
    """
    Super Elite Backtest Module
    Provides hyper-fast vectorized evaluations of trading systems and signals.
    """

    def __init__(self, historical_data: pd.DataFrame, config: EliteBacktestConfig = None):
        self.data = historical_data.copy()
        self.config = config or EliteBacktestConfig()
        
        # We still keep references to the OOP modules for hybrid generation
        self.trade_builder = TradeBuilder()
        self.risk_engine = RiskEngine()
        self.execution_guard = ExecutionGuard()
        
        self.portfolio_state = {
            "capital": self.config.starting_capital,
            "trades": [],
            "daily_loss": 0,
            "trades_today": 0
        }

    def _apply_cost(self, price: float, side: str) -> float:
        """Applies dynamic spread and slippage cost."""
        bps = self.config.slippage_bps + self.config.spread_bps
        if side.upper() == "BUY":
            return price * (1 + bps / 10000.0)
        return price * (1 - bps / 10000.0)

    def run_vectorized_signals(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """
        Fast execution engine that processes a DataFrame of pre-computed signals.
        Expects signals_df to have: ['signal_side', 'entry_price', 'target', 'stop_loss', 'qty', 'lot_size']
        """
        if signals_df.empty:
            return pd.DataFrame()
            
        results = []
        highs = self.data["high"].values
        lows = self.data["low"].values
        closes = self.data["close"].values
        
        horizon = self.config.horizon
        entry_window = self.config.entry_window
        
        for idx, row in signals_df.iterrows():
            if idx + horizon >= len(self.data):
                break
                
            side = row.get("signal_side", "BUY")
            entry_price = row["entry_price"]
            target = row["target"]
            stop_loss = row["stop_loss"]
            qty = row["qty"]
            lot_size = row["lot_size"]
            
            # Fast forward-looking slice
            future_highs = highs[idx + 1: idx + 1 + horizon]
            future_lows = lows[idx + 1: idx + 1 + horizon]
            future_closes = closes[idx + 1: idx + 1 + horizon]
            
            if len(future_highs) == 0:
                continue

            entry_fill = self._apply_cost(entry_price, side)
            
            ts_act_mult = self.config.trailing_stop_activation_mult
            ts_trail_mult = self.config.trailing_stop_trail_mult
            
            outcome = "TIMEOUT"
            exit_price = future_closes[-1]
            
            if ts_act_mult > 0 and ts_trail_mult > 0:
                # We need ATR to calculate absolute trailing levels
                # We can approximate ATR from the distance of original stop to entry
                base_atr = abs(entry_price - stop_loss) / max(self.config.stop_atr_mult, 0.0001)
                activation_dist = base_atr * ts_act_mult
                trail_dist = base_atr * ts_trail_mult
                
                current_stop = stop_loss
                if side == "BUY":
                    activation_price = entry_price + activation_dist
                    for i in range(len(future_highs)):
                        h, l = future_highs[i], future_lows[i]
                        if l <= current_stop:
                            outcome = "STOP"
                            exit_price = current_stop
                            break
                        if h >= target:
                            outcome = "TARGET"
                            exit_price = target
                            break
                        if h >= activation_price:
                            new_stop = h - trail_dist
                            if new_stop > current_stop:
                                current_stop = new_stop
                else:
                    activation_price = entry_price - activation_dist
                    for i in range(len(future_lows)):
                        h, l = future_highs[i], future_lows[i]
                        if h >= current_stop:
                            outcome = "STOP"
                            exit_price = current_stop
                            break
                        if l <= target:
                            outcome = "TARGET"
                            exit_price = target
                            break
                        if l <= activation_price:
                            new_stop = l + trail_dist
                            if new_stop < current_stop:
                                current_stop = new_stop
            else:
                # Original fast evaluation
                hit_target = np.any(future_highs >= target) if side == "BUY" else np.any(future_lows <= target)
                hit_stop = np.any(future_lows <= stop_loss) if side == "BUY" else np.any(future_highs >= stop_loss)
                if hit_target and not hit_stop:
                    outcome = "TARGET"
                    exit_price = target
                elif hit_stop and not hit_target:
                    outcome = "STOP"
                    exit_price = stop_loss
                elif hit_stop and hit_target:
                    outcome = "STOP"
                    exit_price = stop_loss
                
            exit_fill = self._apply_cost(exit_price, "SELL" if side == "BUY" else "BUY")
            
            if side == "BUY":
                pl = (exit_fill - entry_fill) * qty * lot_size
            else:
                pl = (entry_fill - exit_fill) * qty * lot_size
                
            pl -= self.config.fee_per_trade * 2
            
            results.append({
                "entry_idx": idx,
                "side": side,
                "entry_price": entry_fill,
                "exit_price": exit_fill,
                "qty": qty,
                "pl": pl,
                "outcome": outcome,
                "rr": abs(target - entry_price) / max(abs(entry_price - stop_loss), 1e-6)
            })
            
        return pd.DataFrame(results)

    def generate_signals_vectorized(self) -> pd.DataFrame:
        """
        Hyper-fast generation: fully bypasses python iteration by using 
        pure Pandas operations to map indicators and signal thresholds.
        """
        from core.vectorized_signals import build_vectorized_signals
        
        # 1. Add indicators
        self.data = add_indicators(self.data).dropna().reset_index(drop=True)
        
        # 2. Vectorized logic mapping
        signals_df = build_vectorized_signals(self.data, self.config)
        
        if not signals_df.empty:
            return self.run_vectorized_signals(signals_df)
        return pd.DataFrame()

    def generate_and_run(self) -> pd.DataFrame:
        """
        Hybrid run: Uses the python logic to build trades, then vectorizes execution.
        """
        self.data = add_indicators(self.data).dropna().reset_index(drop=True)
        signals = []
        
        # We can optimize this loop heavily later, but for now we extract valid trades
        for idx, row in self.data.iterrows():
            if idx + self.config.horizon >= len(self.data):
                break
                
            ltp = row["close"]
            vwap = row.get("vwap", ltp)
            atr = row.get("atr_14", max(1.0, ltp * 0.002))
            
            # Skip heavy synthetic chain fetches to speed up base evaluation if disabled
            option_chain = fetch_option_chain("NIFTY", ltp, force_synthetic=self.config.use_synth_chain)

            market_data = {
                "symbol": "NIFTY",
                "ltp": ltp,
                "vwap": vwap,
                "atr": atr,
                "orb_high": row["high"],
                "orb_low": row["low"],
                "volume": row["volume"],
                "bias": get_bias(ltp, vwap),
                "option_chain": option_chain,
                "timestamp": idx
            }
            trade = self.trade_builder.build(market_data)
            if not trade:
                continue

            allowed, _ = self.risk_engine.allow_trade(self.portfolio_state)
            if not allowed:
                continue

            approved, _ = self.execution_guard.validate(trade, self.portfolio_state, trade.regime)
            if not approved:
                continue

            lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
            current_vol = (atr / ltp) if ltp else None
            sized_qty = self.risk_engine.size_trade(
                trade,
                self.portfolio_state["capital"],
                lot_size,
                current_vol=current_vol,
                vol_target=self.config.vol_target,
            )
            
            signals.append({
                "idx": idx,
                "signal_side": trade.side,
                "entry_price": trade.entry_price,
                "target": trade.target,
                "stop_loss": trade.stop_loss,
                "qty": sized_qty,
                "lot_size": lot_size
            })
            
        signals_df = pd.DataFrame(signals)
        if not signals_df.empty:
            signals_df = signals_df.set_index("idx")
            return self.run_vectorized_signals(signals_df)
        return pd.DataFrame()
