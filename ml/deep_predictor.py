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

class DeepPredictor:
    def __init__(self, model_path=None, seq_len=None):
        self.model_path = model_path or cfg.DEEP_MODEL_PATH
        self.seq_len = seq_len or cfg.DEEP_SEQUENCE_LEN
        self.model = None
        if load_model and os.path.exists(self.model_path):
            # Avoid unnecessary compile/metrics warnings for inference-only use
            self.model = load_model(self.model_path, compile=False)

    def predict_confidence(self, seq):
        if self.model is None:
            return 0.5
        seq = np.asarray(seq, dtype=float)
        if seq.ndim == 2:
            seq = np.expand_dims(seq, axis=0)
        proba = self.model.predict(seq, verbose=0)
        if proba.ndim == 2 and proba.shape[1] > 1:
            return float(proba[0][1])
        return float(proba[0][0])
