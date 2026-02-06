import json
import time
from pathlib import Path
from datetime import datetime

from config import config as cfg

AUTO_TUNE_PATH = Path("logs/auto_tune.json")
_LAST_TUNE_TS = 0


def _read_recent_trades(path: Path, limit: int):
    if not path.exists():
        return []
    rows = []
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return []
    # iterate from end for most recent
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        # require labeled outcomes
        if obj.get("actual") is None:
            continue
        rows.append(obj)
        if len(rows) >= limit:
            break
    return list(reversed(rows))


def _compute_pnl(trade):
    try:
        entry = float(trade.get("entry", 0) or 0)
        exit_px = trade.get("exit_price")
        if exit_px is None:
            # fallback: use actual outcome with target/stop
            if trade.get("actual") == 1 and trade.get("target") is not None:
                exit_px = trade.get("target")
            elif trade.get("actual") == 0 and trade.get("stop_loss") is not None:
                exit_px = trade.get("stop_loss")
            else:
                exit_px = entry
        exit_px = float(exit_px or entry)
        side = (trade.get("side") or "BUY").upper()
        pnl = exit_px - entry
        if side == "SELL":
            pnl = -pnl
        qty = float(trade.get("qty") or 1)
        return pnl * qty
    except Exception:
        return 0.0


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def compute_auto_tune(window: int = 30):
    trades = _read_recent_trades(Path("data/trade_log.json"), window)
    if len(trades) < max(10, window // 2):
        return {
            "enabled": False,
            "reason": "insufficient_trades",
            "window": len(trades),
        }
    wins = sum(1 for t in trades if t.get("actual") == 1)
    win_rate = wins / max(1, len(trades))
    pnls = [_compute_pnl(t) for t in trades]
    avg_pnl = sum(pnls) / max(1, len(pnls))

    base_min_rr = float(getattr(cfg, "MIN_RR", 1.5))
    base_min_proba = float(getattr(cfg, "ML_MIN_PROBA", 0.45))
    base_score = float(getattr(cfg, "TRADE_SCORE_MIN", 75))

    min_rr = base_min_rr
    min_proba = base_min_proba
    score_min = base_score

    mode = "hold"
    if win_rate < 0.45 or avg_pnl < 0:
        mode = "tighten"
        min_rr = _clamp(base_min_rr + 0.1, 1.2, 2.2)
        min_proba = _clamp(base_min_proba + 0.05, 0.35, 0.8)
        score_min = _clamp(base_score + 5, 55, 90)
    elif win_rate > 0.6 and avg_pnl > 0:
        mode = "loosen"
        min_rr = _clamp(base_min_rr - 0.1, 1.2, 2.2)
        min_proba = _clamp(base_min_proba - 0.03, 0.35, 0.8)
        score_min = _clamp(base_score - 5, 55, 90)

    return {
        "enabled": True,
        "mode": mode,
        "window": len(trades),
        "win_rate": round(win_rate, 3),
        "avg_pnl": round(avg_pnl, 3),
        "min_rr": round(min_rr, 3),
        "min_proba": round(min_proba, 3),
        "trade_score_min": round(score_min, 2),
        "updated_at": datetime.now().isoformat(),
    }


def maybe_auto_tune():
    global _LAST_TUNE_TS
    if not getattr(cfg, "AUTO_TUNE_ENABLE", True):
        return None
    now = time.time()
    every = int(getattr(cfg, "AUTO_TUNE_EVERY_SEC", 600))
    if now - _LAST_TUNE_TS < every:
        return None
    _LAST_TUNE_TS = now
    window = int(getattr(cfg, "AUTO_TUNE_WINDOW", 30))
    result = compute_auto_tune(window=window)
    try:
        AUTO_TUNE_PATH.parent.mkdir(exist_ok=True)
        AUTO_TUNE_PATH.write_text(json.dumps(result, indent=2))
    except Exception:
        pass
    return result
