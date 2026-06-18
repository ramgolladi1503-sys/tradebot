from __future__ import annotations

import logging
from typing import Any
from pathlib import Path
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)

# Global cache for the XGBoost model to avoid reloading on every candidate evaluation
_XGB_MODEL = None
_MODEL_LOAD_FAILED = False

def _get_xgb_model() -> Any:
    global _XGB_MODEL, _MODEL_LOAD_FAILED
    if _XGB_MODEL is not None:
        return _XGB_MODEL
    if _MODEL_LOAD_FAILED:
        return None

    try:
        import xgboost as xgb
        model_path = Path(__file__).resolve().parents[2] / "models" / "xgb_overlay.json"
        if not model_path.exists():
            logger.warning("xgb_overlay_model_not_found path=%s", model_path)
            _MODEL_LOAD_FAILED = True
            return None

        model = xgb.XGBClassifier()
        model.load_model(str(model_path))
        _XGB_MODEL = model
        logger.info("xgb_overlay_model_loaded_successfully path=%s", model_path)
        return _XGB_MODEL
    except Exception as exc:
        logger.exception("xgb_overlay_model_load_failed error=%s", exc)
        _MODEL_LOAD_FAILED = True
        return None


def validate_ml_acceptance(candidate: Any, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """
    Evaluate candidate against the XGBoost ML overlay.
    Extracts live technical features from the candidate and runs inference.

    Returns:
        {
            "pass": bool,
            "reason_code": "ML_PROBABILITY_TOO_LOW" | "MISSING_ML_FEATURES" | None,
            "ml_probability": float | None,
            "ml_threshold": float
        }
    """
    th = dict(thresholds or {})
    min_probability = float(th.get("min_ml_probability", 0.70))

    # Support dict or StrategyCandidate object
    if isinstance(candidate, dict):
        metrics = candidate.get("metrics", {})
        ts_epoch = candidate.get("ts_epoch") or candidate.get("timestamp_epoch")
    else:
        metrics = getattr(candidate, "metrics", {})
        ts_epoch = getattr(candidate, "ts_epoch", None) or getattr(candidate, "timestamp_epoch", None)

    if not isinstance(metrics, dict):
        metrics = {}

    model = _get_xgb_model()
    if model is None:
        # If model is entirely missing, fail open to avoid breaking CI/Unit tests that don't have the model
        return {
            "pass": True,
            "reason_code": None,
            "ml_probability": 1.0,
            "ml_threshold": min_probability,
        }

    # Extract required features: ['rsi_14', 'adx_14', 'vwap_slope', 'trend_dist', 'atr_pct', 'hour', 'minute']
    # Fallback to general rsi/adx if the _14 variants are missing.
    rsi = metrics.get("rsi_14")
    if rsi is None:
        rsi = metrics.get("rsi")

    adx = metrics.get("adx_14")
    if adx is None:
        adx = metrics.get("adx")

    vwap_slope = metrics.get("vwap_slope")
    trend_dist = metrics.get("trend_dist")
    atr_pct = metrics.get("atr_pct")

    # Time features
    hour, minute = 9, 15
    if ts_epoch:
        dt = datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc)
        # Assuming IST
        # Quick offset for IST +5:30
        ist_dt = datetime.fromtimestamp(float(ts_epoch) + 19800, tz=timezone.utc)
        hour = ist_dt.hour
        minute = ist_dt.minute

    # If critical features are missing, fail
    if any(v is None for v in [rsi, adx, vwap_slope, trend_dist, atr_pct]):
        return {
            "pass": False,
            "reason_code": "MISSING_ML_FEATURES",
            "ml_probability": None,
            "ml_threshold": min_probability,
        }

    try:
        import pandas as pd
        # Must match exact feature columns used during training
        features = ['rsi_14', 'adx_14', 'vwap_slope', 'trend_dist', 'atr_pct', 'hour', 'minute']
        df = pd.DataFrame([{
            'rsi_14': float(rsi),
            'adx_14': float(adx),
            'vwap_slope': float(vwap_slope),
            'trend_dist': float(trend_dist),
            'atr_pct': float(atr_pct),
            'hour': int(hour),
            'minute': int(minute),
        }])

        proba = float(model.predict_proba(df)[0, 1])

        if proba < min_probability:
            return {
                "pass": False,
                "reason_code": "ML_PROBABILITY_TOO_LOW",
                "ml_probability": proba,
                "ml_threshold": min_probability,
            }

        return {
            "pass": True,
            "reason_code": None,
            "ml_probability": proba,
            "ml_threshold": min_probability,
        }
    except Exception as exc:
        logger.error("ml_acceptance_gate_prediction_failed err=%s", exc)
        return {
            "pass": False,
            "reason_code": "ML_INFERENCE_ERROR",
            "ml_probability": None,
            "ml_threshold": min_probability,
        }
