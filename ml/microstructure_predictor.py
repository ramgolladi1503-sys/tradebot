import os
import numpy as np
from config import config as cfg
from core.model_registry import get_active_entry, get_shadow_entry

try:
    from core.tf_utils import configure_tensorflow
    configure_tensorflow()
except Exception:
    pass

try:
    from tensorflow.keras.models import load_model
except Exception:
    load_model = None


def _sanitize_key(key: str) -> str:
    return key.replace("|", "_").replace("/", "_").replace(" ", "_")


def _segment_key(context=None):
    if not context:
        return None
    reg = (context.get("regime") or context.get("seg_regime") or "GLOBAL").upper()
    bucket = (context.get("time_bucket") or context.get("seg_bucket") or "MID").upper()
    exp = context.get("is_expiry")
    if exp is None:
        exp = context.get("seg_expiry")
    exp_tag = "EXP" if bool(exp) else "NEXP"
    vq = context.get("vol_quartile")
    if vq is None:
        vq = context.get("seg_vol_q")
    try:
        vq = int(vq)
    except Exception:
        vq = 2
    return f"{reg}|{bucket}|{exp_tag}|VQ{vq}"


class MicrostructurePredictor:
    def __init__(self, model_path=None):
        active = get_active_entry("microstructure")
        self.model_path = model_path or (active.get("path") if active else None) or cfg.MICRO_MODEL_PATH
        self.model = None
        self.segment_models = {}
        self.model_version = active.get("hash") if active else None
        self.model_governance = active.get("governance") if active else {}
        shadow = get_shadow_entry("microstructure")
        self.shadow_version = shadow.get("hash") if shadow else None
        self.shadow_governance = shadow.get("governance") if shadow else {}
        if load_model and os.path.exists(self.model_path):
            self.model = load_model(self.model_path, compile=False)

    def _segment_path(self, key: str) -> str:
        base, ext = os.path.splitext(self.model_path)
        if not ext:
            ext = ".h5"
        safe = _sanitize_key(key)
        return f"{base}_{safe}{ext}"

    def _get_model(self, context=None):
        key = _segment_key(context)
        if not key:
            return self.model
        if key in self.segment_models:
            return self.segment_models[key]
        path = self._segment_path(key)
        if load_model and os.path.exists(path):
            self.segment_models[key] = load_model(path, compile=False)
            return self.segment_models[key]
        return self.model

    def predict_confidence(self, features, context=None):
        model = self._get_model(context=context)
        if model is None:
            return 0.5
        x = np.asarray([features], dtype=float)
        try:
            expected = None
            if hasattr(model, "input_shape") and model.input_shape:
                expected = model.input_shape[-1]
            if expected and x.shape[1] != expected:
                if x.shape[1] < expected:
                    pad = np.zeros((1, expected - x.shape[1]), dtype=float)
                    x = np.concatenate([x, pad], axis=1)
                else:
                    x = x[:, :expected]
        except Exception:
            pass
        proba = model.predict(x, verbose=0)
        if proba.ndim == 2 and proba.shape[1] > 1:
            return float(proba[0][1])
        return float(proba[0][0])

    def get_governance(self):
        return {
            "model_version": self.model_version,
            "model_governance": self.model_governance,
            "shadow_version": self.shadow_version,
            "shadow_governance": self.shadow_governance,
        }
