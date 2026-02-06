import json
from datetime import datetime
from core.trade_store import insert_trade, insert_outcome, update_trade_fill_db
from config import config as cfg
from core import log_lock

def log_trade(trade, extra=None):
    log_entry = {
        "trade_id": trade.trade_id,
        "timestamp": str(datetime.now()),
        "symbol": trade.symbol,
        "instrument": trade.instrument,
        "instrument_token": trade.instrument_token,
        "side": trade.side,
        "entry": trade.entry_price,
        "target": trade.target,
        "qty": trade.qty,
        "confidence": trade.confidence,
        "stop_loss": trade.stop_loss,
        "capital_at_risk": trade.capital_at_risk,
        "regime": trade.regime,
        "strategy": trade.strategy,
        "tier": getattr(trade, "tier", "MAIN"),
        "day_type": getattr(trade, "day_type", "UNKNOWN"),
        "predicted": 1 if trade.side == "BUY" else 0,
        "actual": None,
        "exit_price": None,
        "exit_time": None
    }
    if extra:
        log_entry.update(extra)

    with open("data/trade_log.json", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    try:
        insert_trade(log_entry)
    except Exception:
        pass

def _append_update(update_entry):
    with open("data/trade_updates.json", "a") as f:
        f.write(json.dumps(update_entry) + "\n")

def update_trade_outcome(trade_id, exit_price, actual):
    path = "data/trade_log.json"
    from core.strategy_tracker import StrategyTracker
    tracker = StrategyTracker()
    tracker.load("logs/strategy_perf.json")
    strategy = None
    symbol = None
    side = None
    entry_price = None
    qty = None
    if getattr(cfg, "APPEND_ONLY_LOG", False) or log_lock.is_locked():
        # Append-only update record
        entry = {
            "trade_id": trade_id,
            "timestamp": str(datetime.now()),
            "type": "outcome",
            "exit_price": exit_price,
            "exit_time": str(datetime.now()),
            "actual": actual,
        }
        # Compute R-multiple only if we can read the original entry
        try:
            with open(path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    e = json.loads(line)
                    if e.get("trade_id") == trade_id:
                        entry_price = e.get("entry", 0)
                        stop = e.get("stop_loss", 0)
                        side = e.get("side", "BUY")
                        strategy = e.get("strategy")
                        symbol = e.get("symbol")
                        qty = e.get("qty", 1)
                        risk = abs(entry_price - stop) if stop else 0
                        r_mult = 0
                        if risk > 0:
                            if side == "BUY":
                                r_mult = (exit_price - entry_price) / risk
                            else:
                                r_mult = (entry_price - exit_price) / risk
                        entry["r_multiple"] = round(r_mult, 3)
                        entry["r_label"] = 1 if r_mult >= 1 else 0
                        break
        except Exception:
            pass
        _append_update(entry)
        try:
            insert_outcome(entry)
        except Exception:
            pass
        try:
            if entry_price is not None and qty is not None:
                pnl = (exit_price - entry_price) * qty
                if side == "SELL":
                    pnl *= -1
                tracker.record(strategy, pnl)
                tracker.record_symbol(symbol, pnl)
                tracker.save("logs/strategy_perf.json")
        except Exception:
            pass
        return entry

    updated = False
    lines = []
    updated_entry = None

    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("trade_id") == trade_id:
                entry["exit_price"] = exit_price
                entry["exit_time"] = str(datetime.now())
                entry["actual"] = actual
                # Risk-adjusted label (R-multiple)
                entry_price = entry.get("entry", 0)
                strategy = entry.get("strategy")
                symbol = entry.get("symbol")
                side = entry.get("side", "BUY")
                qty = entry.get("qty", 1)
                stop = entry.get("stop_loss", 0)
                risk = abs(entry_price - stop) if stop else 0
                r_mult = 0
                if risk > 0:
                    if side == "BUY":
                        r_mult = (exit_price - entry_price) / risk
                    else:
                        r_mult = (entry_price - exit_price) / risk
                entry["r_multiple"] = round(r_mult, 3)
                entry["r_label"] = 1 if r_mult >= 1 else 0
                updated = True
                updated_entry = entry
            lines.append(json.dumps(entry))

    if updated:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
    if updated_entry:
        try:
            insert_outcome(updated_entry)
        except Exception:
            pass
        try:
            if entry_price is not None and qty is not None:
                pnl = (exit_price - entry_price) * qty
                if side == "SELL":
                    pnl *= -1
                tracker.record(strategy, pnl)
                tracker.record_symbol(symbol, pnl)
                tracker.save("logs/strategy_perf.json")
        except Exception:
            pass
    return updated_entry if updated else None

def update_trade_fill(trade_id, fill_price, latency_ms=None, slippage=None):
    path = "data/trade_log.json"
    if getattr(cfg, "APPEND_ONLY_LOG", False) or log_lock.is_locked():
        entry = {
            "trade_id": trade_id,
            "timestamp": str(datetime.now()),
            "type": "fill",
            "fill_price": fill_price,
        }
        if latency_ms is not None:
            entry["latency_ms"] = latency_ms
        if slippage is not None:
            entry["slippage"] = slippage
        _append_update(entry)
        try:
            update_trade_fill_db(trade_id, fill_price, latency_ms=latency_ms, slippage=slippage)
        except Exception:
            pass
        return entry

    updated = False
    lines = []
    updated_entry = None

    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("trade_id") == trade_id:
                entry["fill_price"] = fill_price
                if latency_ms is not None:
                    entry["latency_ms"] = latency_ms
                if slippage is not None:
                    entry["slippage"] = slippage
                updated = True
                updated_entry = entry
            lines.append(json.dumps(entry))

    if updated:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
    if updated_entry:
        try:
            update_trade_fill_db(trade_id, fill_price, latency_ms=latency_ms, slippage=slippage)
        except Exception:
            pass
    return updated_entry if updated else None
