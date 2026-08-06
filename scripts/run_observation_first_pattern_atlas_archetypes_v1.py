#!/usr/bin/env python3
"""Freeze recurring whole-day archetypes without reading outcomes or P&L."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "outcome_blind_day_archetypes_v1"
RANDOM_STATE = 20260806
DENY = tuple(re.compile(value, re.I) for value in (
    r"(^|_)(future|forward|fwd)(_|$)", r"(^|_)(target|stop|entry|exit)(_|$)",
    r"(^|_)(pnl|profit|loss|expectancy|drawdown|sharpe)(_|$)",
    r"(^|_)(label|outcome|winner|win_rate|hit_target|mfe|mae)(_|$)",
))


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def denied(value: str) -> bool:
    return any(pattern.search(str(value)) for pattern in DENY)


def assert_outcome_blind(payload: Any, path: str = "root") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if denied(str(key)):
                raise ValueError(f"Outcome-like key in completed-session vectors: {path}.{key}")
            assert_outcome_blind(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_outcome_blind(value, f"{path}[{index}]")


def flatten_sessions(payload: dict[str, Any]) -> pd.DataFrame:
    assert_outcome_blind(payload)
    rows = []
    expected: set[str] | None = None
    for session in payload.get("sessions", []):
        features = session.get("features") or {}
        flat: dict[str, Any] = {
            "instrument": str(session.get("instrument", "")),
            "session_date": str(session.get("session_date", "")),
            "regime": str(session.get("regime", "")),
            "semantic_sha256": str(session.get("semantic_sha256", "")),
        }
        for feature in sorted(features):
            values = features[feature]
            if not isinstance(values, list):
                raise ValueError(f"Feature is not a list: {feature}")
            for index, value in enumerate(values):
                flat[f"{feature}__g{index:03d}"] = value
        columns = {key for key in flat if "__g" in key}
        expected = columns if expected is None else expected
        if columns != expected:
            raise ValueError("Completed-session vectors have inconsistent feature grids")
        rows.append(flat)
    if not rows:
        raise ValueError("No completed-session vectors")
    frame = pd.DataFrame(rows)
    frame["session_date"] = pd.to_datetime(frame["session_date"], errors="coerce")
    frame = frame.loc[frame["session_date"].notna() & frame["instrument"].ne("") & frame["regime"].isin(["PRE_CAS", "POST_CAS"])].copy()
    feature_columns = sorted(column for column in frame if "__g" in column)
    frame[feature_columns] = frame[feature_columns].apply(pd.to_numeric, errors="coerce")
    return frame.sort_values(["instrument", "regime", "session_date"], kind="mergesort").reset_index(drop=True)


def chronological_blocks(frame: pd.DataFrame, observation_share: float = 0.60, replication_share: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = frame.sort_values("session_date", kind="mergesort").reset_index(drop=True)
    total = len(ordered)
    observation_count = max(1, int(total * observation_share))
    replication_count = max(1, int(total * replication_share))
    if observation_count + replication_count >= total:
        replication_count = max(1, total - observation_count - 1)
    if observation_count + replication_count >= total:
        raise ValueError(f"Insufficient chronological sessions: {total}")
    return ordered.iloc[:observation_count].copy(), ordered.iloc[observation_count:observation_count + replication_count].copy(), ordered.iloc[observation_count + replication_count:].copy()


def fit_scaler(observation: pd.DataFrame, features: Sequence[str]) -> tuple[list[str], pd.Series, pd.Series]:
    usable, medians, scales = [], {}, {}
    for feature in features:
        values = pd.to_numeric(observation[feature], errors="coerce")
        finite = values[np.isfinite(values)]
        if len(finite) < max(5, int(len(observation) * 0.90)):
            continue
        median = float(finite.median())
        scale = float(finite.quantile(0.75) - finite.quantile(0.25))
        if math.isfinite(scale) and scale > 1e-12:
            usable.append(feature)
            medians[feature], scales[feature] = median, scale
    if len(usable) < 20:
        raise ValueError(f"Insufficient usable trajectory dimensions: {len(usable)}")
    return usable, pd.Series(medians), pd.Series(scales)


def transform(frame: pd.DataFrame, features: Sequence[str], medians: pd.Series, scales: pd.Series) -> np.ndarray:
    values = frame[list(features)].apply(pd.to_numeric, errors="coerce").fillna(medians)
    return ((values - medians).div(scales)).clip(-8, 8).to_numpy(float)


def js_divergence(left: np.ndarray, right: np.ndarray) -> float:
    left, right = left / left.sum(), right / right.sum()
    middle, eps = 0.5 * (left + right), 1e-12
    return float(0.5 * np.sum(left * np.log((left + eps) / (middle + eps))) + 0.5 * np.sum(right * np.log((right + eps) / (middle + eps))))


def candidate_ks(observation_rows: int) -> list[int]:
    maximum = min(12, max(2, observation_rows // 12))
    return list(range(2, maximum + 1))


def evaluate_models(observation: pd.DataFrame, replication: pd.DataFrame, x_observation: np.ndarray, x_replication: np.ndarray) -> tuple[KMeans, list[dict[str, Any]]]:
    records, models = [], {}
    sample_size = min(5000, len(x_observation))
    rng = np.random.default_rng(RANDOM_STATE)
    sample = np.sort(rng.choice(len(x_observation), sample_size, replace=False)) if sample_size < len(x_observation) else np.arange(len(x_observation))
    for clusters in candidate_ks(len(observation)):
        model = KMeans(n_clusters=clusters, random_state=RANDOM_STATE, n_init=30, max_iter=500)
        obs_labels = model.fit_predict(x_observation)
        rep_labels = model.predict(x_replication)
        obs_counts = np.bincount(obs_labels, minlength=clusters).astype(float)
        rep_counts = np.bincount(rep_labels, minlength=clusters).astype(float)
        cluster_records, drifts, stable = [], [], 0
        for cluster in range(clusters):
            obs_share, rep_share = obs_counts[cluster] / len(obs_labels), rep_counts[cluster] / len(rep_labels)
            if rep_counts[cluster] > 0:
                median = np.median(x_replication[rep_labels == cluster], axis=0)
                drift = float(np.linalg.norm(median - model.cluster_centers_[cluster]) / math.sqrt(x_replication.shape[1]))
                drifts.append(drift)
            else:
                drift = None
            passed = bool(obs_counts[cluster] >= 10 and rep_counts[cluster] >= 4 and obs_share >= 0.04 and rep_share >= 0.02 and drift is not None and drift <= 2.5)
            stable += int(passed)
            cluster_records.append({"cluster": cluster, "observation_count": int(obs_counts[cluster]), "replication_count": int(rep_counts[cluster]), "observation_share": float(obs_share), "replication_share": float(rep_share), "centroid_drift": drift, "stable": passed})
        silhouette = float(silhouette_score(x_observation[sample], obs_labels[sample]))
        divergence = js_divergence(obs_counts, rep_counts)
        median_drift = float(np.median(drifts)) if drifts else 99.0
        stable_ratio = stable / clusters
        score = silhouette + 0.10 * stable_ratio - 0.04 * median_drift - 0.08 * divergence
        records.append({"clusters": clusters, "silhouette": silhouette, "occupancy_js_divergence": divergence, "median_centroid_drift": median_drift, "stable_clusters": stable, "stable_cluster_ratio": stable_ratio, "selection_score": score, "cluster_records": cluster_records})
        models[clusters] = model
    if not records:
        raise ValueError("No valid K candidate")
    best = max(records, key=lambda item: (item["selection_score"], -item["clusters"]))
    return models[int(best["clusters"])], records


def representatives(frame: pd.DataFrame, matrix: np.ndarray, labels: np.ndarray, centers: np.ndarray, count: int = 5) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for cluster in range(len(centers)):
        indexes = np.where(labels == cluster)[0]
        distance = np.linalg.norm(matrix[indexes] - centers[cluster], axis=1)
        chosen = indexes[np.argsort(distance)[:count]]
        result[f"A{cluster}"] = [{"instrument": str(frame.iloc[index]["instrument"]), "session_date": frame.iloc[index]["session_date"].date().isoformat(), "distance": float(np.linalg.norm(matrix[index] - centers[cluster]))} for index in chosen]
    return result


def fit_lane(frame: pd.DataFrame, instrument: str, regime: str) -> dict[str, Any]:
    lane = frame.loc[frame["instrument"].eq(instrument) & frame["regime"].eq(regime)].copy()
    if len(lane) < 45:
        return {"instrument": instrument, "regime": regime, "verdict": "INSUFFICIENT_SESSIONS_FOR_ARCHETYPE_DISCOVERY", "sessions": len(lane), "minimum_required": 45}
    observation, replication, unopened = chronological_blocks(lane)
    all_features = sorted(column for column in lane if "__g" in column)
    features, medians, scales = fit_scaler(observation, all_features)
    x_obs, x_rep = transform(observation, features, medians, scales), transform(replication, features, medians, scales)
    model, records = evaluate_models(observation, replication, x_obs, x_rep)
    selected = next(item for item in records if item["clusters"] == model.n_clusters)
    obs_labels, rep_labels = model.predict(x_obs), model.predict(x_rep)
    stable = [f"A{item['cluster']}" for item in selected["cluster_records"] if item["stable"]]
    payload = {
        "instrument": instrument, "regime": regime,
        "verdict": "OUTCOME_BLIND_DAY_ARCHETYPES_FROZEN" if stable else "NO_STABLE_DAY_ARCHETYPE_FOUND",
        "observation_sessions": len(observation), "replication_sessions": len(replication), "unopened_sessions": len(unopened),
        "observation_date_range": [observation["session_date"].min().date().isoformat(), observation["session_date"].max().date().isoformat()],
        "replication_date_range": [replication["session_date"].min().date().isoformat(), replication["session_date"].max().date().isoformat()],
        "unopened_date_range": [unopened["session_date"].min().date().isoformat(), unopened["session_date"].max().date().isoformat()],
        "selected_clusters": model.n_clusters, "stable_archetype_ids": stable,
        "features": features, "medians": {key: float(medians[key]) for key in features}, "iqrs": {key: float(scales[key]) for key in features},
        "model_selection": records, "centroids": {f"A{index}": center.tolist() for index, center in enumerate(model.cluster_centers_)},
        "observation_representatives": representatives(observation, x_obs, obs_labels, model.cluster_centers_),
        "replication_representatives": representatives(replication, x_rep, rep_labels, model.cluster_centers_),
        "outcomes_read": False, "pnl_calculated": False, "allowed_for_live_execution": False,
    }
    payload["semantic_sha256"] = digest(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory-vectors", type=Path, default=Path("runtime/research/observation_first_pattern_atlas_v1/trajectory/completed_session_vectors.json"))
    parser.add_argument("--output-root", type=Path, default=Path("runtime/research/observation_first_pattern_atlas_v1/archetypes"))
    args = parser.parse_args()
    payload = json.loads(args.trajectory_vectors.read_text(encoding="utf-8"))
    frame = flatten_sessions(payload)
    lanes = [fit_lane(frame, instrument, regime) for instrument in sorted(frame["instrument"].unique()) for regime in ("PRE_CAS", "POST_CAS") if len(frame.loc[frame["instrument"].eq(instrument) & frame["regime"].eq(regime)])]
    result = {"schema_version": 1, "campaign": CAMPAIGN, "stage": STAGE, "lanes": lanes, "policy": {"chronological_observation_replication_unopened": True, "scaler_fit_on_observation_only": True, "pre_cas_post_cas_separate": True, "outcomes_read": False, "pnl_calculated": False, "direction_selected": False, "allowed_for_live_execution": False}}
    result["principal_verdict"] = "OUTCOME_BLIND_ARCHETYPE_LANES_COMPLETE" if any(lane["verdict"] == "OUTCOME_BLIND_DAY_ARCHETYPES_FROZEN" for lane in lanes) else "NO_ARCHETYPE_LANE_PASSED"
    result["semantic_sha256"] = digest(result)
    stable_write(args.output_root / "day_archetype_catalog.json", result)
    print(json.dumps({"principal_verdict": result["principal_verdict"], "lanes": [{"instrument": lane["instrument"], "regime": lane["regime"], "verdict": lane["verdict"], "sessions": lane.get("sessions", lane.get("observation_sessions", 0) + lane.get("replication_sessions", 0) + lane.get("unopened_sessions", 0))} for lane in lanes]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
