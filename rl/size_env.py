import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from rl.size_agent import build_features, discretize, ACTIONS


def _load_jsonl(path: str) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _load_updates():
    updates = _load_jsonl("data/trade_updates.json")
    m = {}
    for u in updates:
        if u.get("type") == "outcome":
            m[u.get("trade_id")] = u
    return m


def _reward(entry, outcome, mult):
    # pnl proxy
    entry_price = entry.get("entry", 0)
    exit_price = outcome.get("exit_price", entry_price)
    qty = entry.get("qty", 1)
    side = entry.get("side", "BUY")
    pnl = (exit_price - entry_price) * qty
    if side == "SELL":
        pnl *= -1
    pnl *= mult

    atr = entry.get("atr") or entry.get("ATR") or 1.0
    base = pnl / max(atr, 1.0)

    # penalties
    dd_pen = 0.0
    if pnl < 0:
        dd_pen = abs(pnl) * 0.01
    tail_pen = 0.0
    if pnl < -2 * atr:
        tail_pen = abs(pnl) * 0.02
    slip = entry.get("slippage", 0) or 0
    exec_pen = abs(slip) * 0.01
    return base - dd_pen - tail_pen - exec_pen


class SizeEnv:
    def __init__(self, trade_log_path="data/trade_log.json"):
        self.trades = _load_jsonl(trade_log_path)
        self.outcomes = _load_updates()
        self.idx = 0
        self.portfolio = {"capital": 100000, "trades": []}
        self.last_md_by_symbol = {}
        self.risk_state = type("Obj", (), {"trade_pnls": [], "daily_max_drawdown": 0.0, "fill_ratio_ewma": 0.7})()

    def reset(self):
        self.idx = 0
        self.portfolio = {"capital": 100000, "trades": []}
        return None

    def step(self, action_mult: float):
        if self.idx >= len(self.trades):
            return None, 0.0, True, {}
        entry = self.trades[self.idx]
        tid = entry.get("trade_id")
        outcome = self.outcomes.get(tid, {"exit_price": entry.get("entry")})

        features = build_features(
            entry,
            {"regime": entry.get("regime"), "regime_probs": entry.get("regime_probs", {})},
            self.risk_state,
            self.portfolio,
            self.last_md_by_symbol
        )
        state = discretize(features)
        reward = _reward(entry, outcome, action_mult)

        self.idx += 1
        done = self.idx >= len(self.trades)
        return state, reward, done, {"trade_id": tid}
