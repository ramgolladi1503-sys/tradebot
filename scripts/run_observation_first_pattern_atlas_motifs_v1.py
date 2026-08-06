#!/usr/bin/env python3
"""Discover recurring native-cadence market motifs without reading outcomes.

The input is the corrected continuous-index causal trajectory. Motifs are built
from observed native bars only, separated by instrument and CAS regime, and
frozen using chronological observation/replication recurrence. Unopened
sessions are not scored. No future return, trade direction, entry, exit, stop,
target, P&L or holdout outcome is read or calculated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "outcome_blind_native_cadence_motifs_v1"
WINDOW_MINUTES = (5, 10, 15, 30, 60)
RANDOM_STATE = 20260806

REQUIRED_COLUMNS = (
    "timestamp",
    "instrument",
    "session_date",
    "regime",
    "price",
    "volume",
    "causal_vwap",
    "session_progress",
    "observed_this_minute",
)

DENY_PATTERNS = tuple(
    re.compile(value, re.IGNORECASE)
    for value in (
        r"(^|_)(future|forward|fwd)(_|$)",
        r"(^|_)(target|stop|entry|exit)(_|$)",
        r"(^|_)(pnl|profit|loss|expectancy|drawdown|sharpe)(_|$)",
        r"(^|_)(label|outcome|winner|win_rate|hit_target|mfe|mae)(_|$)",
    )
)

VECTOR_COMPONENTS = (
    "path",
    "step_return",
    "acceleration",
    "range_position",
    "vwap_distance",
)


@dataclass(frozen=True)
class SessionSplit:
    observation: tuple[str, ...]
    replication: tuple[str, ...]
    unopened: tuple[str, ...]


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def outcome_like_columns(columns: Iterable[str]) -> list[str]:
    return sorted(
        str(column)
        for column in columns
        if any(pattern.search(str(column)) for pattern in DENY_PATTERNS)
    )


def validate_input(frame: pd.DataFrame) -> None:
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing corrected trajectory columns: {missing}")
    leaked = outcome_like_columns(frame.columns)
    if leaked:
        raise ValueError(f"Outcome-like columns reached motif stage: {leaked}")


def prepare_native_rows(frame: pd.DataFrame) -> pd.DataFrame:
    validate_input(frame)
    result = frame.loc[frame["observed_this_minute"].fillna(False).astype(bool)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce", utc=True)
    result["session_date"] = pd.to_datetime(result["session_date"], errors="coerce").dt.date
    result["instrument"] = result["instrument"].astype(str)
    result["regime"] = result["regime"].astype(str)
    for column in ("price", "volume", "causal_vwap", "session_progress"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.loc[
        result["timestamp"].notna()
        & result["session_date"].notna()
        & result["price"].gt(0)
        & result["session_progress"].between(0.0, 1.0, inclusive="both")
    ].copy()
    result = result.sort_values(
        ["instrument", "regime", "session_date", "timestamp"],
        kind="mergesort",
    ).drop_duplicates(
        ["instrument", "regime", "session_date", "timestamp"],
        keep="last",
    )
    return result.reset_index(drop=True)


def infer_native_cadence(group: pd.DataFrame) -> float:
    timestamps = pd.to_datetime(group["timestamp"], errors="coerce", utc=True)
    differences = timestamps.sort_values().diff().dt.total_seconds().div(60.0)
    finite = differences[(differences > 0) & np.isfinite(differences)]
    if finite.empty:
        return float("nan")
    return float(finite.median())


def chronological_split(
    sessions: Sequence[str],
    observation_share: float = 0.60,
    replication_share: float = 0.25,
    minimum_unopened: int = 10,
) -> SessionSplit:
    ordered = tuple(sorted(set(str(value) for value in sessions)))
    if len(ordered) < 3:
        return SessionSplit(ordered, tuple(), tuple())
    observation_count = max(1, int(math.floor(len(ordered) * observation_share)))
    replication_count = max(1, int(math.floor(len(ordered) * replication_share)))
    if len(ordered) - observation_count - replication_count < minimum_unopened:
        replication_count = max(1, len(ordered) - observation_count - minimum_unopened)
    if observation_count + replication_count >= len(ordered):
        replication_count = max(1, len(ordered) - observation_count - 1)
    return SessionSplit(
        observation=ordered[:observation_count],
        replication=ordered[observation_count : observation_count + replication_count],
        unopened=ordered[observation_count + replication_count :],
    )


def window_points(window_minutes: int, cadence_minutes: float) -> int:
    if not math.isfinite(cadence_minutes) or cadence_minutes <= 0:
        raise ValueError(f"Invalid native cadence: {cadence_minutes}")
    return max(2, int(round(window_minutes / cadence_minutes)) + 1)


def robust_standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values, dtype=float)
    median = float(np.median(finite))
    q75, q25 = np.quantile(finite, [0.75, 0.25])
    scale = float(q75 - q25)
    if not math.isfinite(scale) or scale <= 1e-12:
        scale = float(np.std(finite))
    if not math.isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    output = (values - median) / scale
    return np.nan_to_num(output, nan=0.0, posinf=8.0, neginf=-8.0).clip(-8.0, 8.0)


def motif_vector(window: pd.DataFrame) -> tuple[np.ndarray, dict[str, float]]:
    prices = pd.to_numeric(window["price"], errors="coerce").to_numpy(float)
    if len(prices) < 2 or not np.isfinite(prices).all() or np.any(prices <= 0):
        raise ValueError("Invalid motif price sequence")
    log_prices = np.log(prices)
    path = log_prices - log_prices[0]
    step_return = np.diff(log_prices, prepend=log_prices[0])
    acceleration = np.diff(step_return, prepend=step_return[0])
    running_high = np.maximum.accumulate(prices)
    running_low = np.minimum.accumulate(prices)
    denominator = running_high - running_low
    range_position = np.divide(
        prices - running_low,
        denominator,
        out=np.full_like(prices, 0.5),
        where=denominator > 0,
    )
    vwap = pd.to_numeric(window["causal_vwap"], errors="coerce").to_numpy(float)
    vwap_distance = np.divide(
        prices,
        vwap,
        out=np.ones_like(prices),
        where=np.isfinite(vwap) & (vwap > 0),
    ) - 1.0

    components = {
        "path": robust_standardize(path),
        "step_return": robust_standardize(step_return),
        "acceleration": robust_standardize(acceleration),
        "range_position": robust_standardize(range_position),
        "vwap_distance": robust_standardize(vwap_distance),
    }
    vector = np.concatenate([components[name] for name in VECTOR_COMPONENTS])
    amplitude = float(np.max(path) - np.min(path))
    net_return = float(path[-1])
    realized_volatility = float(np.std(step_return, ddof=0))
    efficiency_denominator = float(np.sum(np.abs(step_return)))
    directional_efficiency = (
        abs(net_return) / efficiency_denominator
        if efficiency_denominator > 1e-12
        else 0.0
    )
    descriptors = {
        "net_log_return": net_return,
        "amplitude_log_return": amplitude,
        "realized_volatility": realized_volatility,
        "directional_efficiency": float(np.clip(directional_efficiency, 0.0, 1.0)),
        "start_progress": float(window["session_progress"].iloc[0]),
        "end_progress": float(window["session_progress"].iloc[-1]),
    }
    return vector.astype(float), descriptors


def build_windows(
    frame: pd.DataFrame,
    window_minutes: int,
    cadence_minutes: float,
    stride_points: int | None = None,
    max_windows_per_session: int | None = 20,
) -> tuple[np.ndarray, pd.DataFrame]:
    points = window_points(window_minutes, cadence_minutes)
    stride = max(1, int(stride_points or max(1, points // 2)))
    vectors: list[np.ndarray] = []
    records: list[dict[str, Any]] = []
    for (instrument, regime, session_date), group in frame.groupby(
        ["instrument", "regime", "session_date"], sort=True
    ):
        ordered = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        starts = list(range(0, len(ordered) - points + 1, stride))
        if max_windows_per_session and len(starts) > max_windows_per_session:
            sampled = np.linspace(0, len(starts) - 1, max_windows_per_session)
            starts = [starts[index] for index in np.unique(np.rint(sampled).astype(int))]
        for start in starts:
            window = ordered.iloc[start : start + points]
            gaps = (
                pd.to_datetime(window["timestamp"], utc=True)
                .diff()
                .dt.total_seconds()
                .div(60.0)
                .dropna()
            )
            if len(gaps) and not np.allclose(
                gaps.to_numpy(float), cadence_minutes, atol=max(0.25, cadence_minutes * 0.10)
            ):
                continue
            try:
                vector, descriptors = motif_vector(window)
            except ValueError:
                continue
            vectors.append(vector)
            records.append(
                {
                    "instrument": str(instrument),
                    "regime": str(regime),
                    "session_date": str(session_date),
                    "start_timestamp": pd.Timestamp(window["timestamp"].iloc[0]).isoformat(),
                    "end_timestamp": pd.Timestamp(window["timestamp"].iloc[-1]).isoformat(),
                    "window_minutes": int(window_minutes),
                    "native_cadence_minutes": float(cadence_minutes),
                    "points": int(points),
                    "stride_points": int(stride),
                    **descriptors,
                }
            )
    if not vectors:
        return np.empty((0, len(VECTOR_COMPONENTS) * points), dtype=float), pd.DataFrame(records)
    return np.vstack(vectors), pd.DataFrame(records)


def fit_robust_scaler(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    median = np.nanmedian(values, axis=0)
    q75 = np.nanquantile(values, 0.75, axis=0)
    q25 = np.nanquantile(values, 0.25, axis=0)
    scale = q75 - q25
    fallback = np.nanstd(values, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, fallback)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, 1.0)
    median = np.where(np.isfinite(median), median, 0.0)
    return median.astype(float), scale.astype(float)


def apply_scaler(values: np.ndarray, median: np.ndarray, scale: np.ndarray) -> np.ndarray:
    output = (values - median) / scale
    return np.nan_to_num(output, nan=0.0, posinf=8.0, neginf=-8.0).clip(-8.0, 8.0)


def js_divergence(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    left = left / max(float(left.sum()), 1.0)
    right = right / max(float(right.sum()), 1.0)
    middle = 0.5 * (left + right)
    epsilon = 1e-12
    return float(
        0.5 * np.sum(left * np.log((left + epsilon) / (middle + epsilon)))
        + 0.5 * np.sum(right * np.log((right + epsilon) / (middle + epsilon)))
    )


def cluster_session_count(metadata: pd.DataFrame, labels: np.ndarray, cluster: int) -> int:
    if len(metadata) == 0:
        return 0
    return int(metadata.loc[labels == cluster, "session_date"].nunique())


def select_model(
    observation_values: np.ndarray,
    replication_values: np.ndarray,
    observation_meta: pd.DataFrame,
    replication_meta: pd.DataFrame,
    minimum_clusters: int = 5,
    maximum_clusters: int = 10,
) -> tuple[MiniBatchKMeans, list[dict[str, Any]], int]:
    if len(observation_values) < maximum_clusters * 4:
        raise ValueError("Insufficient observation windows for motif model")
    sample_size = min(1000, len(observation_values))
    rng = np.random.default_rng(RANDOM_STATE)
    sample_index = (
        np.sort(rng.choice(len(observation_values), size=sample_size, replace=False))
        if sample_size < len(observation_values)
        else np.arange(len(observation_values))
    )
    records: list[dict[str, Any]] = []
    models: dict[int, MiniBatchKMeans] = {}
    maximum = min(maximum_clusters, max(minimum_clusters, len(observation_values) // 4))
    for clusters in range(minimum_clusters, maximum + 1):
        model = MiniBatchKMeans(
            n_clusters=clusters,
            random_state=RANDOM_STATE,
            n_init=3,
            max_iter=100,
            batch_size=min(1024, max(64, len(observation_values))),
            reassignment_ratio=0.01,
        )
        observation_labels = model.fit_predict(observation_values)
        replication_labels = model.predict(replication_values)
        distinct = len(np.unique(observation_labels))
        if distinct < 2:
            continue
        silhouette = float(
            silhouette_score(
                observation_values[sample_index],
                observation_labels[sample_index],
            )
        )
        observation_counts = np.bincount(observation_labels, minlength=clusters).astype(float)
        replication_counts = np.bincount(replication_labels, minlength=clusters).astype(float)
        drifts: list[float] = []
        stable_count = 0
        cluster_records: list[dict[str, Any]] = []
        for cluster in range(clusters):
            observation_share = float(observation_counts[cluster] / len(observation_labels))
            replication_share = float(replication_counts[cluster] / len(replication_labels))
            observation_sessions = cluster_session_count(
                observation_meta, observation_labels, cluster
            )
            replication_sessions = cluster_session_count(
                replication_meta, replication_labels, cluster
            )
            if replication_counts[cluster] > 0:
                replication_centroid = np.median(
                    replication_values[replication_labels == cluster], axis=0
                )
                drift = float(
                    np.linalg.norm(replication_centroid - model.cluster_centers_[cluster])
                    / math.sqrt(replication_values.shape[1])
                )
                drifts.append(drift)
            else:
                drift = None
            share_ratio = (
                replication_share / observation_share if observation_share > 0 else 0.0
            )
            stable = bool(
                observation_share >= 0.01
                and replication_share >= 0.005
                and observation_sessions >= 20
                and replication_sessions >= 8
                and 0.25 <= share_ratio <= 4.0
                and drift is not None
                and drift <= 2.5
            )
            stable_count += int(stable)
            cluster_records.append(
                {
                    "cluster": cluster,
                    "observation_occurrences": int(observation_counts[cluster]),
                    "replication_occurrences": int(replication_counts[cluster]),
                    "observation_share": observation_share,
                    "replication_share": replication_share,
                    "replication_to_observation_share_ratio": share_ratio,
                    "observation_sessions": observation_sessions,
                    "replication_sessions": replication_sessions,
                    "replication_centroid_drift": drift,
                    "stable": stable,
                }
            )
        divergence = js_divergence(observation_counts, replication_counts)
        median_drift = float(np.median(drifts)) if drifts else 99.0
        stable_ratio = stable_count / clusters
        score = silhouette + 0.10 * stable_ratio - 0.04 * median_drift - 0.06 * divergence
        records.append(
            {
                "clusters": clusters,
                "silhouette": silhouette,
                "occupancy_js_divergence": divergence,
                "median_replication_centroid_drift": median_drift,
                "stable_clusters": stable_count,
                "stable_cluster_ratio": stable_ratio,
                "selection_score": score,
                "cluster_records": cluster_records,
            }
        )
        models[clusters] = model
    if not records:
        raise ValueError("No valid motif model could be fitted")
    selected = max(records, key=lambda item: (item["selection_score"], -item["clusters"]))
    return models[int(selected["clusters"])], records, int(selected["clusters"])


def representative_occurrences(
    values: np.ndarray,
    metadata: pd.DataFrame,
    labels: np.ndarray,
    centers: np.ndarray,
    cluster: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    indexes = np.flatnonzero(labels == cluster)
    if indexes.size == 0:
        return []
    distances = np.linalg.norm(values[indexes] - centers[cluster], axis=1)
    ordered = indexes[np.argsort(distances, kind="mergesort")[:limit]]
    fields = (
        "session_date",
        "start_timestamp",
        "end_timestamp",
        "start_progress",
        "end_progress",
        "net_log_return",
        "amplitude_log_return",
        "realized_volatility",
        "directional_efficiency",
    )
    return [
        {
            **{field: metadata.iloc[index][field] for field in fields},
            "centroid_distance": float(
                np.linalg.norm(values[index] - centers[cluster])
            ),
        }
        for index in ordered
    ]


def describe_cluster(
    metadata: pd.DataFrame,
    labels: np.ndarray,
    cluster: int,
) -> dict[str, Any]:
    selected = metadata.loc[labels == cluster]
    if selected.empty:
        return {}
    return {
        "median_start_progress": float(selected["start_progress"].median()),
        "median_end_progress": float(selected["end_progress"].median()),
        "median_net_log_return": float(selected["net_log_return"].median()),
        "median_amplitude_log_return": float(
            selected["amplitude_log_return"].median()
        ),
        "median_realized_volatility": float(
            selected["realized_volatility"].median()
        ),
        "median_directional_efficiency": float(
            selected["directional_efficiency"].median()
        ),
        "start_progress_q25": float(selected["start_progress"].quantile(0.25)),
        "start_progress_q75": float(selected["start_progress"].quantile(0.75)),
    }


def run_lane(
    native: pd.DataFrame,
    instrument: str,
    regime: str,
    minimum_sessions: int,
    windows: Sequence[int] = WINDOW_MINUTES,
    minimum_clusters: int = 5,
    maximum_clusters: int = 10,
    max_windows_per_session: int | None = 20,
) -> dict[str, Any]:
    lane = native.loc[
        native["instrument"].eq(instrument) & native["regime"].eq(regime)
    ].copy()
    sessions = tuple(sorted(str(value) for value in lane["session_date"].unique()))
    if len(sessions) < minimum_sessions:
        return {
            "instrument": instrument,
            "regime": regime,
            "verdict": "INSUFFICIENT_SESSIONS_FOR_MOTIF_DISCOVERY",
            "session_count": len(sessions),
            "minimum_sessions": minimum_sessions,
            "windows": [],
        }
    cadence_by_session = lane.groupby("session_date", observed=True).apply(
        infer_native_cadence, include_groups=False
    )
    cadence = float(cadence_by_session.median())
    if not math.isfinite(cadence) or not 1.0 <= cadence <= 15.0:
        return {
            "instrument": instrument,
            "regime": regime,
            "verdict": "UNSUPPORTED_NATIVE_CADENCE",
            "session_count": len(sessions),
            "native_cadence_minutes": cadence,
            "windows": [],
        }

    split = chronological_split(sessions)
    window_results: list[dict[str, Any]] = []
    for minutes in windows:
        values, metadata = build_windows(
            lane,
            minutes,
            cadence,
            max_windows_per_session=max_windows_per_session,
        )
        if len(metadata) == 0:
            window_results.append(
                {
                    "window_minutes": minutes,
                    "verdict": "NO_CONTIGUOUS_WINDOWS",
                }
            )
            continue
        observation_mask = metadata["session_date"].isin(split.observation).to_numpy()
        replication_mask = metadata["session_date"].isin(split.replication).to_numpy()
        unopened_mask = metadata["session_date"].isin(split.unopened).to_numpy()
        observation_values = values[observation_mask]
        replication_values = values[replication_mask]
        observation_meta = metadata.loc[observation_mask].reset_index(drop=True)
        replication_meta = metadata.loc[replication_mask].reset_index(drop=True)
        if len(observation_values) < 50 or len(replication_values) < 20:
            window_results.append(
                {
                    "window_minutes": minutes,
                    "verdict": "INSUFFICIENT_WINDOWS_AFTER_CHRONOLOGICAL_SPLIT",
                    "observation_windows": len(observation_values),
                    "replication_windows": len(replication_values),
                    "unopened_windows": int(unopened_mask.sum()),
                }
            )
            continue
        median, scale = fit_robust_scaler(observation_values)
        x_observation = apply_scaler(observation_values, median, scale)
        x_replication = apply_scaler(replication_values, median, scale)
        model, model_records, selected_clusters = select_model(
            x_observation,
            x_replication,
            observation_meta,
            replication_meta,
            minimum_clusters=minimum_clusters,
            maximum_clusters=maximum_clusters,
        )
        observation_labels = model.predict(x_observation)
        replication_labels = model.predict(x_replication)
        selected_record = next(
            item for item in model_records if item["clusters"] == selected_clusters
        )
        stable = [
            item for item in selected_record["cluster_records"] if item["stable"]
        ]
        motifs: list[dict[str, Any]] = []
        for record in stable:
            cluster = int(record["cluster"])
            motif = {
                "motif_id": f"{instrument}:{regime}:{minutes}m:M{cluster}",
                "cluster": cluster,
                **record,
                "observation_descriptor": describe_cluster(
                    observation_meta, observation_labels, cluster
                ),
                "replication_descriptor": describe_cluster(
                    replication_meta, replication_labels, cluster
                ),
                "representative_observation_occurrences": representative_occurrences(
                    x_observation,
                    observation_meta,
                    observation_labels,
                    model.cluster_centers_,
                    cluster,
                ),
                "representative_replication_occurrences": representative_occurrences(
                    x_replication,
                    replication_meta,
                    replication_labels,
                    model.cluster_centers_,
                    cluster,
                ),
            }
            motif["semantic_sha256"] = digest(motif)
            motifs.append(motif)
        window_results.append(
            {
                "window_minutes": minutes,
                "native_points": window_points(minutes, cadence),
                "stride_points": max(1, window_points(minutes, cadence) // 2),
                "verdict": (
                    "OUTCOME_BLIND_MOTIFS_FROZEN"
                    if motifs
                    else "NO_MOTIF_CLUSTER_PASSED_REPLICATION_GATES"
                ),
                "observation_windows": len(observation_values),
                "replication_windows": len(replication_values),
                "unopened_windows": int(unopened_mask.sum()),
                "selected_clusters": selected_clusters,
                "model_selection": model_records,
                "motifs": motifs,
                "scaler": {
                    "median": median.tolist(),
                    "iqr_or_fallback_scale": scale.tolist(),
                },
            }
        )
    frozen_count = sum(len(item.get("motifs", [])) for item in window_results)
    return {
        "instrument": instrument,
        "regime": regime,
        "verdict": (
            "OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN"
            if frozen_count
            else "NO_NATIVE_CADENCE_MOTIF_PASSED"
        ),
        "session_count": len(sessions),
        "native_cadence_minutes": cadence,
        "observation_sessions": list(split.observation),
        "replication_sessions": list(split.replication),
        "unopened_sessions": list(split.unopened),
        "unopened_sessions_scored": False,
        "frozen_motif_count": frozen_count,
        "windows": window_results,
    }


def build_report(catalog: dict[str, Any]) -> str:
    lines = [
        "# Observation-First Pattern Atlas — Native-Cadence Motifs V1",
        "",
        f"Principal verdict: `{catalog['principal_verdict']}`",
        "",
        "No future return, direction, entry, exit, stop, target, P&L or unopened-session outcome was read.",
        "",
    ]
    for lane in catalog["lanes"]:
        lines.extend(
            [
                f"## {lane['instrument']} / {lane['regime']}",
                "",
                f"Verdict: `{lane['verdict']}`",
                f"Sessions: `{lane.get('session_count', 0)}`",
                f"Frozen motifs: `{lane.get('frozen_motif_count', 0)}`",
                "",
            ]
        )
        for window in lane.get("windows", []):
            lines.append(
                f"- `{window['window_minutes']}m`: `{window['verdict']}`; "
                f"motifs `{len(window.get('motifs', []))}`"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--causal-trajectory", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "runtime/research/observation_first_pattern_atlas_v1/native_motifs_v1"
        ),
    )
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--minimum-sessions", type=int, default=120)
    args = parser.parse_args()

    frame = pd.read_parquet(args.causal_trajectory)
    native = prepare_native_rows(frame)
    regimes = sorted(native.loc[native["instrument"].eq(args.instrument), "regime"].unique())
    lanes = [
        run_lane(native, args.instrument, regime, args.minimum_sessions)
        for regime in regimes
    ]
    frozen_count = sum(int(lane.get("frozen_motif_count", 0)) for lane in lanes)
    catalog = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "source_path": str(args.causal_trajectory),
        "instrument": args.instrument,
        "window_minutes": list(WINDOW_MINUTES),
        "principal_verdict": (
            "OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN"
            if frozen_count
            else "NO_NATIVE_CADENCE_MOTIF_PASSED"
        ),
        "frozen_motif_count": frozen_count,
        "lanes": lanes,
        "policy": {
            "native_observed_rows_only": True,
            "regimes_mixed": False,
            "observation_replication_chronological": True,
            "unopened_sessions_scored": False,
            "outcomes_read": False,
            "future_returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "allowed_for_live_execution": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    args.output_root.mkdir(parents=True, exist_ok=True)
    stable_write(args.output_root / "native_motif_catalog.json", catalog)
    (args.output_root / "MOTIF_RESULT.md").write_text(
        build_report(catalog), encoding="utf-8"
    )
    print(json.dumps({
        "principal_verdict": catalog["principal_verdict"],
        "frozen_motif_count": frozen_count,
        "lane_count": len(lanes),
        "semantic_sha256": catalog["semantic_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
