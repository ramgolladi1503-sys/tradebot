import json
import math
from pathlib import Path

from core.regime_session_context import resolve_canonical_session_context


REGIMES = ["TREND", "RANGE", "RANGE_VOLATILE", "EVENT", "PANIC"]


class RegimeProbModel:
    """
    Probabilistic regime model. Uses a Bayesian Gaussian NB model if available;
    otherwise falls back to a heuristic softmax scorer.
    """
    def __init__(self, model_path: str | None = None):
        self.model_path = Path(model_path) if model_path else Path("models/regime_model.json")
        self.model = None
        self._load()

    def _load(self):
        if not self.model_path.exists():
            self.model = None
            return
        try:
            self.model = json.loads(self.model_path.read_text())
        except Exception:
            self.model = None

    def _gaussian_nb_proba(self, features: dict) -> dict:
        priors = self.model.get("priors", {})
        means = self.model.get("means", {})
        vars_ = self.model.get("vars", {})
        scores = {}
        for r in REGIMES:
            prior = float(priors.get(r, 1e-6))
            score = math.log(prior + 1e-9)
            mu = means.get(r, {})
            var = vars_.get(r, {})
            for k, v in features.items():
                if v is None:
                    continue
                m = float(mu.get(k, 0.0))
                s2 = float(var.get(k, 1e-6))
                s2 = max(s2, 1e-6)
                # log Gaussian
                score += -0.5 * (math.log(2 * math.pi * s2) + ((v - m) ** 2) / s2)
            scores[r] = score
        return _softmax(scores)

    def _heuristic_proba(self, features: dict) -> dict:
        adx = features.get("adx", 0.0) or 0.0
        vwap_slope = features.get("vwap_slope", 0.0) or 0.0
        vol_z = features.get("vol_z", 0.0) or 0.0
        atr_pct = features.get("atr_pct", 0.0) or 0.0
        iv_mean = features.get("iv_mean", 0.0) or 0.0
        ltp_accel = features.get("ltp_acceleration", 0.0) or 0.0
        skew = features.get("option_chain_skew", 0.0) or 0.0
        oi_delta = features.get("oi_delta", 0.0) or 0.0
        depth_imb = features.get("depth_imbalance", 0.0) or 0.0
        trans_rate = features.get("regime_transition_rate", 0.0) or 0.0
        shock_score = features.get("shock_score", 0.0) or 0.0
        uncertainty = features.get("uncertainty_index", 0.0) or 0.0
        macro_bias = features.get("macro_direction_bias", 0.0) or 0.0
        x_align = features.get("x_regime_align", 0.0) or 0.0
        x_volspill = features.get("x_vol_spillover", 0.0) or 0.0
        x_lead = features.get("x_lead_lag", 0.0) or 0.0

        # Normalize helpers
        adx_n = min(max(adx / 40.0, 0.0), 2.0)
        vol_n = min(max(vol_z / 2.0, 0.0), 2.0)
        atr_n = min(max(atr_pct / 0.01, 0.0), 2.0)
        iv_n = min(max(iv_mean / 0.6, 0.0), 2.0)
        slope_n = min(max(abs(vwap_slope) / 5.0, 0.0), 2.0)
        accel_n = min(max(abs(ltp_accel) / 20.0, 0.0), 2.0)
        trans_n = min(max(trans_rate / 10.0, 0.0), 2.0)
        shock_n = min(max(shock_score / 1.0, 0.0), 2.0)
        uncert_n = min(max(uncertainty / 1.0, 0.0), 2.0)
        x_vol_n = min(max(x_volspill / 1.5, 0.0), 2.0)
        x_align_n = max(-1.0, min(1.0, x_align))
        x_lead_n = max(-1.0, min(1.0, x_lead))

        scores = {
            "TREND": 1.2 * adx_n + 1.0 * slope_n + 0.6 * atr_n + 0.2 * abs(oi_delta) + 0.2 * max(0.0, x_align_n),
            "RANGE": 1.2 * (1.5 - adx_n) + 0.8 * (1.0 - slope_n) + 0.2 * (1.0 - atr_n),
            "RANGE_VOLATILE": 0.8 * (1.5 - adx_n) + 1.2 * vol_n + 0.7 * atr_n + 0.3 * x_vol_n,
            "EVENT": 1.3 * vol_n + 1.0 * iv_n + 0.6 * atr_n + 0.2 * abs(skew) + 1.2 * shock_n + 0.4 * uncert_n + 0.3 * x_vol_n,
            "PANIC": 1.4 * vol_n + 1.0 * atr_n + 0.7 * accel_n + 0.4 * trans_n + 1.4 * shock_n + 0.6 * uncert_n + 0.2 * abs(macro_bias) + 0.4 * x_vol_n + 0.2 * abs(x_lead_n),
        }
        # Penalize high transition rates for stable regimes
        scores["TREND"] -= 0.3 * trans_n
        scores["RANGE"] -= 0.3 * trans_n
        # Penalize calm regimes when shock is elevated
        scores["TREND"] -= 0.2 * shock_n
        scores["RANGE"] -= 0.4 * shock_n
        return _softmax(scores)

    def _resolve_session_bucket(self, features: dict) -> str:
        session_bucket = str(features.get("session_bucket") or "").strip().upper()
        if session_bucket:
            return session_bucket
        timestamp_keys = ("timestamp_ist", "timestamp", "ltp_ts_epoch", "quote_ts_epoch", "quote_ts", "candle_ts_epoch", "regime_ts")
        for key in timestamp_keys:
            value = features.get(key)
            if value is None or value == "":
                continue
            context = resolve_canonical_session_context(
                value,
                segment=str(features.get("segment") or "NSE_FNO"),
                is_expiry_day=bool(features.get("is_expiry_day")),
                is_event_mode=bool(features.get("is_event_mode")),
            )
            return context.canonical_session_bucket
        return "DEFAULT"

    def predict(self, features: dict) -> dict:
        if self.model:
            probs = self._gaussian_nb_proba(features)
        else:
            probs = self._heuristic_proba(features)
        primary = max(probs, key=lambda k: probs.get(k, 0.0)) if probs else "NEUTRAL"
        
        from core.entropy_contract import entropy_diagnostics
        diag = entropy_diagnostics(probs, labels=REGIMES)
        entropy = diag["entropy"]
        entropy_normalized = diag["normalized_entropy"]
        
        # Use session-aware threshold if passed in features, else derive canonically.
        session_bucket = self._resolve_session_bucket(features)
        
        # Import config inline to avoid circular imports if any, or rely on features
        try:
            from config import config as cfg
        except Exception:
            cfg = None
            
        if session_bucket == "OPEN_DISCOVERY":
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY", 0.90) if cfg else 0.90
        elif session_bucket == "MID_SESSION":
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_MID_SESSION", 0.78) if cfg else 0.78
        elif session_bucket == "CLOSING_VOL":
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_CLOSING_VOL", 0.88) if cfg else 0.88
        elif session_bucket == "EXPIRY_DAY":
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EXPIRY_DAY", 0.86) if cfg else 0.86
        elif session_bucket == "EVENT_MODE":
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EVENT_MODE", 0.92) if cfg else 0.92
        else:
            threshold = getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT", 0.80) if cfg else 0.80
            
        unstable = bool(entropy_normalized > float(threshold))
        
        return {
            "regime_probs": probs,
            "primary_regime": primary,
            "regime_entropy": entropy,
            "regime_entropy_normalized": entropy_normalized,
            "regime_entropy_threshold": float(threshold),
            "unstable_regime_flag": unstable,
            "market_regime_uncertain": unstable,
        }


def _softmax(scores: dict) -> dict:
    if not scores:
        return {}
    mx = max(scores.values())
    exps = {k: math.exp(v - mx) for k, v in scores.items()}
    s = sum(exps.values()) or 1.0
    return {k: round(v / s, 6) for k, v in exps.items()}
