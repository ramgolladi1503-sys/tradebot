from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Any

import pandas as pd

from config import config as cfg
from core.risk_state import RiskState


@dataclass
class StressScenario:
    returns: List[float]
    price_path: List[float]
    fill_degradation: float
    spread_widen_pct: float
    iv_spike: float


class SyntheticStressGenerator:
    """
    Generates synthetic stress scenarios using:
    - block bootstrap of intraday returns
    - volatility scaling
    - jump diffusion
    - order-book thinning
    - spread widening
    - gap scenarios
    - IV spikes
    """
    def __init__(self,
                 block_size: int | None = None,
                 vol_scale: float | None = None,
                 jump_lambda: float | None = None,
                 jump_sigma: float | None = None,
                 gap_prob: float | None = None,
                 gap_sigma: float | None = None,
                 spread_widen_pct: float | None = None,
                 iv_spike: float | None = None,
                 ob_thin_factor: float | None = None):
        self.block_size = block_size or int(getattr(cfg, "STRESS_BLOCK_SIZE", 20))
        self.vol_scale = vol_scale or float(getattr(cfg, "STRESS_VOL_SCALE", 1.8))
        self.jump_lambda = jump_lambda or float(getattr(cfg, "STRESS_JUMP_LAMBDA", 0.03))
        self.jump_sigma = jump_sigma or float(getattr(cfg, "STRESS_JUMP_SIGMA", 0.03))
        self.gap_prob = gap_prob or float(getattr(cfg, "STRESS_GAP_PROB", 0.02))
        self.gap_sigma = gap_sigma or float(getattr(cfg, "STRESS_GAP_SIGMA", 0.05))
        self.spread_widen_pct = spread_widen_pct or float(getattr(cfg, "STRESS_SPREAD_WIDEN_PCT", 0.5))
        self.iv_spike = iv_spike or float(getattr(cfg, "STRESS_IV_SPIKE", 0.35))
        self.ob_thin_factor = ob_thin_factor or float(getattr(cfg, "STRESS_OB_THIN_FACTOR", 0.6))

    def _block_bootstrap(self, returns: List[float], n_steps: int) -> List[float]:
        if not returns:
            return [0.0] * n_steps
        out = []
        n = len(returns)
        while len(out) < n_steps:
            start = random.randint(0, max(0, n - self.block_size))
            block = returns[start:start + self.block_size]
            if not block:
                block = [returns[random.randint(0, n - 1)]]
            out.extend(block)
        return out[:n_steps]

    def _apply_vol_scale(self, returns: List[float]) -> List[float]:
        return [r * self.vol_scale for r in returns]

    def _apply_jumps(self, returns: List[float]) -> List[float]:
        out = []
        for r in returns:
            if random.random() < self.jump_lambda:
                jump = random.gauss(0, self.jump_sigma)
                out.append(r + jump)
            else:
                out.append(r)
        return out

    def _apply_gaps(self, returns: List[float]) -> List[float]:
        out = []
        for r in returns:
            if random.random() < self.gap_prob:
                gap = random.gauss(0, self.gap_sigma)
                out.append(r + gap)
            else:
                out.append(r)
        return out

    def _price_path(self, start_price: float, returns: List[float]) -> List[float]:
        price = start_price
        path = [price]
        for r in returns:
            price = max(0.01, price * (1 + r))
            path.append(price)
        return path

    def generate(self, returns: List[float], start_price: float, n_steps: int, n_paths: int) -> List[StressScenario]:
        scenarios = []
        for _ in range(n_paths):
            base = self._block_bootstrap(returns, n_steps)
            base = self._apply_vol_scale(base)
            base = self._apply_jumps(base)
            base = self._apply_gaps(base)
            path = self._price_path(start_price, base)
            fill_deg = max(0.0, 1.0 - self.ob_thin_factor)
            scenarios.append(StressScenario(
                returns=base,
                price_path=path,
                fill_degradation=fill_deg,
                spread_widen_pct=self.spread_widen_pct,
                iv_spike=self.iv_spike
            ))
        return scenarios

    def distort_chain(self, chain: List[dict], scenario: StressScenario) -> List[dict]:
        out = []
        for c in chain:
            bid = c.get("bid")
            ask = c.get("ask")
            if bid and ask:
                mid = (bid + ask) / 2
                widen = (ask - bid) * (1 + scenario.spread_widen_pct)
                bid = max(0.01, mid - widen / 2)
                ask = max(bid + 0.01, mid + widen / 2)
            iv = c.get("iv")
            if iv is not None:
                iv = iv * (1 + scenario.iv_spike)
            bid_qty = c.get("bid_qty")
            ask_qty = c.get("ask_qty")
            if bid_qty is not None:
                bid_qty = max(1, int(bid_qty * (1 - self.ob_thin_factor)))
            if ask_qty is not None:
                ask_qty = max(1, int(ask_qty * (1 - self.ob_thin_factor)))
            row = dict(c)
            row.update({"bid": bid, "ask": ask, "iv": iv, "bid_qty": bid_qty, "ask_qty": ask_qty})
            out.append(row)
        return out

    def fill_degradation(self, base_fill_prob: float, scenario: StressScenario) -> float:
        degraded = base_fill_prob * (1 - scenario.fill_degradation)
        degraded *= max(0.1, 1 - scenario.spread_widen_pct)
        return max(0.0, min(1.0, degraded))

    def run(self,
            returns: List[float],
            start_price: float,
            n_steps: int,
            n_paths: int,
            strategy_runner=None,
            rl_agent=None,
            risk_state_cls=RiskState) -> Dict[str, Any]:
        scenarios = self.generate(returns, start_price, n_steps, n_paths)
        pnl_paths = []
        kill_switch = 0
        survivals = []

        for sc in scenarios:
            rs = risk_state_cls(start_capital=float(getattr(cfg, "CAPITAL", 100000)))
            pnl = 0.0
            survived = True
            for i in range(1, len(sc.price_path)):
                step_ret = sc.returns[i - 1]
                if strategy_runner:
                    trades = strategy_runner(sc.price_path[i - 1], sc.price_path[i]) or []
                else:
                    trades = [{"side": "BUY", "qty": 1.0, "entry": sc.price_path[i - 1], "strategy": "SYNTH"}]
                for tr in trades:
                    side = tr.get("side", "BUY")
                    qty = tr.get("qty", 1.0)
                    entry = tr.get("entry", sc.price_path[i - 1])
                    mult = 1.0
                    if rl_agent:
                        try:
                            mult = rl_agent.select_multiplier({"score": 0.7, "regime_prob": 0.6}, explore=False)
                        except Exception:
                            mult = 1.0
                    sign = 1.0 if side == "BUY" else -1.0
                    step_pnl = sign * step_ret * entry * qty * mult
                    pnl += step_pnl
                    rs.record_realized_pnl(tr.get("strategy"), step_pnl)
                    ok, _ = rs.approve(type("T", (), tr))
                    if not ok:
                        kill_switch += 1
                        survived = False
                        break
                if not survived:
                    break
            pnl_paths.append(pnl)
            survivals.append(1 if survived else 0)

        if not pnl_paths:
            return {"status": "no_scenarios"}

        pnl_sorted = sorted(pnl_paths)
        k = max(1, int(len(pnl_sorted) * 0.05))
        cvar = sum(pnl_sorted[:k]) / k
        max_loss = min(pnl_sorted)
        survivability = sum(survivals) / len(survivals)
        kill_freq = kill_switch / max(1, n_paths)

        return {
            "max_loss": round(max_loss, 4),
            "tail_cvar": round(cvar, 4),
            "strategy_survivability": round(survivability, 4),
            "kill_switch_frequency": round(kill_freq, 4),
            "paths": len(pnl_paths),
        }


def _window_index(df: pd.DataFrame, duration: int) -> pd.Index:
    if duration <= 0 or df.empty:
        return df.index[:0]
    end = min(len(df), duration)
    return df.index[:end]


def spread_widen(df: pd.DataFrame, multiplier: float, duration: int) -> pd.DataFrame:
    """
    Widen spreads by a multiplier for a deterministic window.
    """
    out = df.copy()
    idx = _window_index(out, duration)
    if "spread_pct" in out:
        out.loc[idx, "spread_pct"] = out.loc[idx, "spread_pct"].astype(float) * float(multiplier)
    if "bid" in out and "ask" in out:
        bid = out.loc[idx, "bid"].astype(float)
        ask = out.loc[idx, "ask"].astype(float)
        mid = (bid + ask) / 2.0
        widen = (ask - bid) * float(multiplier)
        out.loc[idx, "bid"] = (mid - widen / 2.0).clip(lower=0.01)
        out.loc[idx, "ask"] = (mid + widen / 2.0).clip(lower=0.01)
    out.loc[idx, "stress_spread_widen"] = True
    return out


def depth_thin(df: pd.DataFrame, multiplier: float, duration: int) -> pd.DataFrame:
    """
    Thin depth by reducing bid/ask quantities.
    """
    out = df.copy()
    idx = _window_index(out, duration)
    for col in ("bid_qty", "ask_qty"):
        if col in out:
            out.loc[idx, col] = (out.loc[idx, col].astype(float) * float(multiplier)).clip(lower=0.0)
    out.loc[idx, "stress_depth_thin"] = True
    return out


def quote_stale_burst(df: pd.DataFrame, duration: int, max_age_sec: float) -> pd.DataFrame:
    """
    Force quote_age_sec to exceed max_age_sec for a window.
    """
    out = df.copy()
    idx = _window_index(out, duration)
    if "quote_age_sec" in out:
        out.loc[idx, "quote_age_sec"] = float(max_age_sec) + 1.0
    out.loc[idx, "stress_quote_stale"] = True
    return out


def gap_open(df: pd.DataFrame, size_pct: float, duration: int) -> pd.DataFrame:
    """
    Apply a gap move to bid/ask (and ltp if present).
    """
    out = df.copy()
    idx = _window_index(out, duration)
    mult = 1.0 + float(size_pct)
    for col in ("bid", "ask", "ltp"):
        if col in out:
            out.loc[idx, col] = out.loc[idx, col].astype(float) * mult
    out.loc[idx, "stress_gap_open"] = True
    return out


def iv_spike(df: pd.DataFrame, multiplier: float, duration: int) -> pd.DataFrame:
    """
    Spike IV columns where available.
    """
    out = df.copy()
    idx = _window_index(out, duration)
    for col in ("iv", "iv_mean", "iv_term"):
        if col in out:
            out.loc[idx, col] = out.loc[idx, col].astype(float) * float(multiplier)
    out.loc[idx, "stress_iv_spike"] = True
    return out


def regime_flip_storm(df: pd.DataFrame, flips_per_window: int, duration: int) -> pd.DataFrame:
    """
    Create rapid regime flips and high entropy.
    """
    out = df.copy()
    idx = _window_index(out, duration)
    if "regime_entropy" in out:
        out.loc[idx, "regime_entropy"] = out.loc[idx, "regime_entropy"].fillna(0).astype(float).clip(lower=0.0)
        out.loc[idx, "regime_entropy"] = out.loc[idx, "regime_entropy"].apply(lambda v: max(v, 2.0))
    if "unstable_regime_flag" in out:
        out.loc[idx, "unstable_regime_flag"] = True
    if "primary_regime" in out:
        regimes = ["TREND", "RANGE", "EVENT", "PANIC", "RANGE_VOLATILE"]
        for i, row_idx in enumerate(idx):
            out.at[row_idx, "primary_regime"] = regimes[(i * max(1, flips_per_window)) % len(regimes)]
    out.loc[idx, "stress_regime_flip"] = True
    return out
