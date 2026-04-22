from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import config as cfg
from core.position_sizer import PositionSizer


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class PaperRiskDecision:
    allowed: bool
    qty: int
    risk_budget: float
    stop_loss: float | None
    target: float | None
    reason: str
    metadata: dict[str, Any]


class PaperRiskSizingEngine:
    def __init__(self) -> None:
        self.position_sizer = PositionSizer()
        self.capital = float(getattr(cfg, "CAPITAL", 100000) or 100000)
        self.max_open_positions = int(getattr(cfg, "MAX_POSITIONS_PER_UNDERLYING", 3) or 3)
        self.max_underlying_exposure_pct = float(getattr(cfg, "MAX_UNDERLYING_EXPOSURE_PCT", 0.40) or 0.40)
        self.max_open_risk_pct = float(getattr(cfg, "MAX_OPEN_RISK_PCT", 0.02) or 0.02)

    def evaluate_candidate(
        self,
        candidate: dict[str, Any],
        *,
        portfolio_snapshot: dict[str, Any] | None = None,
    ) -> PaperRiskDecision:
        portfolio_snapshot = dict(portfolio_snapshot or {})
        symbol = str(candidate.get("symbol") or candidate.get("underlying") or "UNKNOWN").strip().upper()
        entry_price = _safe_float(candidate.get("entry_price") or candidate.get("display_entry") or candidate.get("opt_ltp"))
        if entry_price is None or entry_price <= 0:
            return PaperRiskDecision(False, 0, 0.0, None, None, "invalid_entry_price", {"symbol": symbol})

        confidence = max(
            float(_safe_float(candidate.get("confidence")) or 0.0),
            float(_safe_float(candidate.get("rank_score")) or 0.0),
            float(_safe_float(candidate.get("gating_final_confidence")) or 0.0),
        )
        stop_loss = self._derive_stop_loss(candidate, entry_price)
        target = self._derive_target(candidate, entry_price, stop_loss)
        if stop_loss is None or stop_loss >= entry_price:
            return PaperRiskDecision(False, 0, 0.0, stop_loss, target, "invalid_stop_loss", {"symbol": symbol})
        stop_distance = entry_price - stop_loss

        open_positions = list(portfolio_snapshot.get("open_positions") or [])
        same_symbol_open = [row for row in open_positions if str(row.get("symbol") or "").strip().upper() == symbol]
        if len(same_symbol_open) >= self.max_open_positions:
            return PaperRiskDecision(False, 0, 0.0, stop_loss, target, "max_positions_per_underlying", {"symbol": symbol, "open_positions": len(same_symbol_open)})

        current_symbol_exposure = sum(
            max(0.0, float(_safe_float(row.get("entry_price")) or 0.0) * float(_safe_float(row.get("qty")) or 0.0))
            for row in same_symbol_open
        )
        max_symbol_exposure = self.capital * self.max_underlying_exposure_pct
        if current_symbol_exposure >= max_symbol_exposure:
            return PaperRiskDecision(False, 0, 0.0, stop_loss, target, "underlying_exposure_limit", {"symbol": symbol, "current_exposure": current_symbol_exposure, "max_exposure": max_symbol_exposure})

        current_open_risk = sum(
            max(0.0, (float(_safe_float(row.get("entry_price")) or 0.0) - float(_safe_float(row.get("stop_loss")) or 0.0)) * float(_safe_float(row.get("qty")) or 0.0))
            for row in open_positions
        )
        max_open_risk_rupees = self.capital * self.max_open_risk_pct
        if current_open_risk >= max_open_risk_rupees:
            return PaperRiskDecision(False, 0, 0.0, stop_loss, target, "portfolio_open_risk_limit", {"current_open_risk": current_open_risk, "max_open_risk": max_open_risk_rupees})

        remaining_open_risk = max(0.0, max_open_risk_rupees - current_open_risk)
        risk_budget = min(self.capital * float(getattr(cfg, "MAX_RISK_PER_TRADE_PCT", 0.004) or 0.004), remaining_open_risk)
        sizing = self.position_sizer.size_from_budget(
            risk_budget,
            stop_distance,
            multiplier=self.position_sizer.regime_multiplier(str(candidate.get("regime") or "NEUTRAL")),
            ml_proba=confidence,
            confluence_score=max(confidence, float(_safe_float(candidate.get("builder_confidence")) or 0.0)),
        )
        if sizing.qty <= 0:
            return PaperRiskDecision(False, 0, float(sizing.risk_budget), stop_loss, target, sizing.reason, {"symbol": symbol, "sizing_reason": sizing.reason, "confidence_multiplier": sizing.confidence_multiplier})

        allowed_qty = sizing.qty
        symbol_headroom_qty = int(max(0.0, (max_symbol_exposure - current_symbol_exposure) / max(entry_price, 1e-6)))
        if symbol_headroom_qty <= 0:
            return PaperRiskDecision(False, 0, float(sizing.risk_budget), stop_loss, target, "underlying_cap_no_headroom", {"symbol": symbol})
        allowed_qty = min(allowed_qty, symbol_headroom_qty)
        if allowed_qty <= 0:
            return PaperRiskDecision(False, 0, float(sizing.risk_budget), stop_loss, target, "no_qty_after_caps", {"symbol": symbol})

        return PaperRiskDecision(
            True,
            int(allowed_qty),
            float(sizing.risk_budget),
            float(stop_loss),
            float(target) if target is not None else None,
            "OK",
            {
                "symbol": symbol,
                "entry_price": entry_price,
                "stop_distance": stop_distance,
                "confidence": confidence,
                "base_qty": int(sizing.base_qty),
                "confidence_multiplier": float(sizing.confidence_multiplier),
                "effective_stop_distance": float(sizing.effective_stop_distance),
                "current_open_risk": current_open_risk,
                "remaining_open_risk": remaining_open_risk,
            },
        )

    def _derive_stop_loss(self, candidate: dict[str, Any], entry_price: float) -> float | None:
        explicit = _safe_float(candidate.get("stop_loss"))
        if explicit is not None:
            return float(explicit)
        spread_pct = _safe_float(candidate.get("spread_pct")) or 1.0
        stop_pct = max(0.05, min(0.18, 0.08 + (spread_pct / 100.0)))
        return round(entry_price * (1.0 - stop_pct), 4)

    def _derive_target(self, candidate: dict[str, Any], entry_price: float, stop_loss: float | None) -> float | None:
        explicit = _safe_float(candidate.get("target"))
        if explicit is not None:
            return float(explicit)
        if stop_loss is None:
            return None
        risk_per_unit = max(0.0, entry_price - stop_loss)
        rr = 1.5
        return round(entry_price + (risk_per_unit * rr), 4)
