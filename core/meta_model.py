import json
import time
from pathlib import Path

from config import config as cfg


def _family_from_strategy(strategy_name: str | None) -> str:
    if not strategy_name:
        return "OTHER"
    name = str(strategy_name).upper()
    if "TREND" in name or "ORB" in name:
        return "TREND"
    if "MEAN" in name or "REVERT" in name or "RANGE" in name:
        return "MEAN_REVERT"
    if "SPREAD" in name or "CONDOR" in name or "FLY" in name:
        return "DEFINED_RISK"
    if "SCALP" in name:
        return "SCALP"
    return "OTHER"


class MetaModel:
    def __init__(self, log_path: str | None = None):
        self.log_path = Path(log_path or getattr(cfg, "META_SHADOW_LOG_PATH", "logs/meta_shadow.jsonl"))

    def suggest(self, strategy_name, model_type, market_data, strategy_stats: dict | None = None) -> dict:
        strategy_stats = strategy_stats or {}
        family = _family_from_strategy(strategy_name)
        regime_probs = market_data.get("regime_probs") or {}
        primary_regime = (market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL").upper()
        exec_q = strategy_stats.get("exec_quality_avg")
        decay_prob = strategy_stats.get("decay_probability")

        baseline_weight = 1.0
        weight = 1.0
        if regime_probs:
            prob = float(regime_probs.get(primary_regime, 0.0))
            weight *= max(0.7, min(1.3, 0.8 + prob))
        if family in ("TREND", "MEAN_REVERT", "DEFINED_RISK"):
            if family == "TREND" and primary_regime == "TREND":
                weight *= 1.1
            if family == "MEAN_REVERT" and primary_regime in ("RANGE", "RANGE_VOLATILE"):
                weight *= 1.1
            if family == "DEFINED_RISK" and primary_regime == "EVENT":
                weight *= 1.1
            if family != "DEFINED_RISK" and primary_regime == "EVENT":
                weight *= 0.7
        if exec_q is not None:
            try:
                if float(exec_q) < float(getattr(cfg, "META_EXECQ_MIN", 55)):
                    weight *= 0.7
            except Exception:
                pass
        if decay_prob is not None:
            try:
                if float(decay_prob) >= float(getattr(cfg, "META_DECAY_PENALTY_THRESHOLD", 0.6)):
                    weight *= float(getattr(cfg, "META_DECAY_PENALTY_MULT", 0.7))
            except Exception:
                pass

        # Predictor preference suggestion
        baseline_predictor = model_type or "xgb"
        suggested_predictor = baseline_predictor
        if primary_regime == "TREND":
            suggested_predictor = "deep" if getattr(cfg, "USE_DEEP_MODEL", False) else "xgb"
        elif primary_regime in ("RANGE", "RANGE_VOLATILE"):
            suggested_predictor = "xgb"
        elif primary_regime == "EVENT":
            suggested_predictor = "xgb"
        if exec_q is not None:
            try:
                if float(exec_q) < float(getattr(cfg, "META_EXECQ_MIN", 55)):
                    suggested_predictor = "xgb"
            except Exception:
                pass

        return {
            "family": family,
            "primary_regime": primary_regime,
            "baseline_weight": baseline_weight,
            "suggested_weight": float(weight),
            "baseline_predictor": baseline_predictor,
            "suggested_predictor": suggested_predictor,
            "decay_prob": decay_prob,
            "exec_quality": exec_q,
            "regime_probs": regime_probs,
        }

    def log_shadow(self, payload: dict) -> None:
        try:
            self.log_path.parent.mkdir(exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception:
            pass
