#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import joblib
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.train_offline_model import train_offline_model


def _session_bucket(ts: pd.Timestamp) -> str:
    hour = ts.hour
    if hour < 11:
        return "OPEN"
    if hour < 14:
        return "MID"
    return "CLOSE"


def train_segmented_offline_models(
    *,
    input_csv: str | Path,
    model_dir: str | Path,
    metrics_output: str | Path | None = None,
    label_column: str = "label_up",
    model_family: str = "logistic",
) -> dict[str, Any]:
    source = Path(input_csv).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"input_csv_not_found:{source}")

    frame = pd.read_csv(source)
    if label_column not in frame.columns:
        raise ValueError(f"missing_label_column:{label_column}")
    if "timestamp" not in frame.columns:
        raise ValueError("missing_required_columns:timestamp")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = (
        frame.dropna(subset=["timestamp", label_column])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    frame["session_bucket"] = frame["timestamp"].apply(_session_bucket)

    out_dir = Path(model_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, Any] = {"segments": {}}
    skipped: dict[str, str] = {}
    for bucket, segment in frame.groupby("session_bucket", sort=True):
        if len(segment) < 20:
            skipped[bucket] = "segment_too_small"
            continue
        if segment[label_column].dropna().nunique() < 2:
            skipped[bucket] = "single_class_segment"
            continue
        seg_input = out_dir / f"_{bucket}_segment.csv"
        segment.to_csv(seg_input, index=False)
        report = train_offline_model(
            input_csv=seg_input,
            model_output=out_dir / f"{bucket.lower()}_{model_family}.joblib",
            metrics_output=out_dir / f"{bucket.lower()}_{model_family}.json",
            label_column=label_column,
            model_family=model_family,
        )
        metrics["segments"][bucket] = report
        seg_input.unlink(missing_ok=True)

    payload_path = None
    if metrics_output is not None:
        payload_path = Path(metrics_output).expanduser()
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(pd.Series(metrics).to_json(), encoding="utf-8")
    return {
        "input_csv": str(source),
        "model_dir": str(out_dir),
        "metrics_output": str(payload_path) if payload_path else None,
        "segments": list(metrics["segments"].keys()),
        "skipped_segments": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train separate offline models by session bucket."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument(
        "--metrics-output", default="", help="Optional summary JSON path"
    )
    parser.add_argument("--label-column", default="label_up")
    parser.add_argument(
        "--model-family", default="logistic", choices=["logistic", "random_forest"]
    )
    args = parser.parse_args(argv)

    report = train_segmented_offline_models(
        input_csv=args.input_csv,
        model_dir=args.model_dir,
        metrics_output=args.metrics_output or None,
        label_column=args.label_column,
        model_family=args.model_family,
    )
    print(
        f"segmented_models={','.join(report['segments']) or 'NONE'} model_dir={report['model_dir']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
