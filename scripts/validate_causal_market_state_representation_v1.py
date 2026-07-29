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


def _fit_model(states: pd.DataFrame, target: str, features: list[str], train_sessions: set[str], test_sessions: set[str]) -> dict[str, object]:
    usable = states[["session_date", target, *features]].replace([np.inf, -np.inf], np.nan).dropna()
    train = usable[usable["session_date"].astype(str).isin(train_sessions)]
    test = usable[usable["session_date"].astype(str).isin(test_sessions)]
    if len(train) < 100 or len(test) < 50 or not features:
        return {"status": "insufficient", "train_rows": len(train), "test_rows": len(test)}
    mean = train[features].mean()
    std = train[features].std(ddof=0).replace(0, 1.0)
    pred = _ridge_fit_predict(
        ((train[features] - mean) / std).to_numpy(float),
        train[target].to_numpy(float),
        ((test[features] - mean) / std).to_numpy(float),
    )
    return {"features": features, "train_rows": len(train), "test_rows": len(test), "metrics": _metrics(test[target].to_numpy(float), pred)}


def _discover_motifs(states: pd.DataFrame, features: list[str], train_sessions: set[str], validation_sessions: set[str], holdout_sessions: set[str]) -> list[dict[str, object]]:
    target = "future_abs_return_15"
    train = states[states["session_date"].astype(str).isin(train_sessions)]
    validation = states[states["session_date"].astype(str).isin(validation_sessions)]
    holdout = states[states["session_date"].astype(str).isin(holdout_sessions)]
    motifs: list[dict[str, object]] = []
    for feature in features:
        series = train[feature].replace([np.inf, -np.inf], np.nan).dropna()
        if len(series) < 1000:
            continue
        for tail, quantile, op in (("low", 0.10, "le"), ("high", 0.90, "ge")):
            threshold = float(series.quantile(quantile))
            def evaluate(frame: pd.DataFrame) -> dict[str, float]:
                clean = frame[[feature, target]].replace([np.inf, -np.inf], np.nan).dropna()
                selected = clean[clean[feature] <= threshold] if op == "le" else clean[clean[feature] >= threshold]
                baseline = float(clean[target].mean()) if len(clean) else float("nan")
                mean = float(selected[target].mean()) if len(selected) else float("nan")
                return {"rows": float(len(selected)), "mean": mean, "baseline": baseline, "lift": mean - baseline}
            train_eval = evaluate(train)
            validation_eval = evaluate(validation)
            holdout_eval = evaluate(holdout)
            stable = (
                validation_eval["rows"] >= 300
                and holdout_eval["rows"] >= 300
                and validation_eval["lift"] > 0
                and holdout_eval["lift"] > 0
            )
            if stable:
                motifs.append({
                    "feature": feature,
                    "tail": tail,
                    "threshold": threshold,
                    "train": train_eval,
                    "validation": validation_eval,
                    "holdout": holdout_eval,
                    "minimum_lift": min(validation_eval["lift"], holdout_eval["lift"]),
                })
    motifs.sort(key=lambda row: float(row["minimum_lift"]), reverse=True)
    return motifs[:20]


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
    cut1 = max(1, int(len(sessions) * 0.60))
    cut2 = max(cut1 + 1, int(len(sessions) * 0.80))
    train_sessions = set(sessions[:cut1])
    validation_sessions = set(sessions[cut1:cut2])
    holdout_sessions = set(sessions[cut2:])

    contract = state_contract()
    excluded = {"underlying_observable", "option_observable", "state_reliability"}
    full_features = [c for family in contract["families"].values() for c in family if c not in excluded]
    full_features = [c for c in full_features if c in states.columns and states[c].replace([np.inf, -np.inf], np.nan).notna().mean() >= 0.50]
    baseline_candidates = ["trend_return_short", "trend_return_medium", "range_short_long_ratio", "range_zscore", "close_location_value"]
    baseline_features = [c for c in baseline_candidates if c in states.columns and states[c].replace([np.inf, -np.inf], np.nan).notna().mean() >= 0.50]

    results: dict[str, object] = {}
    incremental_wins = 0
    for target in ("future_return_5", "future_return_15", "future_abs_return_15"):
        target_results: dict[str, object] = {}
        for split_name, split_sessions in (("validation", validation_sessions), ("holdout", holdout_sessions)):
            baseline = _fit_model(states, target, baseline_features, train_sessions, split_sessions)
            full = _fit_model(states, target, full_features, train_sessions, split_sessions)
            target_results[split_name] = {"baseline": baseline, "full_state": full}
        valid = target_results["validation"]
        hold = target_results["holdout"]
        try:
            valid_win = valid["full_state"]["metrics"]["mae"] < valid["baseline"]["metrics"]["mae"] and valid["full_state"]["metrics"]["correlation"] > valid["baseline"]["metrics"]["correlation"]
            hold_win = hold["full_state"]["metrics"]["mae"] < hold["baseline"]["metrics"]["mae"] and hold["full_state"]["metrics"]["correlation"] > hold["baseline"]["metrics"]["correlation"]
        except KeyError:
            valid_win = hold_win = False
        if valid_win and hold_win:
            incremental_wins += 1
        results[target] = target_results

    motifs = _discover_motifs(states, full_features, train_sessions, validation_sessions, holdout_sessions)
    if len(sessions) < 30:
        verdict = "MARKET_STATE_INPUTS_INSUFFICIENT"
    elif incremental_wins >= 1 or motifs:
        verdict = "MARKET_STATE_REPRESENTATION_PARTIALLY_VALID"
    else:
        verdict = "NO_USEFUL_MARKET_STATE_REPRESENTATION_FOUND"

    report = {
        "verdict": verdict,
        "scope": "underlying-only empirical screen; exact-option execution remains unvalidated",
        "rows": int(len(states)),
        "sessions": len(sessions),
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "split": {"train": len(train_sessions), "validation": len(validation_sessions), "holdout": len(holdout_sessions)},
        "state_contract_hash": _hash(contract),
        "baseline_features": baseline_features,
        "full_feature_count": len(full_features),
        "incremental_wins": incremental_wins,
        "stable_motif_count": len(motifs),
        "stable_motifs": motifs,
        "results": results,
    }
    states.to_parquet(args.output_dir / "market_state_dataset_with_labels.parquet", index=False)
    (args.output_dir / "validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
