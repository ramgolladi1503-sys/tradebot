from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Tuple, List

from config import config as cfg
from core.greeks import greeks as calc_greeks


@dataclass
class AllocationResult:
    allowed: bool
    max_qty: int
    reason: str | None
    report: Dict[str, Any]


def _parse_expiry(expiry: str | None) -> datetime | None:
    if not expiry:
        return None
    try:
        return datetime.fromisoformat(expiry)
    except Exception:
        try:
            return datetime.strptime(expiry, "%Y-%m-%d")
        except Exception:
            return None


def _default_corr(sym1: str, sym2: str) -> float:
    if sym1 == sym2:
        return 1.0
    pair = tuple(sorted([sym1, sym2]))
    corr_map = getattr(cfg, "SYMBOL_CORRELATIONS", {})
    return float(corr_map.get(pair, 0.85))


def _corr_by_symbol_expiry(sym1: str, exp1: str | None, sym2: str, exp2: str | None) -> float:
    if sym1 == sym2:
        return 1.0 if exp1 == exp2 else 0.95
    return _default_corr(sym1, sym2)


def _exposure_for_trade(trade, spot: float | None, iv: float | None, lot_size: int) -> Dict[str, float]:
    side = (getattr(trade, "side", "BUY") or "BUY").upper()
    sign = 1.0 if side == "BUY" else -1.0
    instrument = (getattr(trade, "instrument", "OPT") or "OPT").upper()
    if instrument in ("FUT", "EQ"):
        return {"delta": sign * 1.0 * lot_size, "gamma": 0.0, "vega": 0.0}

    strike = float(getattr(trade, "strike", 0) or 0)
    expiry = _parse_expiry(getattr(trade, "expiry", None))
    t = 7 / 365
    if expiry:
        t_days = max((expiry.date() - datetime.now().date()).days, 1)
        t = t_days / 365
    vol = iv or float(getattr(trade, "iv", 0.0) or 0.3)
    is_call = str(getattr(trade, "type", "CE")).upper().startswith("C")
    if not spot or spot <= 0 or strike <= 0:
        # fallback to coarse estimates
        delta = 0.5 if is_call else -0.5
        return {"delta": sign * delta * lot_size, "gamma": 0.0, "vega": 0.0}
    g = calc_greeks(spot, strike, t, vol, is_call=is_call)
    return {
        "delta": sign * g["delta"] * lot_size,
        "gamma": sign * g["gamma"] * lot_size,
        "vega": sign * g["vega"] * lot_size,
    }


class PortfolioRiskAllocator:
    def __init__(self):
        self.enabled = getattr(cfg, "PORTFOLIO_ALLOCATOR_ENABLE", True)

    def allocate(
        self,
        trade,
        portfolio: Dict[str, Any],
        market_data: Dict[str, Any],
        last_md_by_symbol: Dict[str, Dict[str, Any]] | None = None,
    ) -> AllocationResult:
        if not self.enabled:
            return AllocationResult(True, int(getattr(trade, "qty", 1) or 1), None, {})

        capital = float(portfolio.get("capital", cfg.CAPITAL))
        lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1))
        spot = float(market_data.get("ltp") or 0)
        iv = float(market_data.get("iv") or 0) if market_data.get("iv") is not None else None

        # Current exposures from open trades
        current = {"delta": 0.0, "gamma": 0.0, "vega": 0.0}
        open_trades = portfolio.get("trades", [])
        for ot in open_trades:
            sym = getattr(ot, "symbol", None)
            md = (last_md_by_symbol or {}).get(sym, {})
            o_spot = float(md.get("ltp") or spot or 0)
            o_iv = float(md.get("iv") or 0) if md.get("iv") is not None else None
            exp = _exposure_for_trade(ot, o_spot, o_iv, int(getattr(cfg, "LOT_SIZE", {}).get(sym, 1)))
            current["delta"] += exp["delta"] * int(getattr(ot, "qty", 1) or 1)
            current["gamma"] += exp["gamma"] * int(getattr(ot, "qty", 1) or 1)
            current["vega"] += exp["vega"] * int(getattr(ot, "qty", 1) or 1)

        # Exposure per 1 lot of this trade
        per_lot = _exposure_for_trade(trade, spot, iv, lot_size)

        # Regime-aware limits
        regime = (market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL").upper()
        base_limits = {
            "delta": getattr(cfg, "PORTFOLIO_MAX_DELTA_PCT", 0.25),
            "gamma": getattr(cfg, "PORTFOLIO_MAX_GAMMA_PCT", 0.10),
            "vega": getattr(cfg, "PORTFOLIO_MAX_VEGA_PCT", 0.12),
        }
        mults = getattr(cfg, "REGIME_EXPOSURE_MULT", {}).get(regime, {"delta": 1.0, "gamma": 1.0, "vega": 1.0})
        max_delta = base_limits["delta"] * mults.get("delta", 1.0) * capital
        max_gamma = base_limits["gamma"] * mults.get("gamma", 1.0) * capital
        max_vega = base_limits["vega"] * mults.get("vega", 1.0) * capital

        # Correlation penalty
        max_corr = 0.0
        for ot in open_trades:
            max_corr = max(max_corr, _corr_by_symbol_expiry(trade.symbol, trade.expiry, ot.symbol, ot.expiry))
        corr_pen = getattr(cfg, "CORR_PENALTY", 0.2)
        max_delta *= (1.0 - max_corr * corr_pen)

        # Convert exposures to notional terms
        delta_notional = abs(current["delta"] + per_lot["delta"]) * spot
        gamma_notional = abs(current["gamma"] + per_lot["gamma"]) * (spot ** 2)
        vega_notional = abs(current["vega"] + per_lot["vega"]) * spot * 0.01

        # Determine max_qty by each exposure
        def _max_qty_for(limit_notional, current_exp, per_lot_exp, scale):
            if per_lot_exp == 0:
                return 999
            headroom = max(0.0, limit_notional - abs(current_exp) * scale)
            return int(headroom / (abs(per_lot_exp) * scale)) if headroom > 0 else 0

        max_qty_delta = _max_qty_for(max_delta, current["delta"], per_lot["delta"], spot)
        max_qty_gamma = _max_qty_for(max_gamma, current["gamma"], per_lot["gamma"], spot ** 2)
        max_qty_vega = _max_qty_for(max_vega, current["vega"], per_lot["vega"], spot * 0.01)

        max_qty = min(max_qty_delta, max_qty_gamma, max_qty_vega)

        # Rolling stress tests
        stress_move = float(getattr(cfg, "STRESS_MOVE_PCT", 0.02))
        stress_vol = float(getattr(cfg, "STRESS_VOL_PCT", 0.3))
        def _stress_pnl(delta_exp, gamma_exp, vega_exp, move, vol):
            pnl = (delta_exp * spot * move) + 0.5 * gamma_exp * (spot ** 2) * (move ** 2) + vega_exp * vol
            return pnl

        # portfolio + proposed 1-lot
        total_delta = current["delta"] + per_lot["delta"]
        total_gamma = current["gamma"] + per_lot["gamma"]
        total_vega = current["vega"] + per_lot["vega"]

        loss_up = _stress_pnl(total_delta, total_gamma, total_vega, +stress_move, stress_vol)
        loss_down = _stress_pnl(total_delta, total_gamma, total_vega, -stress_move, stress_vol)
        worst_loss = min(loss_up, loss_down)
        max_stress_loss = -abs(getattr(cfg, "MAX_STRESS_LOSS_PCT", 0.03)) * capital
        if worst_loss < max_stress_loss:
            return AllocationResult(False, 0, "stress_loss_exceeded", {"worst_loss": worst_loss, "max_stress_loss": max_stress_loss})

        if max_qty <= 0:
            return AllocationResult(False, 0, "portfolio_exposure_limit", {
                "max_qty_delta": max_qty_delta,
                "max_qty_gamma": max_qty_gamma,
                "max_qty_vega": max_qty_vega,
            })

        report = {
            "current_exposure": current,
            "per_lot_exposure": per_lot,
            "max_qty_delta": max_qty_delta,
            "max_qty_gamma": max_qty_gamma,
            "max_qty_vega": max_qty_vega,
            "regime": regime,
            "max_corr": max_corr,
            "stress_loss": worst_loss,
        }
        return AllocationResult(True, max_qty, None, report)
