import math
from dataclasses import dataclass

from config import config as cfg


@dataclass
class PositionSizingResult:
    qty: int
    reason: str
    risk_budget: float
    stop_distance_rupees: float
    effective_stop_distance: float
    base_qty: int = 0
    confidence_multiplier: float = 1.0


class PositionSizer:
    def __init__(self):
        self.risk_per_trade_pct = float(getattr(cfg, "RISK_PER_TRADE_PCT", getattr(cfg, "MAX_RISK_PER_TRADE_PCT", 0.004)))
        self.min_qty = int(getattr(cfg, "MIN_QTY", 1))
        self.max_qty = int(getattr(cfg, "MAX_QTY", 100))
        self.max_slippage_bps_assumed = float(getattr(cfg, "MAX_SLIPPAGE_BPS_ASSUMED", 10.0))
        self.ml_min_proba = float(getattr(cfg, "ML_MIN_PROBA", 0.45))
        self.ml_full_size_proba = float(getattr(cfg, "ML_FULL_SIZE_PROBA", 0.70))
        self.confidence_min = float(getattr(cfg, "CONFIDENCE_MIN", 0.55))
        self.confidence_full = float(getattr(cfg, "CONFIDENCE_FULL", 0.80))

    def regime_multiplier(self, regime: str) -> float:
        regime_u = str(regime or "NEUTRAL").upper()
        if regime_u == "EVENT":
            return float(getattr(cfg, "REGIME_EVENT_SIZE_MULT", 0.6))
        if regime_u == "TREND":
            return float(getattr(cfg, "REGIME_TREND_SIZE_MULT", 1.0))
        if regime_u in ("RANGE", "RANGE_VOLATILE"):
            return float(getattr(cfg, "REGIME_RANGE_SIZE_MULT", 1.0))
        return 1.0

    def size_from_budget(
        self,
        risk_budget: float,
        stop_distance_rupees: float | None,
        *,
        multiplier: float = 1.0,
        ml_proba: float | None = None,
        confluence_score: float | None = None,
    ) -> PositionSizingResult:
        try:
            budget = float(risk_budget) * float(multiplier)
        except (TypeError, ValueError):
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:INVALID_RISK_BUDGET",
                risk_budget=0.0,
                stop_distance_rupees=float(stop_distance_rupees or 0.0),
                effective_stop_distance=float(stop_distance_rupees or 0.0),
                confidence_multiplier=1.0,
            )
        if budget <= 0:
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:NON_POSITIVE_RISK_BUDGET",
                risk_budget=budget,
                stop_distance_rupees=float(stop_distance_rupees or 0.0),
                effective_stop_distance=float(stop_distance_rupees or 0.0),
                confidence_multiplier=1.0,
            )
        if stop_distance_rupees is None:
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:INVALID_STOP_DISTANCE",
                risk_budget=budget,
                stop_distance_rupees=0.0,
                effective_stop_distance=0.0,
                confidence_multiplier=1.0,
            )
        try:
            stop_distance = float(stop_distance_rupees)
        except (TypeError, ValueError):
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:INVALID_STOP_DISTANCE",
                risk_budget=budget,
                stop_distance_rupees=0.0,
                effective_stop_distance=0.0,
                confidence_multiplier=1.0,
            )
        if stop_distance <= 0:
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:INVALID_STOP_DISTANCE",
                risk_budget=budget,
                stop_distance_rupees=stop_distance,
                effective_stop_distance=stop_distance,
                confidence_multiplier=1.0,
            )
        conf_ok, conf_mult, conf_reason = self.confidence_multiplier(ml_proba, confluence_score)
        if not conf_ok:
            return PositionSizingResult(
                qty=0,
                reason=conf_reason,
                risk_budget=budget,
                stop_distance_rupees=stop_distance,
                effective_stop_distance=stop_distance,
                confidence_multiplier=conf_mult,
            )
        budget *= conf_mult
        slippage_mult = 1.0 + max(self.max_slippage_bps_assumed, 0.0) / 10000.0
        effective_stop_distance = stop_distance * slippage_mult
        raw_qty = math.floor(budget / effective_stop_distance)
        base_qty = raw_qty
        if base_qty <= 0:
            return PositionSizingResult(
                qty=0,
                reason="SIZING_BLOCK:RISK_BUDGET_TOO_SMALL",
                risk_budget=budget,
                stop_distance_rupees=stop_distance,
                effective_stop_distance=effective_stop_distance,
                base_qty=base_qty,
                confidence_multiplier=conf_mult,
            )
        qty = max(self.min_qty, base_qty)
        qty = min(qty, self.max_qty)
        return PositionSizingResult(
            qty=int(qty),
            reason="OK",
            risk_budget=budget,
            stop_distance_rupees=stop_distance,
            effective_stop_distance=effective_stop_distance,
            base_qty=int(base_qty),
            confidence_multiplier=conf_mult,
        )

    def confidence_multiplier(self, ml_proba: float | None, confluence_score: float | None) -> tuple[bool, float, str]:
        """
        Deterministic confidence gate + multiplier.
        Returns (ok, multiplier, reason_code).
        """
        # Backward-compatible: if unavailable, do not block.
        if ml_proba is None and confluence_score is None:
            return True, 1.0, "OK"
        try:
            p = float(ml_proba) if ml_proba is not None else 1.0
            c = float(confluence_score) if confluence_score is not None else 1.0
        except (TypeError, ValueError):
            return False, 0.0, "SIZING_BLOCK:LOW_CONFIDENCE"
        p = max(0.0, min(1.0, p))
        c = max(0.0, min(1.0, c))

        min_p = max(0.0, min(1.0, self.ml_min_proba))
        full_p = max(min_p, min(1.0, self.ml_full_size_proba))
        min_c = max(0.0, min(1.0, self.confidence_min))
        full_c = max(min_c, min(1.0, self.confidence_full))

        if p < min_p or c < min_c:
            return False, 0.0, "SIZING_BLOCK:LOW_CONFIDENCE"
        if p >= full_p and c >= full_c:
            return True, 1.0, "OK"

        p_span = max(full_p - min_p, 1e-9)
        c_span = max(full_c - min_c, 1e-9)
        p_scaled = max(0.0, min(1.0, (p - min_p) / p_span))
        c_scaled = max(0.0, min(1.0, (c - min_c) / c_span))
        multiplier = max(0.0, min(1.0, (p_scaled + c_scaled) / 2.0))
        if multiplier <= 0:
            return False, 0.0, "SIZING_BLOCK:LOW_CONFIDENCE"
        return True, multiplier, "OK"
