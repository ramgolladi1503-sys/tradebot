import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.ensemble import GradientBoostingClassifier
from joblib import dump

from core import model_registry


@dataclass
class AlphaFactoryResult:
    report_path: Path
    model_path: Path | None
    best_name: str | None
    metrics: dict


def _parse_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce", utc=True)
    if ts.isna().any():
        raise ValueError("truth_dataset has invalid timestamps in ts column")
    return ts


def _select_target(df: pd.DataFrame) -> tuple[str, pd.Series]:
    for col in ["pnl_15m", "realized_pnl", "pnl_5m"]:
        if col in df.columns and df[col].notna().any():
            return col, df[col]
    raise ValueError("No suitable target column found (pnl_15m/realized_pnl/pnl_5m)")


def _build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    base_cols = [
        "spread_pct",
        "depth_imbalance",
        "quote_age_sec",
        "regime_entropy",
        "shock_score",
        "uncertainty_index",
        "fx_ret_5m",
        "vix_z",
        "crude_ret_15m",
        "corr_fx_nifty",
        "score_0_100",
        "ensemble_proba",
        "ensemble_uncertainty",
    ]
    present = [c for c in base_cols if c in df.columns]
    feat = df[present].copy()
    if "symbol" in df.columns and "score_0_100" in df.columns:
        feat["lag_score_1"] = df.groupby("symbol")["score_0_100"].shift(1)
        feat["lag_score_3"] = df.groupby("symbol")["score_0_100"].shift(3)
        present += ["lag_score_1", "lag_score_3"]
    feat = feat.fillna(0.0)
    return feat, present


def _time_split(df: pd.DataFrame, ts_col: str, train_frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_sorted = df.sort_values(ts_col).reset_index(drop=True)
    cut = int(len(df_sorted) * train_frac)
    if cut <= 0 or cut >= len(df_sorted):
        raise ValueError("Insufficient rows for time split")
    train = df_sorted.iloc[:cut].copy()
    valid = df_sorted.iloc[cut:].copy()
    if train[ts_col].max() >= valid[ts_col].min():
        raise ValueError("Time split leakage: train overlaps validation timestamps")
    return train, valid


def _evaluate_model(name: str, model, X_train, y_train, X_valid, y_valid, pnl_valid, regimes_valid) -> dict:
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_valid)[:, 1]
    pred = prob >= 0.5
    pnl = pnl_valid[pred]
    pnl_mean = float(np.mean(pnl)) if len(pnl) else 0.0
    pnl_std = float(np.std(pnl)) if len(pnl) else 0.0
    sharpe_proxy = float(pnl_mean / pnl_std) if pnl_std > 0 else 0.0
    brier = float(brier_score_loss(y_valid, prob))
    regime_scores = {}
    if regimes_valid is not None:
        for reg in sorted(regimes_valid.unique()):
            mask = regimes_valid == reg
            if mask.sum() < 5:
                continue
            try:
                regime_scores[reg] = float(brier_score_loss(y_valid[mask], prob[mask]))
            except Exception:
                continue
    stability = float(np.std(list(regime_scores.values()))) if regime_scores else 0.0
    score = sharpe_proxy - 0.25 * stability
    return {
        "name": name,
        "sharpe_proxy": sharpe_proxy,
        "pnl_mean": pnl_mean,
        "pnl_std": pnl_std,
        "brier": brier,
        "regime_brier": regime_scores,
        "regime_brier_std": stability,
        "score": score,
        "model": model,
    }


def run_alpha_factory(
    truth_path: Path = Path("data/truth_dataset.parquet"),
    days: int = 90,
    dry_run: bool = False,
    out_report: Path = Path("logs/alpha_factory_report.json"),
    min_rows: int = 200,
) -> AlphaFactoryResult:
    if not truth_path.exists():
        raise FileNotFoundError(f"Missing truth dataset: {truth_path}")
    df = pd.read_parquet(truth_path)
    if "ts" not in df.columns:
        raise ValueError("truth_dataset missing ts column")
    df["ts_dt"] = _parse_ts(df["ts"])
    max_ts = df["ts_dt"].max()
    min_ts = max_ts - pd.Timedelta(days=days)
    df = df[df["ts_dt"] >= min_ts].copy()
    if len(df) < min_rows:
        raise ValueError(f"Insufficient rows for alpha factory: {len(df)} < {min_rows}")
    target_col, target_series = _select_target(df)
    df = df[target_series.notna()].copy()
    if len(df) < min_rows:
        raise ValueError(f"Insufficient labeled rows for alpha factory: {len(df)} < {min_rows}")
    y = (df[target_col] > 0).astype(int).values
    X, features = _build_features(df)
    train, valid = _time_split(df.assign(_y=y), "ts_dt", train_frac=0.7)
    X_train = X.loc[train.index].values
    y_train = train["_y"].values
    X_valid = X.loc[valid.index].values
    y_valid = valid["_y"].values
    pnl_valid = valid[target_col].values
    regimes_valid = valid["primary_regime"] if "primary_regime" in valid.columns else None

    candidates = []
    candidates.append(_evaluate_model(
        "logreg",
        LogisticRegression(max_iter=200, n_jobs=1),
        X_train, y_train, X_valid, y_valid, pnl_valid, regimes_valid
    ))
    candidates.append(_evaluate_model(
        "gboost",
        GradientBoostingClassifier(random_state=42),
        X_train, y_train, X_valid, y_valid, pnl_valid, regimes_valid
    ))
    candidates_sorted = sorted(candidates, key=lambda x: x["score"], reverse=True)
    best = candidates_sorted[0]
    model_path = None
    if not dry_run:
        Path("models").mkdir(exist_ok=True)
        model_path = Path("models") / f"alpha_factory_challenger_{int(time.time())}.pkl"
        dump(best["model"], model_path)
        model_registry.register_model(
            model_type="alpha_factory",
            path=model_path,
            metrics={
                "score": best["score"],
                "sharpe_proxy": best["sharpe_proxy"],
                "brier": best["brier"],
                "regime_brier_std": best["regime_brier_std"],
            },
            governance={
                "features": features,
                "target": target_col,
                "train_start": str(train["ts_dt"].min()),
                "train_end": str(train["ts_dt"].max()),
                "valid_start": str(valid["ts_dt"].min()),
                "valid_end": str(valid["ts_dt"].max()),
                "dry_run": False,
            },
            status="challenger",
        )

    report = {
        "run_ts": time.time(),
        "truth_path": str(truth_path),
        "days": days,
        "rows": int(len(df)),
        "target": target_col,
        "features": features,
        "candidates": [
            {
                "name": c["name"],
                "score": c["score"],
                "sharpe_proxy": c["sharpe_proxy"],
                "brier": c["brier"],
                "regime_brier_std": c["regime_brier_std"],
                "regime_brier": c["regime_brier"],
            }
            for c in candidates_sorted
        ],
        "best": best["name"],
        "dry_run": dry_run,
        "model_path": str(model_path) if model_path else None,
    }
    out_report.parent.mkdir(exist_ok=True)
    out_report.write_text(json.dumps(report, indent=2))
    return AlphaFactoryResult(out_report, model_path, best["name"], report)
