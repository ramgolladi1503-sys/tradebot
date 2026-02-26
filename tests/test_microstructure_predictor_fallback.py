from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression


def test_microstructure_predictor_loads_sklearn_fallback(tmp_path, monkeypatch):
    from config import config as cfg

    x = np.array(
        [
            [0.1, 10.0, 1.0],
            [0.2, 8.0, -1.0],
            [0.3, 15.0, 2.0],
            [0.05, 6.0, -2.0],
        ],
        dtype=float,
    )
    y = np.array([1, 0, 1, 0], dtype=int)
    model = LogisticRegression(max_iter=200, random_state=42)
    model.fit(x, y)

    pkl_path = tmp_path / "microstructure_model.pkl"
    joblib.dump({"backend": "sklearn", "model": model, "features": ["a", "b", "c"]}, pkl_path)

    # Predictor defaults to MICRO_MODEL_PATH; when that is .h5 it should still
    # auto-discover and load the .pkl fallback.
    monkeypatch.setattr(cfg, "MICRO_MODEL_PATH", str(tmp_path / "microstructure_model.h5"), raising=False)

    from ml.microstructure_predictor import MicrostructurePredictor

    predictor = MicrostructurePredictor()
    conf = predictor.predict_confidence([0.2, 11.0, 0.5])

    assert predictor.model_backend == "sklearn"
    assert 0.0 <= float(conf) <= 1.0
    assert Path(predictor.model_path).name == "microstructure_model.h5"
