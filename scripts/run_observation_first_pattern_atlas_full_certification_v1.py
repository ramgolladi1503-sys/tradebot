#!/usr/bin/env python3
"""Complete Pattern Atlas PRE-CAS certification from transitions through shadow gate.

Stages implemented here:
  5  pattern-of-pattern transition graph (outcome blind)
  6  mechanism hypothesis freeze (outcome blind)
  7  causal outcome attachment on observation/replication only
  8  structural-edge screening
  9  canonical signal-strategy construction
  10 chronological fixed-rule walk-forward stability audit
  11 robustness attacks
  12 one-shot unopened-session final test, only for robustness survivors
  13 contemporaneous option-translation evidence gate
  14 shadow-authorization gate

The script never calls a broker and never mutates live, paper, strategy registry,
risk, execution, or ranking behavior. POST_CAS is never pooled with PRE_CAS.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "pre_cas_full_edge_certification_v1"
TARGET_REGIME = "PRE_CAS"
WINDOWS = (5, 10, 15, 30, 60)
COST_BPS = 5.0
ROBUST_COST_BPS = 10.0
BOOTSTRAP_DRAWS = 2000
RANDOM_STATE = 20260807


def load_sibling(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


A = load_sibling(
    "pattern_atlas_analogues_v1_for_full_certification",
    "run_observation_first_pattern_atlas_analogues_v1.py",
)
A2 = load_sibling(
    "pattern_atlas_analogues_v2_for_full_certification",
    "run_observation_first_pattern_atlas_analogues_v2.py",
)
MOTIF = A.MOTIF
BASE = A.BASE
V3 = A.V3


@dataclass
class WindowState:
    minutes: int
    points: int
    cadence: float
    window_record: dict[str, Any]
    values: np.ndarray
    metadata: pd.DataFrame
    x_values: np.ndarray
    model: Any
    labels: np.ndarray
    split_name: np.ndarray
    motif_by_cluster: dict[int, dict[str, Any]]
    full_threshold_by_cluster: dict[int, float]
    prefix_threshold_by_cluster: dict[int, float]


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_inputs(
    motif_catalog: dict[str, Any], analogue_catalog: dict[str, Any], instrument: str
) -> dict[str, Any]:
    lane = A2.validate_recertified_catalog(motif_catalog, instrument, TARGET_REGIME)
    if motif_catalog.get("principal_verdict") != "OUTCOME_BLIND_TRAJECTORY_ACCEPTED_MOTIFS_RECERTIFIED":
        raise ValueError("Recertified motif catalog does not hold the required principal verdict")
    policy = dict(analogue_catalog.get("policy") or {})
    if analogue_catalog.get("principal_verdict") != "PRE_CAS_MATCHED_GEOMETRIC_ANALOGUES_FROZEN":
        raise ValueError("Matched analogue catalog is not frozen")
    if any(
        policy.get(key) is True
        for key in (
            "future_returns_calculated",
            "trade_outcomes_read",
            "pnl_calculated",
            "direction_selected",
            "unopened_sessions_scored",
        )
    ):
        raise ValueError("Matched analogue catalog is outside outcome-blind authority")
    if analogue_catalog.get("source_motif_catalog_sha256") != motif_catalog.get(
        "semantic_sha256"
    ):
        raise ValueError("Analogue catalog does not reference the recertified motif authority")
    return lane


def masks_for_metadata(metadata: pd.DataFrame, lane: dict[str, Any]) -> dict[str, np.ndarray]:
    dates = metadata["session_date"].astype(str)
    result = {}
    for key, field in (
        ("observation", "observation_sessions"),
        ("replication", "replication_sessions"),
        ("unopened", "unopened_sessions"),
    ):
        result[key] = dates.isin(set(map(str, lane.get(field, [])))).to_numpy()
    return result


def reconstruct_window_states(
    native_lane: pd.DataFrame, lane: dict[str, Any]
) -> dict[int, WindowState]:
    states: dict[int, WindowState] = {}
    cadence = float(lane["native_cadence_minutes"])
    for window_record in lane.get("windows", []):
        motifs = list(window_record.get("motifs", []))
        if not motifs:
            continue
        minutes = int(window_record["window_minutes"])
        values, metadata = MOTIF.build_windows(
            native_lane,
            minutes,
            cadence,
            max_windows_per_session=20,
        )
        split_masks = masks_for_metadata(metadata, lane)
        observation_values = values[split_masks["observation"]]
        replication_values = values[split_masks["replication"]]
        scaler = dict(window_record["scaler"])
        median = np.asarray(scaler["median"], dtype=float)
        scale = np.asarray(scaler["iqr_or_fallback_scale"], dtype=float)
        x_values = MOTIF.apply_scaler(values, median, scale)
        x_observation = x_values[split_masks["observation"]]
        x_replication = x_values[split_masks["replication"]]
        model, obs_labels, rep_labels = A.reconstruct_model(
            x_observation,
            x_replication,
            int(window_record["selected_clusters"]),
        )
        A.verify_reconstruction(window_record, obs_labels, rep_labels)
        labels = model.predict(x_values)
        split_name = np.full(len(metadata), "other", dtype=object)
        for name, mask in split_masks.items():
            split_name[mask] = name
        motif_by_cluster = {int(item["cluster"]): item for item in motifs}
        full_threshold_by_cluster: dict[int, float] = {}
        prefix_threshold_by_cluster: dict[int, float] = {}
        points = int(window_record["native_points"])
        prefix_index = A.prefix_indices(points, len(MOTIF.VECTOR_COMPONENTS))
        for cluster in motif_by_cluster:
            members = np.flatnonzero(obs_labels == cluster)
            if len(members) < 5:
                continue
            center = model.cluster_centers_[cluster]
            full_threshold_by_cluster[cluster] = float(
                np.quantile(
                    A.normalized_distances(x_observation[members], center),
                    A.CALIBRATION_QUANTILE,
                )
            )
            prefix_threshold_by_cluster[cluster] = float(
                np.quantile(
                    A.normalized_distances(
                        x_observation[members][:, prefix_index], center[prefix_index]
                    ),
                    A.CALIBRATION_QUANTILE,
                )
            )
        states[minutes] = WindowState(
            minutes=minutes,
            points=points,
            cadence=cadence,
            window_record=window_record,
            values=values,
            metadata=metadata.reset_index(drop=True),
            x_values=x_values,
            model=model,
            labels=labels,
            split_name=split_name,
            motif_by_cluster=motif_by_cluster,
            full_threshold_by_cluster=full_threshold_by_cluster,
            prefix_threshold_by_cluster=prefix_threshold_by_cluster,
        )
    return states


def full_occurrences(state: WindowState) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row, cluster_value in enumerate(state.labels):
        cluster = int(cluster_value)
        motif = state.motif_by_cluster.get(cluster)
        threshold = state.full_threshold_by_cluster.get(cluster)
        if motif is None or threshold is None:
            continue
        distance = float(
            A.normalized_distances(
                state.x_values[row], state.model.cluster_centers_[cluster]
            )[0]
        )
        if distance > threshold:
            continue
        meta = state.metadata.iloc[row]
        records.append(
            {
                "motif_id": motif["motif_id"],
                "window_minutes": state.minutes,
                "session_date": str(meta["session_date"]),
                "start_timestamp": str(meta["start_timestamp"]),
                "end_timestamp": str(meta["end_timestamp"]),
                "start_progress": float(meta["start_progress"]),
                "end_progress": float(meta["end_progress"]),
                "distance": distance,
                "split": str(state.split_name[row]),
            }
        )
    return pd.DataFrame(records)


def transition_records(states: dict[int, WindowState]) -> dict[str, Any]:
    occurrence_by_window = {
        minutes: full_occurrences(state) for minutes, state in states.items()
    }
    scale_counts: dict[str, Counter] = {
        "observation": Counter(),
        "replication": Counter(),
    }
    temporal_counts: dict[str, Counter] = {
        "observation": Counter(),
        "replication": Counter(),
    }
    scale_sessions: dict[tuple[str, tuple[str, str]], set[str]] = defaultdict(set)
    temporal_sessions: dict[tuple[str, tuple[str, str]], set[str]] = defaultdict(set)

    available = sorted(occurrence_by_window)
    for split in ("observation", "replication"):
        for minutes, frame in occurrence_by_window.items():
            if frame.empty:
                continue
            lane = frame.loc[frame["split"].eq(split)].copy()
            for session_date, group in lane.groupby("session_date", sort=True):
                ordered = group.sort_values("start_timestamp", kind="mergesort")
                rows = ordered.to_dict("records")
                for left, right in zip(rows, rows[1:]):
                    pair = (left["motif_id"], right["motif_id"])
                    temporal_counts[split][pair] += 1
                    temporal_sessions[(split, pair)].add(str(session_date))

        for left_minutes, right_minutes in zip(available, available[1:]):
            left_frame = occurrence_by_window[left_minutes]
            right_frame = occurrence_by_window[right_minutes]
            if left_frame.empty or right_frame.empty:
                continue
            left_frame = left_frame.loc[left_frame["split"].eq(split)]
            right_frame = right_frame.loc[right_frame["split"].eq(split)]
            for session_date, left_group in left_frame.groupby("session_date", sort=True):
                right_group = right_frame.loc[
                    right_frame["session_date"].eq(str(session_date))
                ]
                if right_group.empty:
                    continue
                right_times = pd.to_datetime(right_group["start_timestamp"], utc=True)
                for left in left_group.to_dict("records"):
                    left_time = pd.Timestamp(left["start_timestamp"])
                    if left_time.tzinfo is None:
                        left_time = left_time.tz_localize("UTC")
                    gaps = (right_times - left_time).abs().dt.total_seconds() / 60.0
                    candidates = right_group.loc[gaps.le(max(1.0, states[left_minutes].cadence))]
                    if candidates.empty:
                        continue
                    best = candidates.iloc[
                        int(
                            np.argmin(
                                np.asarray(
                                    (pd.to_datetime(candidates["start_timestamp"], utc=True) - left_time)
                                    .abs()
                                    .dt.total_seconds()
                                )
                            )
                        )
                    ]
                    pair = (left["motif_id"], str(best["motif_id"]))
                    scale_counts[split][pair] += 1
                    scale_sessions[(split, pair)].add(str(session_date))

    def freeze(
        obs: Counter, rep: Counter, session_map: dict[tuple[str, tuple[str, str]], set[str]]
    ) -> list[dict[str, Any]]:
        result = []
        source_obs_totals = Counter()
        source_rep_totals = Counter()
        for (source, _), count in obs.items():
            source_obs_totals[source] += count
        for (source, _), count in rep.items():
            source_rep_totals[source] += count
        for pair in sorted(set(obs) | set(rep)):
            obs_count = int(obs[pair])
            rep_count = int(rep[pair])
            obs_share = obs_count / max(1, source_obs_totals[pair[0]])
            rep_share = rep_count / max(1, source_rep_totals[pair[0]])
            ratio = rep_share / obs_share if obs_share > 0 else 0.0
            obs_sessions = len(session_map.get(("observation", pair), set()))
            rep_sessions = len(session_map.get(("replication", pair), set()))
            stable = bool(
                obs_sessions >= 10
                and rep_sessions >= 5
                and obs_share >= 0.05
                and rep_share >= 0.025
                and 0.25 <= ratio <= 4.0
            )
            if stable:
                result.append(
                    {
                        "source_motif_id": pair[0],
                        "target_motif_id": pair[1],
                        "observation_occurrences": obs_count,
                        "replication_occurrences": rep_count,
                        "observation_sessions": obs_sessions,
                        "replication_sessions": rep_sessions,
                        "observation_conditional_share": obs_share,
                        "replication_conditional_share": rep_share,
                        "replication_to_observation_share_ratio": ratio,
                    }
                )
        return result

    stable_scale = freeze(scale_counts["observation"], scale_counts["replication"], scale_sessions)
    stable_temporal = freeze(
        temporal_counts["observation"], temporal_counts["replication"], temporal_sessions
    )
    catalog = {
        "principal_verdict": (
            "PRE_CAS_PATTERN_TRANSITION_GRAPH_FROZEN"
            if stable_scale or stable_temporal
            else "NO_PRE_CAS_TRANSITION_PASSED_REPLICATION_GATES"
        ),
        "stable_scale_transition_count": len(stable_scale),
        "stable_temporal_transition_count": len(stable_temporal),
        "stable_scale_transitions": stable_scale,
        "stable_temporal_transitions": stable_temporal,
        "policy": {
            "pre_cas_only": True,
            "observation_replication_only": True,
            "unopened_sessions_scored": False,
            "outcomes_read": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def analogue_by_motif(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for window in catalog.get("windows", []):
        for motif in window.get("motifs", []):
            result[str(motif["motif_id"])] = motif
    return result


def session_native_cache(native_lane: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cache = {}
    for date, group in native_lane.groupby("session_date", sort=True):
        ordered = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        cache[str(date)] = ordered
    return cache


def locate_window_path(
    cache: dict[str, pd.DataFrame], metadata_row: pd.Series, points: int
) -> pd.DataFrame | None:
    session = cache.get(str(metadata_row["session_date"]))
    if session is None:
        return None
    start = pd.Timestamp(metadata_row["start_timestamp"])
    timestamps = pd.to_datetime(session["timestamp"], utc=True)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    matches = np.flatnonzero(timestamps.eq(start).to_numpy())
    if len(matches) != 1:
        return None
    index = int(matches[0])
    window = session.iloc[index : index + points].copy()
    if len(window) != points:
        return None
    return window


def completion_geometry(
    state: WindowState,
    cache: dict[str, pd.DataFrame],
    cluster: int,
    observation_mask: np.ndarray,
) -> dict[str, Any] | None:
    prefix_points = max(2, int(math.ceil(state.points * A.PREFIX_FRACTION)))
    if prefix_points >= state.points:
        return None
    labels = state.labels[observation_mask]
    observation_meta = state.metadata.loc[observation_mask].reset_index(drop=True)
    members = np.flatnonzero(labels == cluster)
    prefix_returns = []
    completion_returns = []
    amplitudes = []
    for member in members:
        path = locate_window_path(cache, observation_meta.iloc[int(member)], state.points)
        if path is None:
            continue
        prices = pd.to_numeric(path["price"], errors="coerce").to_numpy(float)
        if not np.isfinite(prices).all() or np.any(prices <= 0):
            continue
        logp = np.log(prices)
        prefix_returns.append(float(logp[prefix_points - 1] - logp[0]))
        completion_returns.append(float(logp[-1] - logp[prefix_points - 1]))
        amplitudes.append(float(np.max(logp[:prefix_points]) - np.min(logp[:prefix_points])))
    if len(completion_returns) < 10:
        return None
    return {
        "prefix_points": prefix_points,
        "future_points": state.points - prefix_points,
        "primary_horizon_minutes": int(
            round((state.points - prefix_points) * state.cadence)
        ),
        "observation_members": len(completion_returns),
        "median_prefix_log_return": float(np.median(prefix_returns)),
        "median_completion_log_return": float(np.median(completion_returns)),
        "median_prefix_amplitude": float(np.median(amplitudes)),
    }


def mechanism_type(geometry: dict[str, Any]) -> str:
    prefix = float(geometry["median_prefix_log_return"])
    completion = float(geometry["median_completion_log_return"])
    amplitude = float(geometry["median_prefix_amplitude"])
    if abs(prefix) <= max(1e-6, amplitude * 0.25) and abs(completion) > max(
        1e-5, abs(prefix) * 1.5
    ):
        return "COMPRESSION_RELEASE_GEOMETRY"
    if prefix == 0 or completion == 0:
        return "GEOMETRIC_EXPANSION"
    if math.copysign(1.0, prefix) == math.copysign(1.0, completion):
        return "PERSISTENT_EXPANSION_CONTINUATION"
    return "FAILED_EXPANSION_REVERSAL"


def freeze_hypotheses(
    states: dict[int, WindowState],
    lane: dict[str, Any],
    analogue_catalog: dict[str, Any],
    transition_catalog: dict[str, Any],
    cache: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    analogues = analogue_by_motif(analogue_catalog)
    transitions_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in transition_catalog.get("stable_scale_transitions", []):
        transitions_by_source[str(item["source_motif_id"])].append(item)
    hypotheses = []
    for minutes, state in sorted(states.items()):
        masks = masks_for_metadata(state.metadata, lane)
        for cluster, motif in state.motif_by_cluster.items():
            geometry = completion_geometry(state, cache, cluster, masks["observation"])
            if geometry is None:
                continue
            completion = float(geometry["median_completion_log_return"])
            if abs(completion) < 0.0001:
                continue
            analogue = analogues.get(str(motif["motif_id"]), {})
            if int(analogue.get("replication_prefix_qualified", 0)) < 8:
                continue
            successors = sorted(
                transitions_by_source.get(str(motif["motif_id"]), []),
                key=lambda item: (
                    -float(item["replication_conditional_share"]),
                    -int(item["replication_sessions"]),
                ),
            )
            cas = str(analogue.get("cas_sensitivity", "CAS_SENSITIVITY_UNKNOWN"))
            hypothesis = {
                "hypothesis_id": f"H::{motif['motif_id']}::PREFIX_COMPLETION",
                "motif_id": motif["motif_id"],
                "window_minutes": minutes,
                "prefix_fraction": A.PREFIX_FRACTION,
                **geometry,
                "mechanism": mechanism_type(geometry),
                "expected_completion_sign": 1 if completion > 0 else -1,
                "strongest_scale_transition": successors[0] if successors else None,
                "replication_prefix_qualified": int(
                    analogue.get("replication_prefix_qualified", 0)
                ),
                "replication_geometry_completed": int(
                    analogue.get("replication_geometry_completed", 0)
                ),
                "replication_geometry_diverged": int(
                    analogue.get("replication_geometry_diverged", 0)
                ),
                "cas_sensitivity": cas,
                "post_cas_revalidation_required": cas
                != "CAS_LOW_SENSITIVITY_CANDIDATE",
                "outcomes_seen_when_frozen": False,
            }
            hypothesis["semantic_sha256"] = digest(hypothesis)
            hypotheses.append(hypothesis)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_MECHANISM_HYPOTHESES_FROZEN"
            if hypotheses
            else "NO_PRE_CAS_MECHANISM_HYPOTHESIS_PASSED_GEOMETRY_GATES"
        ),
        "hypothesis_count": len(hypotheses),
        "hypotheses": hypotheses,
        "policy": {
            "outcomes_seen_when_frozen": False,
            "unopened_sessions_scored": False,
            "post_cas_validated": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def prefix_events_for_hypothesis(
    hypothesis: dict[str, Any],
    state: WindowState,
    lane: dict[str, Any],
    cache: dict[str, pd.DataFrame],
    allowed_splits: Sequence[str],
) -> list[dict[str, Any]]:
    motif = next(
        item
        for item in state.motif_by_cluster.values()
        if str(item["motif_id"]) == str(hypothesis["motif_id"])
    )
    cluster = int(motif["cluster"])
    threshold = float(state.prefix_threshold_by_cluster[cluster])
    prefix_index = A.prefix_indices(state.points, len(MOTIF.VECTOR_COMPONENTS))
    center_prefix = state.model.cluster_centers_[cluster][prefix_index]
    distances = A.normalized_distances(state.x_values[:, prefix_index], center_prefix)
    prefix_points = int(hypothesis["prefix_points"])
    expected_sign = int(hypothesis["expected_completion_sign"])
    candidates: list[dict[str, Any]] = []
    for row, distance in enumerate(distances):
        split = str(state.split_name[row])
        if split not in allowed_splits or float(distance) > threshold:
            continue
        meta = state.metadata.iloc[row]
        path = locate_window_path(cache, meta, state.points)
        if path is None:
            continue
        prices = pd.to_numeric(path["price"], errors="coerce").to_numpy(float)
        if not np.isfinite(prices).all() or np.any(prices <= 0):
            continue
        logp = np.log(prices)
        signal_index = prefix_points - 1
        if signal_index >= len(logp) - 1:
            continue
        future_log_return = float(logp[-1] - logp[signal_index])
        shorter_index = max(signal_index + 1, len(logp) - 2)
        shorter_return = float(logp[shorter_index] - logp[signal_index])
        session = cache[str(meta["session_date"])]
        start = pd.Timestamp(meta["start_timestamp"])
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        timestamps = pd.to_datetime(session["timestamp"], utc=True)
        start_matches = np.flatnonzero(timestamps.eq(start).to_numpy())
        longer_return = None
        delayed_return = None
        signal_timestamp = None
        exit_timestamp = None
        if len(start_matches) == 1:
            base_index = int(start_matches[0])
            signal_abs = base_index + signal_index
            exit_abs = base_index + state.points - 1
            signal_timestamp = str(pd.Timestamp(session.iloc[signal_abs]["timestamp"]))
            exit_timestamp = str(pd.Timestamp(session.iloc[exit_abs]["timestamp"]))
            if exit_abs + 1 < len(session):
                later_price = float(session.iloc[exit_abs + 1]["price"])
                longer_return = float(math.log(later_price / prices[signal_index]))
            if signal_abs + 1 < exit_abs:
                delayed_price = float(session.iloc[signal_abs + 1]["price"])
                delayed_return = float(math.log(prices[-1] / delayed_price))
        candidates.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "motif_id": hypothesis["motif_id"],
                "session_date": str(meta["session_date"]),
                "split": split,
                "start_timestamp": str(meta["start_timestamp"]),
                "signal_timestamp": signal_timestamp,
                "exit_timestamp": exit_timestamp,
                "signal_progress": float(meta["start_progress"])
                + (float(meta["end_progress"]) - float(meta["start_progress"]))
                * signal_index
                / max(1, state.points - 1),
                "prefix_distance": float(distance),
                "future_log_return": future_log_return,
                "directional_return_bps": expected_sign * future_log_return * 10000.0,
                "shorter_directional_return_bps": expected_sign
                * shorter_return
                * 10000.0,
                "longer_directional_return_bps": (
                    expected_sign * longer_return * 10000.0
                    if longer_return is not None
                    else None
                ),
                "delayed_directional_return_bps": (
                    expected_sign * delayed_return * 10000.0
                    if delayed_return is not None
                    else None
                ),
            }
        )
    # One independent event per motif/session: retain the closest causal prefix.
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in candidates:
        key = (item["split"], item["session_date"])
        existing = best.get(key)
        if existing is None or item["prefix_distance"] < existing["prefix_distance"]:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item["session_date"], item["start_timestamp"]))


def baseline_table(
    native_lane: pd.DataFrame,
    lane: dict[str, Any],
    horizons: Iterable[int],
    cadence: float,
) -> dict[tuple[int, int], float]:
    observation = set(map(str, lane.get("observation_sessions", [])))
    result: dict[tuple[int, int], list[float]] = defaultdict(list)
    for session_date, group in native_lane.groupby("session_date", sort=True):
        if str(session_date) not in observation:
            continue
        ordered = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        prices = pd.to_numeric(ordered["price"], errors="coerce").to_numpy(float)
        progress = pd.to_numeric(ordered["session_progress"], errors="coerce").to_numpy(float)
        for horizon in horizons:
            steps = max(1, int(round(horizon / cadence)))
            for index in range(0, len(ordered) - steps):
                if not (
                    math.isfinite(prices[index])
                    and math.isfinite(prices[index + steps])
                    and prices[index] > 0
                    and prices[index + steps] > 0
                ):
                    continue
                bucket = int(np.clip(math.floor(progress[index] * 20.0), 0, 19))
                result[(int(horizon), bucket)].append(
                    float(math.log(prices[index + steps] / prices[index]))
                )
    return {
        key: float(np.median(values))
        for key, values in result.items()
        if len(values) >= 20
    }


def bootstrap_mean_ci(values: Sequence[float], confidence: float = 0.90) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    if len(data) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RANDOM_STATE + len(data))
    indexes = rng.integers(0, len(data), size=(BOOTSTRAP_DRAWS, len(data)))
    means = data[indexes].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    return (float(np.quantile(means, alpha)), float(np.quantile(means, 1.0 - alpha)))


def summarize_excess(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = np.asarray([item["directional_excess_bps"] for item in events], dtype=float)
    if len(values) == 0:
        return {
            "n": 0,
            "mean_excess_bps": None,
            "median_excess_bps": None,
            "hit_rate": None,
            "mean_ci90": [None, None],
            "one_sided_sign_p": 1.0,
        }
    hits = int(np.sum(values > 0))
    ci = bootstrap_mean_ci(values)
    p = float(binomtest(hits, len(values), 0.5, alternative="greater").pvalue)
    return {
        "n": int(len(values)),
        "mean_excess_bps": float(np.mean(values)),
        "median_excess_bps": float(np.median(values)),
        "hit_rate": float(hits / len(values)),
        "mean_ci90": [ci[0], ci[1]],
        "one_sided_sign_p": p,
    }


def bh_qvalues(pvalues: Sequence[float]) -> list[float]:
    if not pvalues:
        return []
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    m = len(p)
    q_ranked = np.minimum.accumulate((ranked * m / np.arange(1, m + 1))[::-1])[::-1]
    q_ranked = np.clip(q_ranked, 0.0, 1.0)
    q = np.empty(m, dtype=float)
    q[order] = q_ranked
    return q.tolist()


def attach_outcomes(
    hypotheses: dict[str, Any],
    states: dict[int, WindowState],
    lane: dict[str, Any],
    cache: dict[str, pd.DataFrame],
    baseline: dict[tuple[int, int], float],
) -> dict[str, Any]:
    records = []
    for hypothesis in hypotheses.get("hypotheses", []):
        state = states[int(hypothesis["window_minutes"])]
        events = prefix_events_for_hypothesis(
            hypothesis,
            state,
            lane,
            cache,
            allowed_splits=("observation", "replication"),
        )
        sign = int(hypothesis["expected_completion_sign"])
        horizon = int(hypothesis["primary_horizon_minutes"])
        usable = []
        for event in events:
            bucket = int(np.clip(math.floor(event["signal_progress"] * 20.0), 0, 19))
            baseline_raw = baseline.get((horizon, bucket))
            if baseline_raw is None:
                continue
            item = dict(event)
            item["baseline_raw_return_bps"] = baseline_raw * 10000.0
            item["directional_excess_bps"] = item["directional_return_bps"] - sign * baseline_raw * 10000.0
            usable.append(item)
        observation = [item for item in usable if item["split"] == "observation"]
        replication = [item for item in usable if item["split"] == "replication"]
        records.append(
            {
                "hypothesis": hypothesis,
                "observation": summarize_excess(observation),
                "replication": summarize_excess(replication),
                "events": usable,
            }
        )
    qvalues = bh_qvalues(
        [float(item["replication"]["one_sided_sign_p"]) for item in records]
    )
    for item, q in zip(records, qvalues):
        item["replication"]["bh_q"] = q
    catalog = {
        "principal_verdict": (
            "PRE_CAS_CAUSAL_OUTCOMES_ATTACHED"
            if records
            else "NO_FROZEN_HYPOTHESIS_AVAILABLE_FOR_OUTCOME_ATTACHMENT"
        ),
        "hypothesis_outcome_count": len(records),
        "records": records,
        "policy": {
            "observation_replication_outcomes_opened": True,
            "unopened_sessions_scored": False,
            "baseline_fit_on_observation_only": True,
            "hypotheses_frozen_before_outcomes": True,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def structural_screen(outcomes: dict[str, Any]) -> dict[str, Any]:
    survivors = []
    evaluated = []
    for item in outcomes.get("records", []):
        obs = item["observation"]
        rep = item["replication"]
        ci_low = rep.get("mean_ci90", [None, None])[0]
        gates = {
            "observation_n_ge_20": int(obs["n"]) >= 20,
            "replication_n_ge_10": int(rep["n"]) >= 10,
            "observation_mean_positive": (obs["mean_excess_bps"] or -1e9) > 0,
            "replication_mean_ge_2bps": (rep["mean_excess_bps"] or -1e9) >= 2.0,
            "replication_hit_rate_ge_55pct": (rep["hit_rate"] or 0.0) >= 0.55,
            "replication_ci90_lower_positive": ci_low is not None and ci_low > 0,
            "replication_bh_q_le_10pct": float(rep.get("bh_q", 1.0)) <= 0.10,
        }
        passed = all(gates.values())
        record = {
            "hypothesis_id": item["hypothesis"]["hypothesis_id"],
            "motif_id": item["hypothesis"]["motif_id"],
            "passed": passed,
            "gates": gates,
            "observation": obs,
            "replication": rep,
        }
        evaluated.append(record)
        if passed:
            survivors.append(item)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_STRUCTURAL_EDGE_CANDIDATES_SURVIVED"
            if survivors
            else "NO_PRE_CAS_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
        ),
        "evaluated_count": len(evaluated),
        "survivor_count": len(survivors),
        "evaluated": evaluated,
        "survivor_hypothesis_ids": [
            item["hypothesis"]["hypothesis_id"] for item in survivors
        ],
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def strategy_records(
    outcomes: dict[str, Any], screen: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    survivor_ids = set(screen.get("survivor_hypothesis_ids", []))
    strategies = []
    trades: dict[str, list[dict[str, Any]]] = {}
    for item in outcomes.get("records", []):
        hypothesis = item["hypothesis"]
        hid = hypothesis["hypothesis_id"]
        if hid not in survivor_ids:
            continue
        horizon = int(hypothesis["primary_horizon_minutes"])
        if horizon < 10:
            continue
        direction = "LONG_UNDERLYING_PROXY" if int(hypothesis["expected_completion_sign"]) > 0 else "SHORT_UNDERLYING_PROXY"
        strategy_id = f"S::{hypothesis['motif_id']}::CAUSAL_PREFIX"
        strategy = {
            "strategy_id": strategy_id,
            "hypothesis_id": hid,
            "motif_id": hypothesis["motif_id"],
            "direction": direction,
            "signal": "prefix_distance_within_observation_calibrated_90pct_envelope",
            "entry_proxy": "prefix_end_5m_close_then_immediate_execution",
            "exit": f"time_exit_after_{horizon}_minutes",
            "round_trip_cost_bps": COST_BPS,
            "stop_modelled": False,
            "stop_reason": "source is close-only causal geometry; intrabar stop cannot be certified",
            "risk_complete": False,
            "post_cas_revalidation_required": bool(
                hypothesis["post_cas_revalidation_required"]
            ),
        }
        strategy["semantic_sha256"] = digest(strategy)
        strategy_trades = []
        for event in item.get("events", []):
            trade = dict(event)
            trade["gross_directional_bps"] = float(event["directional_return_bps"])
            trade["net_proxy_bps"] = float(event["directional_return_bps"] - COST_BPS)
            strategy_trades.append(trade)
        strategies.append(strategy)
        trades[strategy_id] = strategy_trades
    return strategies, trades


def summarize_net(trades: Sequence[dict[str, Any]], key: str = "net_proxy_bps") -> dict[str, Any]:
    values = np.asarray(
        [float(item[key]) for item in trades if item.get(key) is not None], dtype=float
    )
    if len(values) == 0:
        return {"n": 0, "mean_bps": None, "median_bps": None, "hit_rate": None, "total_bps": 0.0}
    return {
        "n": int(len(values)),
        "mean_bps": float(values.mean()),
        "median_bps": float(np.median(values)),
        "hit_rate": float(np.mean(values > 0)),
        "total_bps": float(values.sum()),
    }


def construct_strategies(outcomes: dict[str, Any], screen: dict[str, Any]) -> dict[str, Any]:
    strategies, trades = strategy_records(outcomes, screen)
    survivors = []
    evaluated = []
    for strategy in strategies:
        sid = strategy["strategy_id"]
        rep = [item for item in trades[sid] if item["split"] == "replication"]
        stats = summarize_net(rep)
        passed = bool(
            stats["n"] >= 10
            and (stats["mean_bps"] or -1e9) > 0
            and (stats["hit_rate"] or 0) > 0.50
        )
        evaluated.append({"strategy": strategy, "replication_proxy": stats, "passed": passed})
        if passed:
            survivors.append(strategy)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_CANONICAL_SIGNAL_STRATEGIES_FROZEN"
            if survivors
            else "NO_PRE_CAS_SIGNAL_STRATEGY_SURVIVED_EXECUTION_PROXY"
        ),
        "strategy_count": len(strategies),
        "survivor_count": len(survivors),
        "strategies": evaluated,
        "survivor_strategy_ids": [item["strategy_id"] for item in survivors],
        "trade_book": {sid: trades[sid] for sid in [s["strategy_id"] for s in survivors]},
        "policy": {
            "underlying_proxy_only": True,
            "options_edge_claimed": False,
            "risk_complete": False,
            "live_authorized": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def walk_forward(strategy_catalog: dict[str, Any]) -> dict[str, Any]:
    results = []
    survivors = []
    for sid in strategy_catalog.get("survivor_strategy_ids", []):
        trades = sorted(
            strategy_catalog["trade_book"].get(sid, []), key=lambda item: item["session_date"]
        )
        dates = sorted(set(item["session_date"] for item in trades))
        if len(dates) < 25:
            results.append({"strategy_id": sid, "passed": False, "reason": "insufficient_dates"})
            continue
        fold_dates = np.array_split(np.asarray(dates, dtype=object), 5)
        folds = []
        for number, date_array in enumerate(fold_dates, start=1):
            date_set = set(map(str, date_array.tolist()))
            fold_trades = [item for item in trades if item["session_date"] in date_set]
            folds.append({"fold": number, **summarize_net(fold_trades)})
        nonempty = [item for item in folds if item["n"] > 0]
        positive = [item for item in nonempty if (item["mean_bps"] or -1e9) > 0]
        means = [float(item["mean_bps"]) for item in nonempty]
        totals = [max(0.0, float(item["total_bps"])) for item in nonempty]
        concentration = max(totals) / sum(totals) if sum(totals) > 0 else 1.0
        passed = bool(
            len(nonempty) >= 4
            and len(positive) >= 3
            and np.median(means) > 0
            and min(means) > -10.0
            and concentration <= 0.60
        )
        result = {
            "strategy_id": sid,
            "passed": passed,
            "folds": folds,
            "positive_fold_count": len(positive),
            "median_fold_mean_bps": float(np.median(means)) if means else None,
            "worst_fold_mean_bps": min(means) if means else None,
            "positive_pnl_fold_concentration": concentration,
        }
        results.append(result)
        if passed:
            survivors.append(sid)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_FIXED_RULE_WALK_FORWARD_SURVIVORS"
            if survivors
            else "NO_PRE_CAS_STRATEGY_SURVIVED_WALK_FORWARD"
        ),
        "survivor_strategy_ids": survivors,
        "results": results,
        "policy": {"parameters_retrained_per_fold": False, "unopened_sessions_scored": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def concentration_ratio(values: np.ndarray, top_n: int = 5) -> float:
    positive = np.sort(values[values > 0])[::-1]
    total = float(positive.sum())
    if total <= 0:
        return 1.0
    return float(positive[:top_n].sum() / total)


def robustness(strategy_catalog: dict[str, Any], wfa: dict[str, Any]) -> dict[str, Any]:
    results = []
    survivors = []
    for sid in wfa.get("survivor_strategy_ids", []):
        trades = strategy_catalog["trade_book"].get(sid, [])
        gross = np.asarray([float(item["gross_directional_bps"]) for item in trades], dtype=float)
        if len(gross) < 20:
            results.append({"strategy_id": sid, "passed": False, "reason": "insufficient_trades"})
            continue
        base = gross - COST_BPS
        high_cost = gross - ROBUST_COST_BPS
        cutoff = max(1, int(math.ceil(len(base) * 0.10)))
        remove_indexes = np.argsort(base)[-cutoff:]
        keep = np.ones(len(base), dtype=bool)
        keep[remove_indexes] = False
        stripped = base[keep]
        delayed = np.asarray(
            [
                float(item["delayed_directional_return_bps"]) - COST_BPS
                for item in trades
                if item.get("delayed_directional_return_bps") is not None
            ],
            dtype=float,
        )
        shorter = np.asarray(
            [float(item["shorter_directional_return_bps"]) - COST_BPS for item in trades],
            dtype=float,
        )
        longer = np.asarray(
            [
                float(item["longer_directional_return_bps"]) - COST_BPS
                for item in trades
                if item.get("longer_directional_return_bps") is not None
            ],
            dtype=float,
        )
        gates = {
            "base_mean_positive": float(base.mean()) > 0,
            "ten_bps_cost_mean_positive": float(high_cost.mean()) > 0,
            "remove_best_10pct_mean_positive": len(stripped) > 0 and float(stripped.mean()) > 0,
            "top5_positive_concentration_le_60pct": concentration_ratio(base, 5) <= 0.60,
            "delayed_entry_mean_positive": len(delayed) >= 10 and float(delayed.mean()) > 0,
            "shorter_horizon_not_catastrophic": float(shorter.mean()) > -5.0,
            "longer_horizon_not_catastrophic": len(longer) >= 10 and float(longer.mean()) > -5.0,
        }
        passed = all(gates.values())
        record = {
            "strategy_id": sid,
            "passed": passed,
            "gates": gates,
            "base_mean_bps": float(base.mean()),
            "ten_bps_cost_mean_bps": float(high_cost.mean()),
            "remove_best_10pct_mean_bps": float(stripped.mean()) if len(stripped) else None,
            "top5_positive_concentration": concentration_ratio(base, 5),
            "delayed_entry_mean_bps": float(delayed.mean()) if len(delayed) else None,
            "shorter_horizon_mean_bps": float(shorter.mean()),
            "longer_horizon_mean_bps": float(longer.mean()) if len(longer) else None,
        }
        results.append(record)
        if passed:
            survivors.append(sid)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_ROBUSTNESS_SURVIVORS"
            if survivors
            else "NO_PRE_CAS_STRATEGY_SURVIVED_ROBUSTNESS_ATTACKS"
        ),
        "survivor_strategy_ids": survivors,
        "results": results,
        "policy": {"unopened_sessions_scored": False, "thresholds_tuned_after_attack": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def final_unopened_test(
    robustness_catalog: dict[str, Any],
    strategy_catalog: dict[str, Any],
    outcomes: dict[str, Any],
    states: dict[int, WindowState],
    lane: dict[str, Any],
    cache: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    survivor_ids = set(robustness_catalog.get("survivor_strategy_ids", []))
    if not survivor_ids:
        catalog = {
            "principal_verdict": "UNOPENED_NOT_ACCESSED_NO_ROBUST_SURVIVOR",
            "unopened_sessions_scored": False,
            "survivor_strategy_ids": [],
            "results": [],
        }
        catalog["semantic_sha256"] = digest(catalog)
        return catalog

    hypothesis_by_id = {
        item["hypothesis"]["hypothesis_id"]: item["hypothesis"]
        for item in outcomes.get("records", [])
    }
    strategy_by_id = {
        entry["strategy"]["strategy_id"]: entry["strategy"]
        for entry in strategy_catalog.get("strategies", [])
    }
    results = []
    passed_ids = []
    for sid in sorted(survivor_ids):
        strategy = strategy_by_id[sid]
        hypothesis = hypothesis_by_id[strategy["hypothesis_id"]]
        state = states[int(hypothesis["window_minutes"])]
        events = prefix_events_for_hypothesis(
            hypothesis,
            state,
            lane,
            cache,
            allowed_splits=("unopened",),
        )
        trades = []
        for item in events:
            record = dict(item)
            record["net_proxy_bps"] = float(item["directional_return_bps"] - COST_BPS)
            trades.append(record)
        stats = summarize_net(trades)
        values = np.asarray([item["net_proxy_bps"] for item in trades], dtype=float)
        concentration = concentration_ratio(values, 5) if len(values) else 1.0
        passed = bool(
            stats["n"] >= 8
            and (stats["mean_bps"] or -1e9) >= 2.0
            and (stats["hit_rate"] or 0) >= 0.50
            and concentration <= 0.70
        )
        results.append(
            {
                "strategy_id": sid,
                "passed": passed,
                "stats": stats,
                "top5_positive_concentration": concentration,
                "unopened_trade_count": len(trades),
            }
        )
        if passed:
            passed_ids.append(sid)
    catalog = {
        "principal_verdict": (
            "PRE_CAS_FINAL_UNOPENED_STRUCTURAL_EDGE_SURVIVORS"
            if passed_ids
            else "NO_PRE_CAS_STRATEGY_SURVIVED_FINAL_UNOPENED_TEST"
        ),
        "unopened_sessions_scored": True,
        "tested_strategy_ids": sorted(survivor_ids),
        "survivor_strategy_ids": passed_ids,
        "results": results,
        "policy": {"one_shot_final_test": True, "post_test_tuning_authorized": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def inspect_option_data(option_roots: Sequence[Path], required_dates: set[str]) -> dict[str, Any]:
    files = []
    overlapping_dates: set[str] = set()
    required_columns_any = {"timestamp", "datetime", "date", "symbol", "tradingsymbol"}
    for root in option_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.parquet"):
            try:
                if path.stat().st_size < 1000:
                    continue
                frame = pd.read_parquet(path)
            except Exception:
                continue
            columns = {str(value).lower() for value in frame.columns}
            if not columns.intersection(required_columns_any):
                continue
            option_like = bool(
                columns.intersection({"strike", "option_type", "expiry", "instrument_type"})
            )
            if not option_like:
                continue
            date_column = next(
                (col for col in frame.columns if str(col).lower() in {"date", "session_date", "timestamp", "datetime"}),
                None,
            )
            dates = set()
            if date_column is not None:
                parsed = pd.to_datetime(frame[date_column], errors="coerce")
                dates = set(parsed.dropna().dt.date.astype(str).unique().tolist())
            overlap = dates & required_dates
            overlapping_dates.update(overlap)
            files.append(
                {
                    "path": str(path),
                    "rows": int(len(frame)),
                    "date_overlap_count": len(overlap),
                    "has_bid_ask": {"bid", "ask"}.issubset(columns)
                    or {"best_bid", "best_ask"}.issubset(columns),
                }
            )
    sufficient = len(overlapping_dates) >= 20 and any(item["has_bid_ask"] for item in files)
    return {
        "principal_verdict": (
            "CONTEMPORANEOUS_OPTION_TRANSLATION_DATA_AVAILABLE"
            if sufficient
            else "OPTION_TRANSLATION_BLOCKED_BY_CERTIFIED_CONTEMPORANEOUS_DATA"
        ),
        "files_considered": files,
        "overlapping_required_dates": len(overlapping_dates),
        "minimum_required_overlap_dates": 20,
        "bid_ask_required": True,
        "translation_authorized": sufficient,
    }


def shadow_gate(
    final_test: dict[str, Any], option_gate: dict[str, Any], native_lane: pd.DataFrame
) -> dict[str, Any]:
    final_survivors = list(final_test.get("survivor_strategy_ids", []))
    post_cas_sessions = int(
        native_lane.loc[native_lane["regime"].eq("POST_CAS"), "session_date"].nunique()
    )
    reasons = []
    if not final_survivors:
        reasons.append("no_final_unopened_structural_edge_survivor")
    if option_gate.get("translation_authorized") is not True:
        reasons.append("option_translation_not_certified")
    if post_cas_sessions < 45:
        reasons.append("post_cas_revalidation_sample_insufficient")
    authorized = not reasons
    catalog = {
        "principal_verdict": (
            "SHADOW_SIGNAL_PACKAGE_AUTHORIZED_NO_ORDER_AUTHORITY"
            if authorized
            else "SHADOW_ACTIVATION_BLOCKED"
        ),
        "shadow_authorized": authorized,
        "order_authorized": False,
        "final_survivor_strategy_ids": final_survivors,
        "post_cas_sessions_in_source": post_cas_sessions,
        "minimum_post_cas_sessions_for_revalidation": 45,
        "blocking_reasons": reasons,
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def write_stage(output: Path, name: str, payload: dict[str, Any]) -> None:
    stable_write(output / f"{name}.json", payload)


def build_final_report(stages: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Observation-First Pattern Atlas — Full Certification V1",
        "",
        "This report is PRE-CAS unless a stage explicitly says otherwise.",
        "No broker call or order authority is created by this campaign.",
        "",
    ]
    for name in (
        "stage5_transition_graph",
        "stage6_hypotheses",
        "stage7_outcomes",
        "stage8_edge_screen",
        "stage9_strategy_construction",
        "stage10_walk_forward",
        "stage11_robustness",
        "stage12_unopened_final",
        "stage13_option_translation",
        "stage14_shadow_gate",
    ):
        stage = stages[name]
        lines.append(f"- **{name}**: `{stage.get('principal_verdict')}`")
    lines.extend(
        [
            "",
            "## Final authority",
            "",
            f"`{stages['final_authority']['principal_verdict']}`",
            "",
            "A completed phase may legitimately end in a fail-closed/no-survivor verdict.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--motif-catalog", type=Path, required=True)
    parser.add_argument("--analogue-catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha256", default=V3.DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-size", type=int, default=V3.DEFAULT_NIFTY_SOURCE_SIZE)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--option-data-root", action="append", type=Path, default=[])
    args = parser.parse_args()

    motif_catalog = load_json(args.motif_catalog)
    analogue_catalog = load_json(args.analogue_catalog)
    lane = validate_inputs(motif_catalog, analogue_catalog, args.instrument)
    native, source_authority = A.authoritative_native_rows(
        source_file=args.source_file,
        source_sha256=args.source_sha256,
        source_size=args.source_size,
        source_basename=args.source_basename,
        instrument=args.instrument,
        minimum_source_sessions=120,
        minimum_median_price=10000.0,
        minimum_native_coverage=0.90,
        maximum_staleness_multiple=1.25,
    )
    native_lane = native.loc[
        native["instrument"].eq(args.instrument) & native["regime"].eq(TARGET_REGIME)
    ].copy()
    states = reconstruct_window_states(native_lane, lane)
    cache = session_native_cache(native_lane)

    stage5 = transition_records(states)
    stage6 = freeze_hypotheses(states, lane, analogue_catalog, stage5, cache)
    baseline = baseline_table(
        native_lane,
        lane,
        [int(item["primary_horizon_minutes"]) for item in stage6.get("hypotheses", [])],
        float(lane["native_cadence_minutes"]),
    )
    stage7 = attach_outcomes(stage6, states, lane, cache, baseline)
    stage8 = structural_screen(stage7)
    stage9 = construct_strategies(stage7, stage8)
    stage10 = walk_forward(stage9)
    stage11 = robustness(stage9, stage10)
    stage12 = final_unopened_test(stage11, stage9, stage7, states, lane, cache)

    required_dates: set[str] = set()
    if stage12.get("survivor_strategy_ids"):
        for sid in stage12["survivor_strategy_ids"]:
            for item in stage9.get("trade_book", {}).get(sid, []):
                required_dates.add(str(item["session_date"]))
    stage13 = inspect_option_data(args.option_data_root, required_dates)
    stage14 = shadow_gate(stage12, stage13, native)

    if stage12.get("survivor_strategy_ids"):
        underlying = "PRE_CAS_UNDERLYING_STRUCTURAL_EDGE_SURVIVOR_EXISTS"
    else:
        underlying = "NO_PRE_CAS_UNDERLYING_STRUCTURAL_EDGE_SURVIVED_FULL_CERTIFICATION"
    final = {
        "principal_verdict": (
            "PATTERN_ATLAS_ALL_PHASES_COMPLETE_SHADOW_BLOCKED"
            if not stage14["shadow_authorized"]
            else "PATTERN_ATLAS_ALL_PHASES_COMPLETE_SHADOW_SIGNAL_ONLY_AUTHORIZED"
        ),
        "underlying_edge_verdict": underlying,
        "options_edge_certified": bool(stage13.get("translation_authorized"))
        and bool(stage12.get("survivor_strategy_ids")),
        "post_cas_certified": False,
        "live_or_order_authorized": False,
        "source_authority": source_authority,
    }
    final["semantic_sha256"] = digest(final)

    stages = {
        "stage5_transition_graph": stage5,
        "stage6_hypotheses": stage6,
        "stage7_outcomes": stage7,
        "stage8_edge_screen": stage8,
        "stage9_strategy_construction": stage9,
        "stage10_walk_forward": stage10,
        "stage11_robustness": stage11,
        "stage12_unopened_final": stage12,
        "stage13_option_translation": stage13,
        "stage14_shadow_gate": stage14,
        "final_authority": final,
    }

    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in stages.items():
        write_stage(output, name, payload)
    (output / "FULL_CERTIFICATION_RESULT.md").write_text(
        build_final_report(stages), encoding="utf-8"
    )
    summary = {
        "principal_verdict": final["principal_verdict"],
        "underlying_edge_verdict": final["underlying_edge_verdict"],
        "frozen_hypotheses": stage6.get("hypothesis_count", 0),
        "structural_edge_screen_survivors": stage8.get("survivor_count", 0),
        "strategy_survivors": stage9.get("survivor_count", 0),
        "walk_forward_survivors": len(stage10.get("survivor_strategy_ids", [])),
        "robustness_survivors": len(stage11.get("survivor_strategy_ids", [])),
        "final_unopened_survivors": len(stage12.get("survivor_strategy_ids", [])),
        "option_translation_authorized": stage13.get("translation_authorized", False),
        "shadow_authorized": stage14.get("shadow_authorized", False),
        "semantic_sha256": final["semantic_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
