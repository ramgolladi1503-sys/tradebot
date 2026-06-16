import pandas as pd
from dataclasses import replace
from strategies.trade_builder import TradeBuilder
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from core.execution_engine import ExecutionEngine
from core.feature_builder import add_indicators
from core.option_chain import fetch_option_chain
from core.filters import get_bias
from datetime import datetime
from config import config as cfg

import warnings

class BacktestEngine:
    def __init__(self, historical_data: pd.DataFrame, starting_capital=100000, train_stats=None, research_mode="PROXY_RESEARCH"):
        warnings.warn("BacktestEngine is deprecated. Use OptionBacktestEngine or VectorizedBacktestEngine.", DeprecationWarning, stacklevel=2)
        self.data = historical_data
        self.capital = starting_capital
        self.train_stats = train_stats or {}
        self.research_mode = research_mode
        self.portfolio = {
            "capital": starting_capital,
            "trades": [],
            "daily_loss": 0,
            "trades_today": 0
        }
        self.trade_builder = TradeBuilder()
        self.risk_engine = RiskEngine()
        self.execution_guard = ExecutionGuard()
        self.execution_engine = ExecutionEngine()
        self.vol_target = self.train_stats.get("vol_target") or getattr(cfg, "VOL_TARGET", 0.002)
        self.entry_window = getattr(cfg, "BACKTEST_ENTRY_WINDOW", 3)
        self.horizon = getattr(cfg, "BACKTEST_HORIZON", 5)
        self.slippage_bps = getattr(cfg, "BACKTEST_SLIPPAGE_BPS", 5)
        self.fee_per_trade = getattr(cfg, "BACKTEST_FEE_PER_TRADE", 0.0)
        self.spread_bps = getattr(cfg, "BACKTEST_SPREAD_BPS", 5)

    def run(self):
        results = []
        data = add_indicators(self.data).dropna().reset_index(drop=True)
        horizon = self.horizon

        for idx, row in data.iterrows():
            if idx + horizon >= len(data):
                break

            ltp = row["close"]
            vwap = row.get("vwap", ltp)
            atr = row.get("atr_14", max(1.0, ltp * 0.002))
            option_chain = fetch_option_chain("NIFTY", ltp, force_synthetic=getattr(cfg, "BACKTEST_USE_SYNTH_CHAIN", False))

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
                "timestamp": row.get("timestamp_epoch", idx)
            }
            trade = self.trade_builder.build(market_data)
            if not trade:
                continue

            # Risk Engine check
            allowed, reason = self.risk_engine.allow_trade(self.portfolio)
            if not allowed:
                continue

            # Execution Guard check
            approved, reason = self.execution_guard.validate(trade, self.portfolio, trade.regime)
            if not approved:
                continue

            # Risk sizing (vol target from train window)
            lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
            current_vol = (atr / ltp) if ltp else None
            sized_qty = self.risk_engine.size_trade(
                trade,
                self.portfolio["capital"],
                lot_size,
                current_vol=current_vol,
                vol_target=self.vol_target,
            )
            trade = replace(trade, qty=sized_qty, capital_at_risk=round((trade.entry_price - trade.stop_loss) * sized_qty * lot_size, 2))

            # Simulate execution using future bars
            future = data.iloc[idx + 1: idx + 1 + horizon]
            # Entry trigger: only enter if price crosses entry condition
            entry_idx = None
            if trade.entry_condition == "BUY_ABOVE":
                for j, r in future.head(self.entry_window).iterrows():
                    if r["high"] >= trade.entry_price:
                        entry_idx = j
                        break
            elif trade.entry_condition == "SELL_BELOW":
                for j, r in future.head(self.entry_window).iterrows():
                    if r["low"] <= trade.entry_price:
                        entry_idx = j
                        break
            else:
                entry_idx = future.index[0] if not future.empty else None

            if entry_idx is None:
                continue

            eval_start = data.index.get_loc(entry_idx) + 1
            eval_slice = data.iloc[eval_start: eval_start + horizon]
            if eval_slice.empty:
                continue

            outcome = "TIMEOUT"
            is_ambiguous = False
            exit_price = eval_slice["close"].iloc[-1] if not eval_slice.empty else trade.entry_price

            for _, eval_row in eval_slice.iterrows():
                h, l = eval_row["high"], eval_row["low"]
                if trade.side == "BUY":
                    tgt_hit = h >= trade.target
                    stp_hit = l <= trade.stop_loss
                else:
                    tgt_hit = l <= trade.target
                    stp_hit = h >= trade.stop_loss

                if tgt_hit and stp_hit:
                    outcome = "STOP"
                    exit_price = trade.stop_loss
                    is_ambiguous = True
                    break
                elif stp_hit:
                    outcome = "STOP"
                    exit_price = trade.stop_loss
                    break
                elif tgt_hit:
                    outcome = "TARGET"
                    exit_price = trade.target
                    break

            # Apply costs/slippage to fills
            def _apply_cost(price, side):
                bps = self.slippage_bps + self.spread_bps
                if side == "BUY":
                    return price * (1 + bps / 10000.0)
                return price * (1 - bps / 10000.0)

            entry_fill = _apply_cost(trade.entry_price, "BUY" if trade.side == "BUY" else "SELL")
            exit_fill = _apply_cost(exit_price, "SELL" if trade.side == "BUY" else "BUY")

            if trade.side == "BUY":
                pl = (exit_fill - entry_fill) * trade.qty * lot_size
            else:
                pl = (entry_fill - exit_fill) * trade.qty * lot_size

            # Fees (entry + exit)
            pl -= self.fee_per_trade * 2

            self.portfolio["capital"] += pl
            self.portfolio["trades"].append(trade)
            self.portfolio["trades_today"] += 1

            results.append({
                "timestamp": trade.timestamp,
                "symbol": trade.symbol,
                "side": trade.side,
                "entry": trade.entry_price,
                "entry_condition": getattr(trade, "entry_condition", None),
                "entry_ref_price": getattr(trade, "entry_ref_price", None),
                "target": trade.target,
                "stop_loss": trade.stop_loss,
                "qty": trade.qty,
                "pl": pl,
                "outcome": outcome,
                "ambiguous_exit_rows": 1 if is_ambiguous else 0,
                "capital": self.portfolio["capital"],
                "strategy": getattr(trade, "strategy", None),
                "regime": getattr(trade, "regime", None),
                "day_type": getattr(trade, "day_type", None),
                "rr": round(abs(trade.target - trade.entry_price) / max(abs(trade.entry_price - trade.stop_loss), 1e-6), 3),
            })

        return pd.DataFrame(results)
