import os
import numpy as np
from config import config as cfg

try:
    from core.tf_utils import configure_tensorflow
    configure_tensorflow()
except Exception:
    pass

try:
    from tensorflow.keras.models import load_model
except Exception:
    load_model = None

class MicrostructurePredictor:
    def __init__(self, model_path=None):
        self.model_path = model_path or cfg.MICRO_MODEL_PATH
        self.model = None
        if load_model and os.path.exists(self.model_path):
            # Avoid unnecessary compile/metrics warnings for inference-only use
            self.model = load_model(self.model_path, compile=False)

    def predict_confidence(self, features):
        if self.model is None:
            return 0.5
        x = np.asarray([features], dtype=float)
        try:
            expected = None
            if hasattr(self.model, "input_shape") and self.model.input_shape:
                expected = self.model.input_shape[-1]
            if expected and x.shape[1] != expected:
                if x.shape[1] < expected:
                    pad = np.zeros((1, expected - x.shape[1]), dtype=float)
                    x = np.concatenate([x, pad], axis=1)
                else:
                    x = x[:, :expected]
        except Exception:
            pass
        proba = self.model.predict(x, verbose=0)
        if proba.ndim == 2 and proba.shape[1] > 1:
            return float(proba[0][1])
        return float(proba[0][0])
