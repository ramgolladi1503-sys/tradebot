#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.feature_builder import add_indicators


DEFAULT_FEATURES = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "sma_10",
    "ema_20",
    "ema_50",
    "rsi_14",
    "atr_14",
    "vwap",
    "vwap_slope",
    "return_1",
    "rsi_mom",
    "vol_z",
    "adx_14",
)


def _pick_features(frame: pd.DataFrame, features: list[str] | None) -> list[str]:
    selected = [str(col).strip() for col in (features or DEFAULT_FEATURES) if str(col).strip()]
    missing = [col for col in selected if col not in frame.columns]
    if missing:
        raise ValueError(f"missing_feature_columns:{','.join(missing)}")
    return selected


def _engineer_features(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = add_indicators(frame.copy())
    if "timestamp" in enriched.columns:
        enriched["timestamp"] = pd.to_datetime(enriched["timestamp"], errors="coerce")
    if "vol_z" in enriched.columns:
        enriched["vol_z"] = enriched["vol_z"].fillna(0.0)
    if "vwap_slope" in enriched.columns:
        enriched["vwap_slope"] = enriched["vwap_slope"].fillna(0.0)
    if "rsi_mom" in enriched.columns:
        enriched["rsi_mom"] = enriched["rsi_mom"].fillna(0.0)
    if "adx_14" in enriched.columns:
        enriched["adx_14"] = enriched["adx_14"].fillna(0.0)
    return enriched


def _best_reject_threshold(frame: pd.DataFrame, proba: pd.Series, *, return_col: str = "future_return", cost_bps: float = 10.0) -> dict[str, Any]:
    if return_col not in frame.columns:
        return {"status": "missing_return_col"}
    returns = pd.to_numeric(frame[return_col], errors="coerce").fillna(0.0).reset_index(drop=True)
    proba = pd.Series(proba).reset_index(drop=True)
    best = {"threshold": 0.5, "net_expectancy": float("-inf"), "reject_rate": 1.0}
    for threshold in [i / 100 for i in range(30, 71, 2)]:
        selected = proba >= threshold
        if not bool(selected.any()):
            continue
        gross = returns[selected].mean()
        net = float(gross - (cost_bps / 10000.0))
        if net > best["net_expectancy"]:
            best = {
                "threshold": float(threshold),
                "net_expectancy": float(net),
                "reject_rate": float(1.0 - selected.mean()),
            }
    return best


def train_offline_model(
    *,
    input_csv: str | Path,
    model_output: str | Path,
    metrics_output: str | Path | None = None,
    feature_columns: list[str] | None = None,
    label_column: str = "label_up",
    test_fraction: float = 0.2,
    model_family: str = "logistic",
) -> dict[str, Any]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    frame = pd.read_csv(source)
    if label_column not in frame.columns:
        raise ValueError(f"missing_label_column:{label_column}")

    engineered = _engineer_features(frame)
    features = _pick_features(engineered, feature_columns)
    usable = engineered.dropna(subset=["timestamp"] + [label_column]).copy()
    if usable.empty:
        raise ValueError("no_usable_rows_after_dropna")

    usable = usable.sort_values("timestamp").reset_index(drop=True)
    usable = usable.dropna(subset=features).reset_index(drop=True)
    if len(usable) < 10:
        raise ValueError("insufficient_rows_for_training")

    split_idx = max(1, int(len(usable) * (1.0 - float(test_fraction))))
    if split_idx >= len(usable):
        split_idx = len(usable) - 1
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()
    if train.empty or test.empty:
        raise ValueError("train_test_split_too_small")

    x_train = train[features].astype(float)
    y_train = train[label_column].astype(int)
    x_test = test[features].astype(float)
    y_test = test[label_column].astype(int)

    family = str(model_family or "logistic").strip().lower()
    if family == "logistic":
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=3000, class_weight="balanced")),
            ]
        )
        model_type = "StandardScaledLogisticRegression"
    elif family == "random_forest":
        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=50,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
        model_type = "RandomForestClassifier"
    else:
        raise ValueError(f"unsupported_model_family:{model_family}")
    model.fit(x_train, y_train)

    proba = model.predict_proba(x_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    acc = float(accuracy_score(y_test, preds))
    try:
        auc = float(roc_auc_score(y_test, proba))
    except Exception:
        auc = None

    report = classification_report(y_test, preds, output_dict=True, zero_division=0)
    reject_gate = _best_reject_threshold(
        test.reset_index(drop=True),
        pd.Series(proba, index=test.index),
        return_col="future_return" if "future_return" in test.columns else "realized_pnl_pct" if "realized_pnl_pct" in test.columns else "future_return_1",
    )
    payload = {
        "input_csv": str(source),
        "rows": int(len(usable)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "feature_columns": features,
        "label_column": label_column,
        "accuracy": acc,
        "roc_auc": auc,
        "classification_report": report,
        "model_type": model_type,
        "model_family": family,
        "reject_gate": reject_gate,
        "test_fraction": float(test_fraction),
    }

    model_path = Path(model_output).expanduser()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "feature_columns": features,
        "label_column": label_column,
        "metrics": payload,
    }
    joblib.dump(bundle, model_path)

    if metrics_output is not None:
        metrics_path = Path(metrics_output).expanduser()
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return {**payload, "model_output": str(model_path), "metrics_output": str(metrics_output) if metrics_output else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train a small offline classifier from labeled historical candles.")
    parser.add_argument("--input-csv", required=True, help="Labeled CSV path from build_next_bar_labels.py")
    parser.add_argument("--model-output", required=True, help="Joblib model artifact path")
    parser.add_argument("--metrics-output", default="", help="Optional metrics JSON path")
    parser.add_argument("--feature-columns", default="", help="Optional comma-separated feature columns")
    parser.add_argument("--label-column", default="label_up", help="Label column name")
    parser.add_argument("--test-fraction", type=float, default=0.2, help="Holdout fraction from the end of the series")
    parser.add_argument("--model-family", default="logistic", choices=["logistic", "random_forest"], help="Offline model family")
    args = parser.parse_args(argv)

    features = [item.strip() for item in args.feature_columns.split(",") if item.strip()]
    report = train_offline_model(
        input_csv=args.input_csv,
        model_output=args.model_output,
        metrics_output=args.metrics_output or None,
        feature_columns=features or None,
        label_column=args.label_column,
        test_fraction=args.test_fraction,
        model_family=args.model_family,
    )
    print(
        "training_complete "
        f"rows={report['rows']} train_rows={report['train_rows']} test_rows={report['test_rows']} "
        f"accuracy={report['accuracy']:.6f} "
        f"roc_auc={report['roc_auc'] if report['roc_auc'] is not None else 'NA'} "
        f"model={report['model_output']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
