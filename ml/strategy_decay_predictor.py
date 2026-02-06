from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from config import config as cfg


MODEL_PATH = Path(getattr(cfg, "DECAY_MODEL_PATH", "models/decay_model.pkl"))
FEATURES_PATH = Path("data/decay_features.parquet")
REPORT_PATH = Path("logs/decay_report.json")


def _load_features(path: Path = FEATURES_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _select_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
    if df.empty:
        return df, []
    drop_cols = {
        "strategy_id",
        "window_end_ts",
        "decayed",
        "next_expectancy",
        "next_drawdown",
        "time_to_failure_sec",
        "regime_dist",
    }
    numeric_cols = [c for c in df.columns if c not in drop_cols and df[c].dtype.kind in "if"]
    X = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return X, numeric_cols


def _load_model():
    if not MODEL_PATH.exists():
        return None
    import joblib
    return joblib.load(MODEL_PATH)


def predict_decay_probs(features_path: Path = FEATURES_PATH) -> pd.DataFrame:
    df = _load_features(features_path)
    if df.empty:
        return pd.DataFrame()
    X, _ = _select_features(df)
    model = _load_model()
    if model is None:
        return pd.DataFrame()
    probs = model.predict_proba(X)[:, 1]
    out = df[["strategy_id", "window_end_ts"]].copy()
    out["decay_probability"] = probs
    return out


def latest_decay_probs(features_path: Path = FEATURES_PATH) -> Dict[str, float]:
    df = predict_decay_probs(features_path)
    if df.empty:
        return {}
    df["window_end_ts"] = pd.to_datetime(df["window_end_ts"], errors="coerce")
    df = df.dropna(subset=["window_end_ts"])
    latest = df.sort_values("window_end_ts").groupby("strategy_id").tail(1)
    return {r["strategy_id"]: float(r["decay_probability"]) for _, r in latest.iterrows()}


def generate_decay_report() -> dict:
    probs = latest_decay_probs()
    soft_thr = float(getattr(cfg, "DECAY_SOFT_THRESHOLD", 0.5))
    hard_thr = float(getattr(cfg, "DECAY_HARD_THRESHOLD", 0.75))
    report = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "soft_threshold": soft_thr,
        "hard_threshold": hard_thr,
        "decay_probabilities": probs,
        "soft_disabled": [k for k, v in probs.items() if v >= soft_thr],
        "quarantine_candidates": [k for k, v in probs.items() if v >= hard_thr],
    }
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    return report


def telegram_summary(report: dict) -> str:
    probs = report.get("decay_probabilities", {})
    if not probs:
        return "Decay report: no decay probabilities available."
    soft = report.get("soft_disabled", [])
    hard = report.get("quarantine_candidates", [])
    return (
        "Decay report: "
        f"soft={len(soft)} hard={len(hard)} "
        f"top={sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]}"
    )

