import json
from pathlib import Path

QUEUE_PATH = Path("logs/review_queue.json")
QUICK_QUEUE_PATH = Path("logs/quick_review_queue.json")
ZERO_HERO_QUEUE_PATH = Path("logs/zero_hero_queue.json")
SCALP_QUEUE_PATH = Path("logs/scalp_queue.json")
APPROVED_PATH = Path("logs/approved_trades.json")

def add_to_queue(trade, queue_path=None, extra=None):
    try:
        from config import config as cfg
        instr = getattr(trade, "instrument", None)
        if instr is None and isinstance(trade, dict):
            instr = trade.get("instrument")
        if instr == "EQ" and not getattr(cfg, "ENABLE_EQUITIES", True):
            return
    except Exception:
        pass
    path = queue_path or QUEUE_PATH
    path.parent.mkdir(exist_ok=True)
    data = []
    if path.exists():
        data = json.loads(path.read_text())
    def get_attr(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    strike_val = get_attr(trade, "strike")
    trade_id = get_attr(trade, "trade_id")
    if strike_val in (None, 0) and trade_id and "ATM" in str(trade_id):
        strike_val = "ATM"
    entry = {
        "trade_id": trade_id,
        "symbol": get_attr(trade, "symbol"),
        "strike": strike_val,
        "instrument": get_attr(trade, "instrument"),
        "instrument_token": get_attr(trade, "instrument_token"),
        "side": get_attr(trade, "side"),
        "entry": get_attr(trade, "entry_price"),
        "entry_condition": get_attr(trade, "entry_condition"),
        "entry_ref_price": get_attr(trade, "entry_ref_price"),
        "stop": get_attr(trade, "stop_loss"),
        "target": get_attr(trade, "target"),
        "qty": get_attr(trade, "qty"),
        "confidence": get_attr(trade, "confidence"),
        "strategy": get_attr(trade, "strategy"),
        "regime": get_attr(trade, "regime"),
        "tier": get_attr(trade, "tier", None),
        "legs": get_attr(trade, "legs", None),
        "max_profit": get_attr(trade, "max_profit", None),
        "max_loss": get_attr(trade, "max_loss", None),
        "max_profit_label": get_attr(trade, "max_profit_label", None),
        "max_loss_label": get_attr(trade, "max_loss_label", None),
        "breakeven_low": get_attr(trade, "breakeven_low", None),
        "breakeven_high": get_attr(trade, "breakeven_high", None),
        "est_pnl_at_ltp": get_attr(trade, "est_pnl_at_ltp", None),
        "opt_ltp": get_attr(trade, "opt_ltp", None),
        "opt_bid": get_attr(trade, "opt_bid", None),
        "opt_ask": get_attr(trade, "opt_ask", None),
        "quote_ok": get_attr(trade, "quote_ok", None),
        "trade_score": get_attr(trade, "trade_score", None),
        "trade_alignment": get_attr(trade, "trade_alignment", None),
        "trade_score_detail": get_attr(trade, "trade_score_detail", None),
        "timestamp": str(get_attr(trade, "timestamp"))
    }
    if extra:
        entry.update(extra)
    data.append(entry)
    path.write_text(json.dumps(data, indent=2))
    # Log suggestion for evaluation
    try:
        sug_path = Path("logs/suggestions.jsonl")
        sug_path.parent.mkdir(exist_ok=True)
        with open(sug_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

def is_approved(trade_id):
    if not APPROVED_PATH.exists():
        return False
    data = json.loads(APPROVED_PATH.read_text())
    return trade_id in data

def approve(trade_id):
    APPROVED_PATH.parent.mkdir(exist_ok=True)
    data = []
    if APPROVED_PATH.exists():
        data = json.loads(APPROVED_PATH.read_text())
    if trade_id not in data:
        data.append(trade_id)
    APPROVED_PATH.write_text(json.dumps(data, indent=2))

def remove_from_queue(trade_id):
    if not QUEUE_PATH.exists():
        return
    data = json.loads(QUEUE_PATH.read_text())
    data = [d for d in data if d.get("trade_id") != trade_id]
    QUEUE_PATH.write_text(json.dumps(data, indent=2))
