from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional

import joblib

from config import config as cfg


def _safe_float(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _entropy(probs: Dict[str, float]) -> float:
    if not probs:
        return 1.0
    vals = [max(0.0, float(v)) for v in probs.values()]
    s = sum(vals)
    if s <= 0:
        return 1.0
    ent = 0.0
    for v in vals:
        p = v / s
        if p > 0:
            ent -= p * math.log(p + 1e-12)
    # Normalize by max entropy
    return _clamp(ent / max(1e-12, math.log(len(vals))))


def _logit(p: float) -> float:
    p = _clamp(p, 1e-6, 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class AlphaEnsemble:
    """
    Combines multiple model confidences + regime/news/cross-asset context into
    a final trade probability and uncertainty estimate.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or getattr(cfg, "ALPHA_STACKING_MODEL_PATH", "")
        self.meta_model = None
        if self.model_path:
            try:
                path = Path(self.model_path)
                if path.exists():
                    self.meta_model = joblib.load(path)
            except Exception:
                self.meta_model = None

    def _features(
        self,
        xgb_conf: Optional[float],
        deep_conf: Optional[float],
        micro_conf: Optional[float],
        regime_probs: Optional[Dict[str, float]],
        shock_score: Optional[float],
        cross: Optional[Dict[str, float]],
    ):
        reg = regime_probs or {}
        cross = cross or {}
        feat = {
            "xgb": _safe_float(xgb_conf, 0.5),
            "deep": _safe_float(deep_conf, 0.5),
            "micro": _safe_float(micro_conf, 0.5),
            "reg_trend": _safe_float(reg.get("TREND"), 0.0),
            "reg_range": max(_safe_float(reg.get("RANGE"), 0.0), _safe_float(reg.get("RANGE_VOLATILE"), 0.0)),
            "reg_event": _safe_float(reg.get("EVENT"), 0.0),
            "reg_panic": _safe_float(reg.get("PANIC"), 0.0),
            "shock_score": _safe_float(shock_score, 0.0),
            "x_regime_align": _safe_float(cross.get("x_regime_align"), 0.0),
            "x_vol_spillover": _safe_float(cross.get("x_vol_spillover"), 0.0),
            "x_lead_lag": _safe_float(cross.get("x_lead_lag"), 0.0),
        }
        return feat

    def _stacking(self, features: Dict[str, float]) -> Optional[float]:
        if not self.meta_model:
            return None
        try:
            cols = list(features.keys())
            X = [[features[c] for c in cols]]
            if hasattr(self.meta_model, "predict_proba"):
                return float(self.meta_model.predict_proba(X)[0][1])
            if hasattr(self.meta_model, "predict"):
                # Treat output as probability-like score
                return float(self.meta_model.predict(X)[0])
        except Exception:
            return None
        return None

    def _dynamic_weights(self, regime_probs: Dict[str, float] | None):
        base = getattr(cfg, "ALPHA_BASE_WEIGHTS", {"xgb": 0.45, "deep": 0.35, "micro": 0.2})
        reg_weights = getattr(cfg, "ALPHA_REGIME_WEIGHTS", {})
        if not regime_probs:
            return base
        # Choose most probable regime
        primary = max(regime_probs.items(), key=lambda kv: kv[1])[0] if regime_probs else None
        if primary and primary in reg_weights:
            w = reg_weights[primary]
            return {
                "xgb": _safe_float(w.get("xgb"), base.get("xgb", 0.45)),
                "deep": _safe_float(w.get("deep"), base.get("deep", 0.35)),
                "micro": _safe_float(w.get("micro"), base.get("micro", 0.2)),
            }
        return base

    def _bayesian_average(self, confs: Dict[str, float], weights: Dict[str, float]) -> float:
        # Weighted log-odds averaging
        num = 0.0
        den = 0.0
        for k, p in confs.items():
            if p is None:
                continue
            w = float(weights.get(k, 0.0))
            num += w * _logit(float(p))
            den += w
        if den <= 0:
            return 0.5
        return _sigmoid(num / den)

    def _uncertainty(
        self,
        confs: Dict[str, float],
        regime_probs: Optional[Dict[str, float]],
        shock_score: Optional[float],
        cross: Optional[Dict[str, float]],
    ) -> float:
        vals = [v for v in confs.values() if v is not None]
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            disagreement = math.sqrt(var) / 0.25
        else:
            disagreement = 0.5
        disagreement = _clamp(disagreement)

        reg_entropy = _entropy(regime_probs or {})
        shock = _clamp(_safe_float(shock_score, 0.0))

        cross = cross or {}
        volspill = _safe_float(cross.get("x_vol_spillover"), 0.0)
        volspill = _clamp(abs(volspill) / 2.0)

        w_dis = getattr(cfg, "ALPHA_UNCERT_W_DISAGREE", 0.45)
        w_reg = getattr(cfg, "ALPHA_UNCERT_W_REGIME", 0.25)
        w_shk = getattr(cfg, "ALPHA_UNCERT_W_SHOCK", 0.20)
        w_vol = getattr(cfg, "ALPHA_UNCERT_W_VOLSPILL", 0.10)
        return _clamp(w_dis * disagreement + w_reg * reg_entropy + w_shk * shock + w_vol * volspill)

    def combine(
        self,
        xgb_conf: Optional[float],
        deep_conf: Optional[float],
        micro_conf: Optional[float],
        regime_probs: Optional[Dict[str, float]],
        shock_score: Optional[float],
        cross: Optional[Dict[str, float]] = None,
    ):
        confs = {
            "xgb": _safe_float(xgb_conf, None),
            "deep": _safe_float(deep_conf, None),
            "micro": _safe_float(micro_conf, None),
        }
        features = self._features(xgb_conf, deep_conf, micro_conf, regime_probs, shock_score, cross)

        method = getattr(cfg, "ALPHA_METHOD", "AUTO").upper()
        final_prob = None
        if method in ("STACKING", "AUTO"):
            final_prob = self._stacking(features)
        if final_prob is None:
            weights = self._dynamic_weights(regime_probs)
            final_prob = self._bayesian_average(confs, weights)
        uncertainty = self._uncertainty(confs, regime_probs, shock_score, cross)

        # Size multiplier based on uncertainty
        down_th = getattr(cfg, "ALPHA_UNCERTAINTY_DOWNSIZE", 0.55)
        min_mult = getattr(cfg, "ALPHA_UNCERTAINTY_MIN_SIZE_MULT", 0.5)
        if uncertainty <= down_th:
            size_mult = 1.0
        else:
            # Linear downscale from down_th to 1.0 uncertainty
            size_mult = max(min_mult, 1.0 - (uncertainty - down_th) / max(1e-6, (1.0 - down_th)))

        return {
            "final_prob": float(final_prob),
            "uncertainty": float(uncertainty),
            "method": method,
            "size_mult": float(size_mult),
            "features": features,
        }

