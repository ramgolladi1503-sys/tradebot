#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.train_offline_model import _engineer_features, _pick_features


def _format_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "NA"


def _fit_model(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    label_column: str,
    model_family: str,
) -> tuple[Any | None, pd.DataFrame, str | None]:
    usable = (
        frame.dropna(subset=["timestamp", label_column])
        .copy()
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    usable = usable.dropna(subset=feature_columns).reset_index(drop=True)
    if len(usable) < 10:
        raise ValueError("insufficient_rows_for_regime_comparison")
    split_idx = max(1, int(len(usable) * 0.8))
    if split_idx >= len(usable):
        split_idx = len(usable) - 1
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()
    if train.empty or test.empty:
        raise ValueError("train_test_split_too_small")
    if train[label_column].dropna().nunique() < 2:
        return (
            None,
            test.assign(
                pred_proba=0.0,
                pred_label=0,
                actual_label=test[label_column].astype(int),
            ),
            "single_class_train",
        )

    x_train = train[feature_columns].astype(float)
    y_train = train[label_column].astype(int)
    x_test = test[feature_columns].astype(float)
    y_test = test[label_column].astype(int)

    family = str(model_family or "logistic").strip().lower()
    if family == "logistic":
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(max_iter=3000, class_weight="balanced"),
                ),
            ]
        )
    elif family == "random_forest":
        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=50,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"unsupported_model_family:{model_family}")
    model.fit(x_train, y_train)
    proba = pd.Series(model.predict_proba(x_test)[:, 1], index=test.index)
    scored = test.copy()
    scored["pred_proba"] = proba
    scored["pred_label"] = (scored["pred_proba"] >= 0.5).astype(int)
    scored["actual_label"] = y_test.values
    return model, scored, None


def _regime_summary(
    scored: pd.DataFrame,
    *,
    label_column: str,
    return_column: str = "expected_value_bps",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    regime_filter: dict[str, str] = {}
    if scored.empty:
        return {"rows": [], "regime_filter": {}, "status": "empty_scored_frame"}
    for regime, segment in scored.groupby("regime_tag", sort=True):
        actual = segment[label_column].astype(int)
        preds = segment["pred_label"].astype(int)
        proba = segment["pred_proba"].astype(float)
        metrics = {
            "regime_tag": regime,
            "samples": int(len(segment)),
            "accuracy": float(accuracy_score(actual, preds)),
            "roc_auc": None,
            "avg_pred_proba": float(proba.mean()) if len(proba) else 0.0,
            "avg_expected_value_bps": float(
                pd.to_numeric(segment.get(return_column), errors="coerce")
                .fillna(0.0)
                .mean()
            )
            if return_column in segment.columns
            else None,
            "positive_rate": float(actual.mean()) if len(actual) else 0.0,
        }
        try:
            metrics["roc_auc"] = float(roc_auc_score(actual, proba))
        except Exception:
            metrics["roc_auc"] = None
        if metrics["samples"] < 20:
            regime_filter[regime] = "FILTER_SMALL_SAMPLE"
        elif (metrics["avg_expected_value_bps"] is not None) and metrics[
            "avg_expected_value_bps"
        ] <= 0:
            regime_filter[regime] = "FILTER_NEGATIVE_EV"
        elif metrics["roc_auc"] is not None and metrics["roc_auc"] < 0.5:
            regime_filter[regime] = "WATCH_WEAK_AUC"
        else:
            regime_filter[regime] = "KEEP"
        rows.append(metrics)
    rows.sort(key=lambda row: (row["regime_tag"], row["samples"]))
    return {"rows": rows, "regime_filter": regime_filter}


def build_regime_model_comparison(
    *,
    input_csv: str | Path,
    output_json: str | Path,
    output_csv: str | Path | None = None,
    output_md: str | Path | None = None,
    label_column: str = "ev_positive",
    feature_columns: list[str] | None = None,
) -> dict[str, Any]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    frame = pd.read_csv(source)
    if "regime_tag" not in frame.columns:
        raise ValueError("missing_regime_tag_column")
    if label_column not in frame.columns:
        raise ValueError(f"missing_label_column:{label_column}")

    engineered = _engineer_features(frame)
    features = _pick_features(engineered, feature_columns)
    scored_by_model: dict[str, Any] = {}
    for family in ("logistic", "random_forest"):
        model, scored, status = _fit_model(
            engineered,
            feature_columns=features,
            label_column=label_column,
            model_family=family,
        )
        summary = _regime_summary(scored, label_column=label_column)
        if status:
            summary["status"] = status
        summary["trained"] = model is not None
        scored_by_model[family] = summary

    payload = {
        "input_csv": str(source),
        "label_column": label_column,
        "feature_columns": features,
        "models": scored_by_model,
    }
    target = Path(output_json).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    csv_target = (
        Path(output_csv).expanduser()
        if output_csv is not None
        else target.with_suffix(".csv")
    )
    md_target = (
        Path(output_md).expanduser()
        if output_md is not None
        else target.with_suffix(".md")
    )

    csv_rows: list[dict[str, Any]] = []
    for model_name, summary in scored_by_model.items():
        for row in summary.get("rows", []):
            csv_rows.append(
                {
                    "model_family": model_name,
                    "regime_tag": row.get("regime_tag"),
                    "samples": row.get("samples"),
                    "accuracy": row.get("accuracy"),
                    "roc_auc": row.get("roc_auc"),
                    "avg_pred_proba": row.get("avg_pred_proba"),
                    "avg_expected_value_bps": row.get("avg_expected_value_bps"),
                    "positive_rate": row.get("positive_rate"),
                    "regime_filter": summary.get("regime_filter", {}).get(
                        str(row.get("regime_tag")), "KEEP"
                    ),
                    "status": summary.get("status", "ok"),
                    "trained": summary.get("trained", False),
                }
            )
    csv_frame = pd.DataFrame(csv_rows)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    csv_frame.to_csv(csv_target, index=False)

    md_lines = [
        "# Regime Model Comparison",
        "",
        f"- Input CSV: {source}",
        f"- Label column: `{label_column}`",
        f"- Feature columns: {', '.join(features)}",
        "",
    ]
    for model_name, summary in scored_by_model.items():
        md_lines.extend(
            [
                f"## {model_name}",
                "",
                f"- Trained: `{summary.get('trained', False)}`",
                f"- Status: `{summary.get('status', 'ok')}`",
                "",
                "| regime_tag | samples | accuracy | roc_auc | avg_pred_proba | avg_expected_value_bps | positive_rate | filter |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in summary.get("rows", []):
            md_lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("regime_tag")),
                        str(row.get("samples")),
                        _format_float(row.get("accuracy")),
                        _format_float(row.get("roc_auc")),
                        _format_float(row.get("avg_pred_proba")),
                        _format_float(row.get("avg_expected_value_bps")),
                        _format_float(row.get("positive_rate")),
                        str(
                            summary.get("regime_filter", {}).get(
                                str(row.get("regime_tag")), "KEEP"
                            )
                        ),
                    ]
                )
                + " |"
            )
        md_lines.append("")
    md_target.parent.mkdir(parents=True, exist_ok=True)
    md_target.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    return {
        **payload,
        "output_json": str(target),
        "output_csv": str(csv_target),
        "output_md": str(md_target),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare model families across market regimes."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--label-column", default="ev_positive")
    parser.add_argument(
        "--feature-columns", default="", help="Optional comma-separated feature columns"
    )
    args = parser.parse_args(argv)

    features = [
        item.strip() for item in args.feature_columns.split(",") if item.strip()
    ]
    report = build_regime_model_comparison(
        input_csv=args.input_csv,
        output_json=args.output_json,
        label_column=args.label_column,
        feature_columns=features or None,
    )
    print(f"regime_comparison_written={report['output_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
