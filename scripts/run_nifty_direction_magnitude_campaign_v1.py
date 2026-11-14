from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.ml_strategy_discovery.features import compute_causal_features
from research.nifty_option_edge.contracts import ForwardMoveLabelConfig
from research.nifty_option_edge.underlying_labels import compute_forward_move_labels

EXPECTED_ARCHIVE_SHA256 = "4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707"
SOURCE_TIMEZONE = "Asia/Kolkata"
SESSION_ROWS = 375
SESSION_START = "09:15"
SESSION_END = "15:29"
HORIZONS = (15, 20, 30)
PROBABILITY_GATES = (0.55, 0.60, 0.65, 0.70)
MOVE_GATES = (15.0, 25.0, 40.0, 60.0)
SEED = 20260906


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_symbol(value: Any) -> str:
    text = str(value or "").upper().strip().replace("_", " ")
    if "NIFTY BANK" in text or "BANKNIFTY" in text:
        return "BANKNIFTY"
    if "NIFTY 50" in text or text == "NIFTY" or text.endswith("|NIFTY"):
        return "NIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return text.replace(" ", "")


def parse_local_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="raise")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize(SOURCE_TIMEZONE, ambiguous="raise", nonexistent="raise")
    return parsed.dt.tz_convert(SOURCE_TIMEZONE)


def validate_nifty_session(frame: pd.DataFrame, path: str) -> pd.DataFrame:
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns path={path} missing={sorted(missing)}")
    if len(frame) != SESSION_ROWS:
        raise ValueError(f"incomplete session path={path} rows={len(frame)}")
    out = frame.copy()
    out["timestamp"] = parse_local_timestamp(out["timestamp"])
    if out["timestamp"].duplicated().any() or not out["timestamp"].is_monotonic_increasing:
        raise ValueError(f"invalid timestamp order path={path}")
    deltas = out["timestamp"].diff().dropna()
    if not (deltas == pd.Timedelta(minutes=1)).all():
        raise ValueError(f"non-1m cadence path={path}")
    if out["timestamp"].iloc[0].strftime("%H:%M") != SESSION_START or out["timestamp"].iloc[-1].strftime("%H:%M") != SESSION_END:
        raise ValueError(f"session bounds mismatch path={path}")
    symbols = {normalize_symbol(v) for v in out["symbol"].dropna().unique()}
    if symbols != {"NIFTY"}:
        raise ValueError(f"symbol mismatch path={path} symbols={sorted(symbols)}")
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="raise")
    values = out[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite OHLCV path={path}")
    if (out[["open", "high", "low", "close"]] <= 0).any().any() or (out["volume"] < 0).any():
        raise ValueError(f"invalid OHLCV sign path={path}")
    if (out["high"] < out[["open", "close", "low"]].max(axis=1)).any() or (out["low"] > out[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"OHLC ordering violation path={path}")
    session_date = out["timestamp"].iloc[0].date().isoformat()
    if any(ts.date().isoformat() != session_date for ts in out["timestamp"]):
        raise ValueError(f"cross-date session path={path}")
    out["session_date"] = session_date
    out["bar_start_timestamp"] = out["timestamp"].dt.tz_convert("UTC")
    out["bar_end_timestamp"] = (out["timestamp"] + pd.Timedelta(minutes=1)).dt.tz_convert("UTC")
    out["decision_timestamp"] = out["bar_end_timestamp"]
    out["source_archive_member"] = path
    return out


def load_nifty_from_archive(archive_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    actual_hash = sha256_file(archive_path)
    if actual_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError(f"archive hash mismatch expected={EXPECTED_ARCHIVE_SHA256} actual={actual_hash}")
    sessions: dict[str, pd.DataFrame] = {}
    members_used: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith(".parquet")
            and "/underlying/" in info.filename.lower()
            and not info.filename.startswith("__MACOSX/")
            and not Path(info.filename).name.startswith("._")
        ]
        for info in sorted(candidates, key=lambda x: x.filename):
            frame = pd.read_parquet(io.BytesIO(archive.read(info)))
            if "symbol" not in frame.columns:
                continue
            normalized = {normalize_symbol(v) for v in frame["symbol"].dropna().unique()}
            if normalized != {"NIFTY"} or len(frame) != SESSION_ROWS:
                continue
            verified = validate_nifty_session(frame, info.filename)
            session_date = str(verified["session_date"].iloc[0])
            if session_date in sessions:
                raise ValueError(f"duplicate complete NIFTY session in archive: {session_date}")
            sessions[session_date] = verified
            members_used.append(info.filename)
    if len(sessions) < 100:
        raise ValueError(f"insufficient complete NIFTY sessions: {len(sessions)}")
    ordered_dates = sorted(sessions)
    bars = pd.concat([sessions[d] for d in ordered_dates], ignore_index=True)
    manifest = {
        "archive_sha256": actual_hash,
        "session_count": len(ordered_dates),
        "row_count": int(len(bars)),
        "first_session": ordered_dates[0],
        "last_session": ordered_dates[-1],
        "member_count": len(members_used),
        "member_manifest_sha256": hashlib.sha256("\n".join(members_used).encode("utf-8")).hexdigest(),
    }
    return bars, manifest


def split_sessions(session_dates: list[str]) -> dict[str, list[str]]:
    n = len(session_dates)
    dev_end = int(n * 0.60)
    val_end = int(n * 0.80)
    if not 0 < dev_end < val_end < n:
        raise ValueError("invalid split")
    return {
        "DEVELOPMENT": session_dates[:dev_end],
        "VALIDATION": session_dates[dev_end:val_end],
        "HOLDOUT_LOCKED": session_dates[val_end:],
    }


def model_factories() -> tuple[dict[str, Callable[[], Any]], dict[str, Callable[[], Any]]]:
    direction = {
        "logistic_l2": lambda: Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=1.0, max_iter=1200, solver="lbfgs", random_state=SEED)),
        ]),
        "hist_gb_classifier": lambda: Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingClassifier(max_iter=140, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=SEED)),
        ]),
    }
    magnitude = {
        "ridge": lambda: Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]),
        "hist_gb_regressor": lambda: Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(max_iter=140, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=SEED)),
        ]),
    }
    return direction, magnitude


def direction_metrics(y: np.ndarray, probability_up: np.ndarray) -> dict[str, float]:
    predicted = probability_up >= 0.5
    return {
        "accuracy": float(accuracy_score(y, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "brier": float(brier_score_loss(y, probability_up)),
    }


def magnitude_metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    corr = float(np.corrcoef(y, pred)[0, 1]) if len(y) > 1 and np.std(y) > 0 and np.std(pred) > 0 else float("nan")
    return {
        "mae_points": float(mean_absolute_error(y, pred)),
        "rmse_points": float(math.sqrt(mean_squared_error(y, pred))),
        "pearson": corr,
    }


def nonoverlap_indices(frame: pd.DataFrame, eligible: np.ndarray, horizon: int) -> np.ndarray:
    selected: list[int] = []
    work = frame.reset_index(drop=True)
    eligible = np.asarray(eligible, dtype=bool)
    for _, group in work.groupby("session_date", sort=False):
        next_allowed: pd.Timestamp | None = None
        for idx in group.index:
            if not eligible[idx]:
                continue
            ts = pd.Timestamp(work.loc[idx, "decision_timestamp"])
            if next_allowed is not None and ts < next_allowed:
                continue
            selected.append(int(idx))
            next_allowed = ts + pd.Timedelta(minutes=horizon)
    return np.asarray(selected, dtype=int)


def event_metrics(frame: pd.DataFrame, event_idx: np.ndarray, pred_sign: np.ndarray, actual_move: np.ndarray, move_gate: float) -> dict[str, Any]:
    if len(event_idx) == 0:
        return {"events": 0, "sessions": 0}
    directed = pred_sign[event_idx] * actual_move[event_idx]
    event_sessions = frame.iloc[event_idx]["session_date"].astype(str).to_numpy()
    accuracy = float(np.mean(directed > 0))
    per_session = pd.DataFrame({"session": event_sessions, "directed": directed}).groupby("session")["directed"].mean()
    return {
        "events": int(len(event_idx)),
        "sessions": int(len(per_session)),
        "direction_accuracy": accuracy,
        "mean_directed_points": float(np.mean(directed)),
        "median_directed_points": float(np.median(directed)),
        "directed_ge_gate_rate": float(np.mean(directed >= float(move_gate))),
        "session_mean_directed_points": float(per_session.mean()),
        "session_std_directed_points": float(per_session.std(ddof=1)) if len(per_session) > 1 else 0.0,
    }


def bootstrap_session_ci(frame: pd.DataFrame, event_idx: np.ndarray, pred_sign: np.ndarray, actual_move: np.ndarray, *, iterations: int = 1000) -> tuple[float, float]:
    if len(event_idx) == 0:
        return float("nan"), float("nan")
    event_sessions = frame.iloc[event_idx]["session_date"].astype(str).to_numpy()
    directed = pred_sign[event_idx] * actual_move[event_idx]
    session_values = pd.DataFrame({"session": event_sessions, "directed": directed}).groupby("session")["directed"].mean().to_numpy(dtype=float)
    if len(session_values) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(SEED)
    means = np.empty(iterations, dtype=float)
    for i in range(iterations):
        sample = rng.choice(session_values, size=len(session_values), replace=True)
        means[i] = float(np.mean(sample))
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def permutation_p_value(event_idx: np.ndarray, pred_sign: np.ndarray, actual_move: np.ndarray, *, iterations: int = 500) -> float:
    if len(event_idx) < 2:
        return float("nan")
    signs = pred_sign[event_idx]
    moves = actual_move[event_idx]
    observed = float(np.mean(signs * moves))
    rng = np.random.default_rng(SEED + 17)
    count = 1
    for _ in range(iterations):
        null = float(np.mean(signs * rng.permutation(moves)))
        if null >= observed:
            count += 1
    return float(count / (iterations + 1))


def choose_gate(selection_frame: pd.DataFrame, p_up: np.ndarray, predicted_move: np.ndarray, actual_move: np.ndarray, horizon: int, baseline_accuracy: float) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    pred_sign = np.where(p_up >= 0.5, 1.0, -1.0)
    p_direction = np.where(pred_sign > 0, p_up, 1.0 - p_up)
    agreement = np.sign(predicted_move) == pred_sign
    rows: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for p_gate in PROBABILITY_GATES:
        for move_gate in MOVE_GATES:
            eligible = agreement & (p_direction >= p_gate) & (np.abs(predicted_move) >= move_gate)
            idx = nonoverlap_indices(selection_frame, eligible, horizon)
            metrics = event_metrics(selection_frame, idx, pred_sign, actual_move, move_gate)
            row = {"probability_gate": p_gate, "move_gate_points": move_gate, **metrics}
            if metrics.get("events", 0) >= 100 and metrics.get("sessions", 0) >= 20:
                improvement = float(metrics["direction_accuracy"] - baseline_accuracy)
                mean_directed = float(metrics["mean_directed_points"])
                row["eligible_for_freeze"] = bool(improvement >= 0.01 and mean_directed > 0)
                row["dev_selection_score"] = float(mean_directed * math.sqrt(max(1, metrics["sessions"]))) if row["eligible_for_freeze"] else float("-inf")
                if row["eligible_for_freeze"] and (best is None or row["dev_selection_score"] > best["dev_selection_score"]):
                    best = dict(row)
            else:
                row["eligible_for_freeze"] = False
                row["dev_selection_score"] = float("-inf")
            rows.append(row)
    return best, rows


def build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# NIFTY Direction + Magnitude Campaign V1",
        "",
        f"Archive SHA-256: `{summary['source']['archive_sha256']}`",
        f"Complete NIFTY sessions: **{summary['source']['session_count']}** ({summary['source']['first_session']} → {summary['source']['last_session']})",
        "",
        "## Split",
        "",
        f"- DEVELOPMENT: {summary['split']['development_sessions']} sessions",
        f"- VALIDATION: {summary['split']['validation_sessions']} sessions",
        f"- HOLDOUT_LOCKED: {summary['split']['holdout_sessions']} sessions / {summary['split']['holdout_raw_rows']} raw bars",
        f"- holdout labels computed: **{str(summary['split']['holdout_labels_computed']).lower()}**",
        "",
        "## Results",
        "",
    ]
    for horizon in HORIZONS:
        result = summary["horizons"][str(horizon)]
        lines.extend([
            f"### {horizon} minutes",
            f"- frozen direction model: `{result['frozen_direction_model']}`",
            f"- frozen magnitude model: `{result['frozen_magnitude_model']}`",
            f"- validation direction accuracy: {result['validation']['direction']['accuracy']:.4f} (constant baseline {result['validation']['direction_baseline']['accuracy']:.4f})",
            f"- validation Brier: {result['validation']['direction']['brier']:.4f} (constant baseline {result['validation']['direction_baseline']['brier']:.4f})",
            f"- validation magnitude MAE: {result['validation']['magnitude']['mae_points']:.3f} pts (constant-mean baseline {result['validation']['magnitude_baseline']['mae_points']:.3f})",
            f"- frozen DEV gate: `{result['frozen_gate']}`",
            f"- verdict: **{result['verdict']}**",
            "",
        ])
        if result.get("validation_gate"):
            g = result["validation_gate"]
            lines.extend([
                f"  - non-overlapping validation events: {g['events']} across {g['sessions']} sessions",
                f"  - event direction accuracy: {g['direction_accuracy']:.4f}",
                f"  - mean directed move: {g['mean_directed_points']:.3f} pts",
                f"  - session-bootstrap 95% CI: [{g['bootstrap_ci_low']:.3f}, {g['bootstrap_ci_high']:.3f}]",
                f"  - label-permutation p-value: {g['permutation_p_value']:.4f}",
                "",
            ])
    lines.extend([
        "## Claim boundary",
        "",
        "This campaign evaluates **underlying NIFTY direction and movement magnitude only**. It does not certify CE/PE profitability, strike-level expectancy, or executable option P&L. The chronological holdout remains sealed for a later frozen-candidate test.",
        "",
    ])
    return "\n".join(lines)


def run(archive_path: Path, output_dir: Path) -> dict[str, Any]:
    bars, source_manifest = load_nifty_from_archive(archive_path)
    session_dates = sorted(bars["session_date"].unique().tolist())
    split = split_sessions(session_dates)
    dev_sessions = split["DEVELOPMENT"]
    validation_sessions = split["VALIDATION"]
    holdout_sessions = split["HOLDOUT_LOCKED"]

    # Critically, holdout bars are counted only. No forward labels are computed for them.
    holdout_raw_rows = int(bars["session_date"].isin(holdout_sessions).sum())
    preholdout = bars[bars["session_date"].isin(dev_sessions + validation_sessions)].copy().reset_index(drop=True)
    features = compute_causal_features(preholdout, opening_range_bars=15)
    labels = compute_forward_move_labels(preholdout, config=ForwardMoveLabelConfig(horizons_minutes=HORIZONS, move_thresholds_points=MOVE_GATES, bar_interval_minutes=1))
    metadata = preholdout[["session_date", "decision_timestamp"]].reset_index(drop=True)
    feature_names = [c for c in features.columns if pd.api.types.is_numeric_dtype(features[c])]
    data = pd.concat([metadata, features.reset_index(drop=True), labels.drop(columns=["decision_timestamp"]).reset_index(drop=True)], axis=1)

    dev_set = set(dev_sessions)
    validation_set = set(validation_sessions)
    inner_end = int(len(dev_sessions) * 0.80)
    fit_sessions = set(dev_sessions[:inner_end])
    selection_sessions = set(dev_sessions[inner_end:])
    if len(selection_sessions) < 20:
        raise ValueError("insufficient DEV selection sessions")

    direction_factories, magnitude_factories = model_factories()
    horizon_results: dict[str, Any] = {}
    validation_rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []

    for horizon in HORIZONS:
        prefix = f"fwd_{horizon}m"
        measured = data[f"{prefix}_status"].eq("MEASURED")
        horizon_frame = data.loc[measured].copy().reset_index(drop=True)
        actual_move = horizon_frame[f"{prefix}_signed_points"].to_numpy(dtype=float)
        y_direction = actual_move > 0

        fit_mask = horizon_frame["session_date"].isin(fit_sessions).to_numpy()
        selection_mask = horizon_frame["session_date"].isin(selection_sessions).to_numpy()
        dev_mask = horizon_frame["session_date"].isin(dev_set).to_numpy()
        validation_mask = horizon_frame["session_date"].isin(validation_set).to_numpy()

        candidate_features = [
            c for c in feature_names
            if c in horizon_frame.columns and np.isfinite(pd.to_numeric(horizon_frame.loc[fit_mask, c], errors="coerce").to_numpy(dtype=float)).any()
        ]
        if len(candidate_features) < 10:
            raise ValueError(f"too few usable features horizon={horizon}: {len(candidate_features)}")
        X = horizon_frame[candidate_features]
        X_fit, X_sel, X_dev, X_val = X.loc[fit_mask], X.loc[selection_mask], X.loc[dev_mask], X.loc[validation_mask]
        y_fit_dir, y_sel_dir, y_dev_dir, y_val_dir = y_direction[fit_mask], y_direction[selection_mask], y_direction[dev_mask], y_direction[validation_mask]
        y_fit_move, y_sel_move, y_dev_move, y_val_move = actual_move[fit_mask], actual_move[selection_mask], actual_move[dev_mask], actual_move[validation_mask]

        direction_selection: list[dict[str, Any]] = []
        selected_direction_name: str | None = None
        selected_direction_score = float("inf")
        for name, factory in direction_factories.items():
            model = factory()
            model.fit(X_fit, y_fit_dir)
            p = model.predict_proba(X_sel)[:, 1]
            metrics = direction_metrics(y_sel_dir, p)
            direction_selection.append({"model": name, **metrics})
            if metrics["brier"] < selected_direction_score:
                selected_direction_score = metrics["brier"]
                selected_direction_name = name
        assert selected_direction_name is not None

        magnitude_selection: list[dict[str, Any]] = []
        selected_magnitude_name: str | None = None
        selected_magnitude_score = float("inf")
        for name, factory in magnitude_factories.items():
            model = factory()
            model.fit(X_fit, y_fit_move)
            pred = model.predict(X_sel)
            metrics = magnitude_metrics(y_sel_move, pred)
            magnitude_selection.append({"model": name, **metrics})
            if metrics["mae_points"] < selected_magnitude_score:
                selected_magnitude_score = metrics["mae_points"]
                selected_magnitude_name = name
        assert selected_magnitude_name is not None

        # Refit selected pair on DEV after model family was chosen entirely within DEV.
        direction_model = direction_factories[selected_direction_name]()
        magnitude_model = magnitude_factories[selected_magnitude_name]()
        direction_model.fit(X_dev, y_dev_dir)
        magnitude_model.fit(X_dev, y_dev_move)

        # Gate is frozen using the DEV selection tail and models trained only on DEV-fit.
        gate_dir_model = direction_factories[selected_direction_name]()
        gate_mag_model = magnitude_factories[selected_magnitude_name]()
        gate_dir_model.fit(X_fit, y_fit_dir)
        gate_mag_model.fit(X_fit, y_fit_move)
        p_sel = gate_dir_model.predict_proba(X_sel)[:, 1]
        move_sel = gate_mag_model.predict(X_sel)
        selection_frame = horizon_frame.loc[selection_mask, ["session_date", "decision_timestamp"]].reset_index(drop=True)
        constant_p_fit = float(np.mean(y_fit_dir))
        selection_baseline_accuracy = float(max(np.mean(y_sel_dir), 1.0 - np.mean(y_sel_dir)))
        frozen_gate, selection_gate_rows = choose_gate(selection_frame, p_sel, move_sel, y_sel_move, horizon, selection_baseline_accuracy)
        for row in selection_gate_rows:
            gate_rows.append({"horizon_minutes": horizon, "stage": "DEV_SELECTION", **row})

        p_val = direction_model.predict_proba(X_val)[:, 1]
        move_val = magnitude_model.predict(X_val)
        val_direction = direction_metrics(y_val_dir, p_val)
        constant_p_dev = float(np.mean(y_dev_dir))
        baseline_prob = np.full(len(y_val_dir), constant_p_dev, dtype=float)
        val_direction_baseline = direction_metrics(y_val_dir, baseline_prob)
        val_magnitude = magnitude_metrics(y_val_move, move_val)
        constant_move_dev = float(np.mean(y_dev_move))
        val_magnitude_baseline = magnitude_metrics(y_val_move, np.full(len(y_val_move), constant_move_dev, dtype=float))

        validation_frame = horizon_frame.loc[validation_mask, ["session_date", "decision_timestamp"]].reset_index(drop=True)
        validation_gate: dict[str, Any] | None = None
        verdict = "NO_DEV_GATE_CANDIDATE"
        frozen_gate_repr = "NONE"
        if frozen_gate is not None:
            p_gate = float(frozen_gate["probability_gate"])
            move_gate = float(frozen_gate["move_gate_points"])
            frozen_gate_repr = f"P_DIRECTION>={p_gate:.2f} AND ABS_EXPECTED_MOVE>={move_gate:.0f} AND MODEL_SIGN_AGREEMENT"
            pred_sign = np.where(p_val >= 0.5, 1.0, -1.0)
            p_direction = np.where(pred_sign > 0, p_val, 1.0 - p_val)
            agreement = np.sign(move_val) == pred_sign
            eligible = agreement & (p_direction >= p_gate) & (np.abs(move_val) >= move_gate)
            event_idx = nonoverlap_indices(validation_frame, eligible, horizon)
            validation_gate = event_metrics(validation_frame, event_idx, pred_sign, y_val_move, move_gate)
            ci_low, ci_high = bootstrap_session_ci(validation_frame, event_idx, pred_sign, y_val_move)
            validation_gate["bootstrap_ci_low"] = ci_low
            validation_gate["bootstrap_ci_high"] = ci_high
            validation_gate["permutation_p_value"] = permutation_p_value(event_idx, pred_sign, y_val_move)
            validation_gate["probability_gate"] = p_gate
            validation_gate["move_gate_points"] = move_gate
            gate_rows.append({"horizon_minutes": horizon, "stage": "VALIDATION_FROZEN_GATE", **validation_gate})

            baseline_accuracy = float(val_direction_baseline["accuracy"])
            passes = (
                validation_gate.get("events", 0) >= 100
                and validation_gate.get("sessions", 0) >= 30
                and validation_gate.get("direction_accuracy", 0.0) >= max(0.50, baseline_accuracy) + 0.01
                and validation_gate.get("mean_directed_points", 0.0) > 0.0
                and np.isfinite(ci_low) and ci_low > 0.0
                and validation_gate.get("permutation_p_value", 1.0) <= 0.05
                and val_direction["brier"] < val_direction_baseline["brier"]
            )
            verdict = "UNDERLYING_VALIDATION_CANDIDATE_OPTION_PNL_BLOCKED" if passes else "VALIDATION_GATE_FAILED"

        result = {
            "horizon_minutes": horizon,
            "feature_count": len(candidate_features),
            "feature_names": candidate_features,
            "fit_sessions": len(fit_sessions),
            "selection_sessions": len(selection_sessions),
            "development_rows": int(dev_mask.sum()),
            "validation_rows": int(validation_mask.sum()),
            "frozen_direction_model": selected_direction_name,
            "frozen_magnitude_model": selected_magnitude_name,
            "direction_model_selection": direction_selection,
            "magnitude_model_selection": magnitude_selection,
            "frozen_gate": frozen_gate_repr,
            "dev_gate_selection": frozen_gate,
            "validation": {
                "direction": val_direction,
                "direction_baseline": val_direction_baseline,
                "magnitude": val_magnitude,
                "magnitude_baseline": val_magnitude_baseline,
            },
            "validation_gate": validation_gate,
            "verdict": verdict,
        }
        horizon_results[str(horizon)] = result
        validation_rows.append({
            "horizon_minutes": horizon,
            "direction_model": selected_direction_name,
            "magnitude_model": selected_magnitude_name,
            "accuracy": val_direction["accuracy"],
            "baseline_accuracy": val_direction_baseline["accuracy"],
            "brier": val_direction["brier"],
            "baseline_brier": val_direction_baseline["brier"],
            "magnitude_mae_points": val_magnitude["mae_points"],
            "baseline_magnitude_mae_points": val_magnitude_baseline["mae_points"],
            "frozen_gate": frozen_gate_repr,
            "verdict": verdict,
        })

    summary = {
        "schema_version": "nifty_direction_magnitude_campaign_v1",
        "research_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "holdout_outcomes_read": False,
        "option_pnl_evaluated": False,
        "source": source_manifest,
        "split": {
            "development_sessions": len(dev_sessions),
            "validation_sessions": len(validation_sessions),
            "holdout_sessions": len(holdout_sessions),
            "holdout_raw_rows": holdout_raw_rows,
            "holdout_labels_computed": False,
            "development_first": dev_sessions[0],
            "development_last": dev_sessions[-1],
            "validation_first": validation_sessions[0],
            "validation_last": validation_sessions[-1],
            "holdout_first": holdout_sessions[0],
            "holdout_last": holdout_sessions[-1],
        },
        "horizons": horizon_results,
        "claim_boundary": "UNDERLYING_DIRECTION_AND_MAGNITUDE_ONLY",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    pd.DataFrame(validation_rows).to_csv(output_dir / "validation_metrics.csv", index=False)
    pd.DataFrame(gate_rows).to_csv(output_dir / "selective_gates.csv", index=False)
    (output_dir / "report.md").write_text(build_report(summary), encoding="utf-8")
    hashes = {}
    for name in ("summary.json", "validation_metrics.csv", "selective_gates.csv", "report.md"):
        hashes[name] = sha256_file(output_dir / name)
    (output_dir / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="runtime/upstox_candidate_replay.zip")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    summary = run(Path(args.archive), Path(args.output_dir))
    print(f"SOURCE_SESSIONS={summary['source']['session_count']}")
    print(f"SOURCE_RANGE={summary['source']['first_session']}..{summary['source']['last_session']}")
    print(f"SPLIT={summary['split']}")
    for horizon in HORIZONS:
        result = summary["horizons"][str(horizon)]
        print(f"HORIZON_{horizon}_VERDICT={result['verdict']}")
        print(f"HORIZON_{horizon}_MODELS={result['frozen_direction_model']}+{result['frozen_magnitude_model']}")
        print(f"HORIZON_{horizon}_GATE={result['frozen_gate']}")
        print(f"HORIZON_{horizon}_VALIDATION={json.dumps(result['validation'], sort_keys=True)}")
        if result.get("validation_gate"):
            print(f"HORIZON_{horizon}_VALIDATION_GATE={json.dumps(result['validation_gate'], sort_keys=True)}")
    print("HOLDOUT_LABELS_COMPUTED=false")
    print("OPTION_PNL_EVALUATED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
