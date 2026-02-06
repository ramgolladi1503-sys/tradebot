from dataclasses import dataclass
from config import config as cfg


@dataclass
class GateResult:
    allowed: bool
    family: str | None
    reasons: list


class StrategyGatekeeper:
    """
    Hard regime gating:
      TREND -> only trend strategies
      RANGE -> only mean reversion
      EVENT -> defined-risk only or NO TRADE
      NEUTRAL -> NO TRADE
    """
    def evaluate(self, market_data, mode="MAIN") -> GateResult:
        reasons = []
        regime_probs = market_data.get("regime_probs") or {}
        regime_entropy = market_data.get("regime_entropy", 0.0) or 0.0
        unstable = bool(market_data.get("unstable_regime_flag", False))
        regime = (market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL").upper()
        indicators_ok = market_data.get("indicators_ok", True)
        indicators_age = market_data.get("indicators_age_sec")
        if indicators_age is None:
            indicators_age = 0
        stale = indicators_age > getattr(cfg, "INDICATOR_STALE_SEC", 120)
        if not indicators_ok or stale:
            reasons.append("indicators_missing_or_stale")
            return GateResult(False, None, reasons)
        # cross-asset data quality gating
        try:
            if market_data.get("cross_asset_quality", {}).get("any_stale"):
                reasons.append("cross_asset_stale")
                return GateResult(False, None, reasons)
        except Exception:
            pass

        shock_score = float(market_data.get("shock_score") or 0.0)
        uncertainty = float(market_data.get("uncertainty_index") or 0.0)
        if shock_score >= getattr(cfg, "NEWS_SHOCK_BLOCK_THRESHOLD", 0.7):
            reasons.append("news_shock_block")
            return GateResult(False, None, reasons)
        if shock_score >= getattr(cfg, "NEWS_SHOCK_EVENT_THRESHOLD", 0.4) or uncertainty >= 0.8:
            if getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True):
                return GateResult(True, "DEFINED_RISK", reasons + ["news_shock_defined_risk_only"])
            reasons.append("news_shock_no_trade")
            return GateResult(False, None, reasons)

        if regime_probs:
            max_prob = max(regime_probs.values()) if regime_probs else 0.0
            if unstable or regime_entropy > getattr(cfg, "REGIME_ENTROPY_MAX", 1.3):
                reasons.append("regime_unstable")
                return GateResult(False, None, reasons)
            if max_prob < getattr(cfg, "REGIME_PROB_MIN", 0.45):
                reasons.append("regime_low_confidence")
                return GateResult(False, None, reasons)

        if regime == "TREND":
            return GateResult(True, "TREND", reasons)
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return GateResult(True, "MEAN_REVERT", reasons)
        if regime == "EVENT":
            if getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True):
                return GateResult(True, "DEFINED_RISK", reasons + ["event_defined_risk_only"])
            reasons.append("event_no_trade")
            return GateResult(False, None, reasons)
        if regime == "NEUTRAL":
            reasons.append("neutral_no_trade")
            return GateResult(False, None, reasons)

        # default: block unknown regimes
        reasons.append(f"unsupported_regime:{regime}")
        return GateResult(False, None, reasons)
