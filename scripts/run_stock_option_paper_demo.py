from __future__ import annotations

import json
import time

from core.candidate_generator import generate_candidates
from core.paper_portfolio_optimizer import PaperPortfolioOptimizer
from core.paper_trading_engine import PaperTradingEngine


def build_demo_market_data() -> dict[str, dict]:
    now_age = 0.4
    return {
        "NIFTY": {
            "symbol": "NIFTY",
            "ltp": 24500.0,
            "vwap": 24480.0,
            "regime": "TREND",
            "option_chain": [
                {"strike": 24450, "expiry": "2026-04-30", "option_type": "CE"},
                {"strike": 24500, "expiry": "2026-04-30", "option_type": "CE"},
                {"strike": 24550, "expiry": "2026-04-30", "option_type": "PE"},
            ],
        },
        "BANKNIFTY": {
            "symbol": "BANKNIFTY",
            "ltp": 53200.0,
            "vwap": 53120.0,
            "regime": "TREND",
            "option_chain": [
                {"strike": 53100, "expiry": "2026-04-30", "option_type": "CE"},
                {"strike": 53200, "expiry": "2026-04-30", "option_type": "CE"},
                {"strike": 53300, "expiry": "2026-04-30", "option_type": "PE"},
            ],
        },
        "RELIANCE": {
            "symbol": "RELIANCE",
            "ltp": 2520.0,
            "vwap": 2511.0,
            "regime": "TREND",
            "bias": "bullish",
            "option_chain": [
                {
                    "strike": 2500,
                    "expiry": "2026-04-30",
                    "option_type": "CE",
                    "tradingsymbol": "RELIANCE26APR2500CE",
                    "instrument_token": 111001,
                    "best_bid": 120.0,
                    "best_ask": 121.0,
                    "ltp": 120.5,
                    "oi": 180000,
                    "volume": 32000,
                    "quote_age_sec": now_age,
                },
                {
                    "strike": 2520,
                    "expiry": "2026-04-30",
                    "option_type": "CE",
                    "tradingsymbol": "RELIANCE26APR2520CE",
                    "instrument_token": 111002,
                    "best_bid": 108.0,
                    "best_ask": 109.0,
                    "ltp": 108.5,
                    "oi": 150000,
                    "volume": 28000,
                    "quote_age_sec": now_age,
                },
            ],
        },
        "HDFCBANK": {
            "symbol": "HDFCBANK",
            "ltp": 1710.0,
            "vwap": 1708.0,
            "regime": "TREND",
            "bias": "bullish",
            "option_chain": [
                {
                    "strike": 1700,
                    "expiry": "2026-04-30",
                    "option_type": "CE",
                    "tradingsymbol": "HDFCBANK26APR1700CE",
                    "instrument_token": 222001,
                    "best_bid": 94.0,
                    "best_ask": 95.0,
                    "ltp": 94.6,
                    "oi": 110000,
                    "volume": 21000,
                    "quote_age_sec": now_age,
                }
            ],
        },
        "ICICIBANK": {
            "symbol": "ICICIBANK",
            "ltp": 1430.0,
            "vwap": 1436.0,
            "regime": "RANGE",
            "bias": "bearish",
            "option_chain": [
                {
                    "strike": 1430,
                    "expiry": "2026-04-30",
                    "option_type": "PE",
                    "tradingsymbol": "ICICIBANK26APR1430PE",
                    "instrument_token": 333001,
                    "best_bid": 72.0,
                    "best_ask": 73.0,
                    "ltp": 72.5,
                    "oi": 98000,
                    "volume": 18000,
                    "quote_age_sec": now_age,
                }
            ],
        },
    }


def main() -> None:
    market_data_by_symbol = build_demo_market_data()
    candidates = generate_candidates(market_data_by_symbol, ts_epoch=time.time())
    stock_candidates = [row for row in candidates if str(row.get("candidate_type") or "") == "stock_option"]

    optimizer = PaperPortfolioOptimizer()
    portfolio_snapshot = {"open_positions": []}
    optimized = optimizer.optimize(stock_candidates, portfolio_snapshot=portfolio_snapshot, max_selected=2, per_strategy_cap=1)

    engine = PaperTradingEngine()
    entered = []
    now_ts = time.time()
    for row in optimized:
        if not row.allowed or row.allocated_qty <= 0:
            continue
        source = next((c for c in stock_candidates if str(c.get("tradingsymbol") or c.get("symbol")) in row.trade_id or str(c.get("symbol")) == row.symbol), None)
        if not source:
            source = next((c for c in stock_candidates if str(c.get("symbol")) == row.symbol and str(c.get("strategy_family")) == row.strategy_family), None)
        if not source:
            continue
        candidate = dict(source)
        candidate["qty"] = row.allocated_qty
        trade = engine.enter_position(candidate, now_ts)
        if trade is not None:
            entered.append(trade.trade_id)
            engine.mark_position(trade.trade_id, float(trade.entry_price) * 1.08, now_ts + 60)
            engine.exit_position(trade.trade_id, float(trade.entry_price) * 1.08, now_ts + 60, reason="demo_take_profit")

    snapshot = engine.snapshot()
    output = {
        "candidate_count": len(candidates),
        "stock_candidate_count": len(stock_candidates),
        "optimizer": [row.__dict__ for row in optimized],
        "entered_trade_ids": entered,
        "paper_snapshot": snapshot.__dict__,
    }
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
