from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import config as cfg
from ml.strategy_decay_predictor import _select_features


MODEL_PATH = Path(getattr(cfg, "DECAY_MODEL_PATH", "models/decay_model.pkl"))


def train_decay_model(features_path: Path = Path("data/decay_features.parquet")) -> dict:
    if not features_path.exists():
        raise FileNotFoundError(f"Decay features not found: {features_path}")

    df = pd.read_parquet(features_path)
    if df.empty or "decayed" not in df.columns:
        raise ValueError("Decay features must include a 'decayed' column.")

    X, cols = _select_features(df)
    y = df["decayed"].fillna(0).astype(int)

    try:
        from xgboost import XGBClassifier
    except Exception as e:
        raise ImportError("xgboost is required for decay model training.") from e

    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score
    except Exception as e:
        raise ImportError("scikit-learn is required for decay model training.") from e

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    base = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=4,
    )
    method = str(getattr(cfg, "DECAY_CALIBRATION_METHOD", "isotonic"))
    model = CalibratedClassifierCV(base, method=method, cv=3)
    model.fit(X_train, y_train)

    y_pred = model.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, y_pred) if y_val.nunique() > 1 else None

    MODEL_PATH.parent.mkdir(exist_ok=True)
    import joblib
    joblib.dump(model, MODEL_PATH)

    return {
        "model_path": str(MODEL_PATH),
        "features": cols,
        "auc": auc,
        "calibration_method": method,
        "rows": len(df),
    }


if __name__ == "__main__":
    report = train_decay_model()
    print(report)
