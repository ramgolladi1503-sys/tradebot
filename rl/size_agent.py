from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple

from config import config as cfg
from core.greeks import greeks as calc_greeks


ACTIONS = [0.0, 0.25, 0.5, 0.75, 1.0]


def _bin(value: float, edges: list[float]) -> int:
    for i, e in enumerate(edges):
        if value <= e:
            return i
    return len(edges)


def _safe(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _regime_bucket(regime: str | None) -> int:
    r = (regime or "NEUTRAL").upper()
    mapping = {"TREND": 0, "RANGE": 1, "RANGE_VOLATILE": 2, "EVENT": 3, "PANIC": 4, "NEUTRAL": 5}
    return mapping.get(r, 5)


def _time_bucket(hour: int) -> int:
    if hour < 11:
        return 0
    if hour < 14:
        return 1
    return 2


def _default_corr(sym1: str, sym2: str) -> float:
    if sym1 == sym2:
        return 1.0
    pair = tuple(sorted([sym1, sym2]))
    corr_map = getattr(cfg, "SYMBOL_CORRELATIONS", {})
    return float(corr_map.get(pair, 0.85))


def _exposure_for_trade(trade, spot: float | None, iv: float | None, lot_size: int) -> Dict[str, float]:
    side = (getattr(trade, "side", "BUY") or "BUY").upper()
    sign = 1.0 if side == "BUY" else -1.0
    instrument = (getattr(trade, "instrument", "OPT") or "OPT").upper()
    if instrument in ("FUT", "EQ"):
        return {"delta": sign * 1.0 * lot_size, "gamma": 0.0, "vega": 0.0}

    strike = _safe(getattr(trade, "strike", 0))
    vol = iv or _safe(getattr(trade, "iv", 0.3), 0.3)
    t = 7 / 365
    is_call = str(getattr(trade, "type", "CE")).upper().startswith("C")
    if not spot or spot <= 0 or strike <= 0:
        delta = 0.5 if is_call else -0.5
        return {"delta": sign * delta * lot_size, "gamma": 0.0, "vega": 0.0}
    g = calc_greeks(spot, strike, t, vol, is_call=is_call)
    return {
        "delta": sign * g["delta"] * lot_size,
        "gamma": sign * g["gamma"] * lot_size,
        "vega": sign * g["vega"] * lot_size,
    }


def _portfolio_exposure(open_trades, last_md_by_symbol):
    exp = {"delta": 0.0, "gamma": 0.0, "vega": 0.0}
    for ot in open_trades:
        sym = getattr(ot, "symbol", None)
        md = (last_md_by_symbol or {}).get(sym, {})
        spot = _safe(md.get("ltp"), 0.0)
        iv = _safe(md.get("iv"), None) if md.get("iv") is not None else None
        lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(sym, 1))
        e = _exposure_for_trade(ot, spot, iv, lot_size)
        qty = int(getattr(ot, "qty", 1) or 1)
        exp["delta"] += e["delta"] * qty
        exp["gamma"] += e["gamma"] * qty
        exp["vega"] += e["vega"] * qty
    return exp


def build_features(trade, market_data, risk_state, portfolio, last_md_by_symbol):
    score = _safe(getattr(trade, "trade_score", None) or market_data.get("trade_score") or 0.0)
    score = score / 100.0 if score > 1.5 else score

    regime_probs = market_data.get("regime_probs") or {}
    prob_max = max(regime_probs.values()) if regime_probs else 0.5

    fill_prob = _safe(market_data.get("fill_prob"), 0.7)
    exec_q = _safe(getattr(risk_state, "fill_ratio_ewma", None) or 0.7)

    pnl_streak = 0
    try:
        # Approx: use last 5 PnLs sign
        pnls = list(getattr(risk_state, "trade_pnls", []))[-5:]
        for p in reversed(pnls):
            if p > 0:
                pnl_streak += 1
            elif p < 0:
                pnl_streak -= 1
    except Exception:
        pnl_streak = 0

    drawdown = _safe(getattr(risk_state, "daily_max_drawdown", 0.0), 0.0)
    vol_regime = _regime_bucket(market_data.get("primary_regime") or market_data.get("regime"))
    hour = int(market_data.get("hour") or 12)
    time_bucket = _time_bucket(hour)
    shock_score = _safe(market_data.get("shock_score"), 0.0)
    uncertainty = _safe(market_data.get("uncertainty_index"), 0.0)

    exp = _portfolio_exposure(portfolio.get("trades", []), last_md_by_symbol)
    cap = float(portfolio.get("capital", cfg.CAPITAL))
    delta_pct = abs(exp["delta"]) * _safe(market_data.get("ltp"), 0.0) / max(cap, 1.0)
    gamma_pct = abs(exp["gamma"]) * (_safe(market_data.get("ltp"), 0.0) ** 2) / max(cap, 1.0)
    vega_pct = abs(exp["vega"]) * _safe(market_data.get("ltp"), 0.0) * 0.01 / max(cap, 1.0)

    max_corr = 0.0
    for ot in portfolio.get("trades", []):
        max_corr = max(max_corr, _default_corr(getattr(trade, "symbol", ""), getattr(ot, "symbol", "")))

    return {
        "score": score,
        "regime_prob": prob_max,
        "fill_prob": fill_prob,
        "exec_q": exec_q,
        "pnl_streak": pnl_streak,
        "drawdown": drawdown,
        "vol_regime": vol_regime,
        "time_bucket": time_bucket,
        "shock_score": shock_score,
        "uncertainty": uncertainty,
        "delta_pct": delta_pct,
        "gamma_pct": gamma_pct,
        "vega_pct": vega_pct,
        "corr": max_corr,
    }


def discretize(features: Dict[str, Any]) -> Tuple:
    return (
        _bin(features["score"], [0.4, 0.6, 0.75, 0.9]),
        _bin(features["regime_prob"], [0.4, 0.6, 0.8]),
        _bin(features["fill_prob"], [0.5, 0.7, 0.9]),
        _bin(features["exec_q"], [0.5, 0.7, 0.85]),
        _bin(features["pnl_streak"], [-2, -1, 0, 1, 2]),
        _bin(features["drawdown"], [-0.05, -0.02, -0.01, 0.0]),
        int(features["vol_regime"]),
        int(features["time_bucket"]),
        _bin(features["shock_score"], [0.2, 0.4, 0.6, 0.8]),
        _bin(features["uncertainty"], [0.2, 0.4, 0.6, 0.8]),
        _bin(features["delta_pct"], [0.05, 0.1, 0.2]),
        _bin(features["gamma_pct"], [0.02, 0.05, 0.1]),
        _bin(features["vega_pct"], [0.02, 0.05, 0.1]),
        _bin(features["corr"], [0.3, 0.6, 0.85]),
    )


class SizeRLAgent:
    def __init__(self, model_path: str, epsilon: float = 0.05):
        self.model_path = Path(model_path)
        self.epsilon = epsilon
        self.q = {}  # state -> action_idx -> value
        self._load()

    def _load(self):
        if self.model_path.exists():
            try:
                self.q = json.loads(self.model_path.read_text())
            except Exception:
                self.q = {}

    def save(self):
        self.model_path.parent.mkdir(exist_ok=True)
        self.model_path.write_text(json.dumps(self.q))

    def _state_key(self, state: Tuple) -> str:
        return ",".join(map(str, state))

    def select_multiplier(self, features: Dict[str, Any], explore: bool = False) -> float:
        state = discretize(features)
        key = self._state_key(state)
        if explore and random.random() < self.epsilon:
            return random.choice(ACTIONS)
        if key not in self.q:
            return 1.0
        vals = self.q[key]
        # vals is list aligned to ACTIONS
        best = max(range(len(ACTIONS)), key=lambda i: vals[i])
        return ACTIONS[best]

    def update(self, state: Tuple, action_idx: int, reward: float, next_state: Tuple, alpha=0.1, gamma=0.9):
        key = self._state_key(state)
        nkey = self._state_key(next_state)
        if key not in self.q:
            self.q[key] = [0.0 for _ in ACTIONS]
        if nkey not in self.q:
            self.q[nkey] = [0.0 for _ in ACTIONS]
        qsa = self.q[key][action_idx]
        qnext = max(self.q[nkey])
        self.q[key][action_idx] = qsa + alpha * (reward + gamma * qnext - qsa)

    def action_index(self, multiplier: float) -> int:
        if multiplier in ACTIONS:
            return ACTIONS.index(multiplier)
        # closest
        return int(min(range(len(ACTIONS)), key=lambda i: abs(ACTIONS[i] - multiplier)))
