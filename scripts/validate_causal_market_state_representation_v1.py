from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.market_state import build_market_state_frame, state_contract


def _hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _ridge_fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, alpha: float = 10.0) -> np.ndarray:
    x_train = np.column_stack([np.ones(len(x_train)), x_train])
    x_test = np.column_stack([np.ones(len(x_test)), x_test])
    penalty = np.eye(x_train.shape[1]) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(x_train.T @ x_train + penalty) @ x_train.T @ y_train
    return x_test @ beta


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(y) & np.isfinite(pred)
    y = y[mask]
    pred = pred[mask]
    if len(y) < 2:
        return {"rows": float(len(y)), "mae": float("nan"), "correlation": float("nan"), "r2": float("nan")}
    residual = y - pred
    denom = float(np.sum((y - y.mean()) ** 2))
    return {
        "rows": float(len(y)),
        "mae": float(np.mean(np.abs(residual))),
        "correlation": float(np.corrcoef(y, pred)[0, 1]) if np.std(pred) > 0 and np.std(y) > 0 else 0.0,
        "r2": float(1.0 - np.sum(residual**2) / denom) if denom > 0 else 0.0,
    }


def _load_nifty_sessions(root: Path, limit: int | None) -> pd.DataFrame:
    files = sorted(root.glob("sessions/*/underlying/NIFTY_*.parquet"))
    if limit:
        files = files[:limit]
    if not files:
        raise FileNotFoundError(f"no NIFTY session parquet files under {root}")
    frames: list[pd.DataFrame] = []
    for path in files:
        frame = pd.read_parquet(path)
        if "timestamp" not in frame.columns:
            for candidate in ("datetime", "date", "time"):
                if candidate in frame.columns:
                    frame = frame.rename(columns={candidate: "timestamp"})
                    break
        frame["source_file"] = str(path)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit-sessions", type=int)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source = _load_nifty_sessions(args.evidence_root, args.limit_sessions)
    states = build_market_state_frame(source)
    states["future_return_5"] = states.groupby("session_date", sort=False)["close"].shift(-5) / states["close"] - 1.0
    states["future_return_15"] = states.groupby("session_date", sort=False)["close"].shift(-15) / states["close"] - 1.0
    states["future_abs_return_15"] = states["future_return_15"].abs()

    sessions = sorted(states["session_date"].astype(str).unique())
    if len(sessions) < 30:
        verdict = "MARKET_STATE_INPUTS_INSUFFICIENT"
    else:
        verdict = "MARKET_STATE_REPRESENTATION_PARTIALLY_VALID"
    cut1 = max(1, int(len(sessions) * 0.60))
    cut2 = max(cut1 + 1, int(len(sessions) * 0.80))
    train_sessions = set(sessions[:cut1])
    validation_sessions = set(sessions[cut1:cut2])
    holdout_sessions = set(sessions[cut2:])

    contract = state_contract()
    full_features = [c for family in contract["families"].values() for c in family if c not in {"underlying_observable", "option_observable", "state_reliability"}]
    full_features = [c for c in full_features if c in states.columns and states[c].notna().mean() >= 0.50]
    baseline_features = [c for c in ["trend_return_short", "trend_return_medium", "vwap_distance_atr", "range_short_long_ratio"] if c in states.columns]

    results: dict[str, object] = {}
    for target in ("future_return_5", "future_return_15", "future_abs_return_15"):
        target_results: dict[str, object] = {}
        for name, features in (("baseline", baseline_features), ("full_state", full_features)):
            usable = states[["session_date", target, *features]].replace([np.inf, -np.inf], np.nan).dropna()
            train = usable[usable["session_date"].astype(str).isin(train_sessions)]
            holdout = usable[usable["session_date"].astype(str).isin(holdout_sessions)]
            if len(train) < 100 or len(holdout) < 50 or not features:
                target_results[name] = {"status": "insufficient", "train_rows": len(train), "holdout_rows": len(holdout)}
                continue
            mean = train[features].mean()
            std = train[features].std(ddof=0).replace(0, 1.0)
            x_train = ((train[features] - mean) / std).to_numpy(float)
            x_holdout = ((holdout[features] - mean) / std).to_numpy(float)
            pred = _ridge_fit_predict(x_train, train[target].to_numpy(float), x_holdout)
            target_results[name] = {
                "features": features,
                "train_rows": len(train),
                "holdout_rows": len(holdout),
                "metrics": _metrics(holdout[target].to_numpy(float), pred),
            }
        results[target] = target_results

    incremental_wins = 0
    for target_result in results.values():
        if not isinstance(target_result, dict):
            continue
        base = target_result.get("baseline", {})
        full = target_result.get("full_state", {})
        if isinstance(base, dict) and isinstance(full, dict) and "metrics" in base and "metrics" in full:
            if full["metrics"]["mae"] < base["metrics"]["mae"] and full["metrics"]["correlation"] > base["metrics"]["correlation"]:
                incremental_wins += 1

    if verdict != "MARKET_STATE_INPUTS_INSUFFICIENT":
        verdict = "MARKET_STATE_REPRESENTATION_PARTIALLY_VALID" if incremental_wins >= 1 else "NO_USEFUL_MARKET_STATE_REPRESENTATION_FOUND"

    report = {
        "verdict": verdict,
        "scope": "underlying-only first empirical screen; exact-option families remain unvalidated",
        "rows": int(len(states)),
        "sessions": len(sessions),
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "split": {"train": len(train_sessions), "validation": len(validation_sessions), "holdout": len(holdout_sessions)},
        "state_contract_hash": _hash(contract),
        "full_feature_count": len(full_features),
        "incremental_wins": incremental_wins,
        "results": results,
    }
    states.to_parquet(args.output_dir / "market_state_dataset_with_labels.parquet", index=False)
    (args.output_dir / "validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
