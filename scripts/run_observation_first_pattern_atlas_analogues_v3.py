#!/usr/bin/env python3
"""Recertify PRE-CAS matched analogues with a strictly causal prefix representation.

Stage-4 V1/V2 sliced the first dimensions from a full-window motif vector. Each
component of that vector had first been robust-standardized over the *entire*
window, so suffix values could influence the supposed prefix representation.
That is future leakage for a live trigger.

V3 keeps full-window motif membership only as an outcome-blind discovery label.
For matching/trigger calibration it rebuilds every prefix from prefix rows only,
fits a prefix scaler on observation prefixes only, and persists the resulting
motif-specific prefix prototype and distance threshold. Replication suffixes are
used only after qualification to classify geometric completion/divergence.
Unopened sessions are never prefix-scored here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "pre_cas_causal_prefix_matched_geometric_analogues_v3"
SCHEMA_VERSION = 3
TARGET_REGIME = "PRE_CAS"
PREFIX_FRACTION = 0.50
CALIBRATION_QUANTILE = 0.90
MAX_NEAREST_ANALOGUES = 12
MAX_MATCHED_PAIRS = 20


def load_sibling(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V2 = load_sibling(
    "pattern_atlas_analogues_v2_for_v3",
    "run_observation_first_pattern_atlas_analogues_v2.py",
)
V1 = V2.V1
MOTIF = V1.MOTIF
BASE = V1.BASE
V3SOURCE = V1.V3


def causal_prefix_vector(full_window: pd.DataFrame, prefix_points: int) -> np.ndarray:
    """Build a shape vector using prefix rows only; suffix values are unreachable."""
    if prefix_points < 2:
        raise ValueError("Causal prefix requires at least two native points")
    if len(full_window) < prefix_points:
        raise ValueError("Window is shorter than the causal prefix")
    prefix = full_window.iloc[:prefix_points].copy()
    vector, _ = MOTIF.motif_vector(prefix)
    return vector.astype(float)


def session_cache(native_lane: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cache: dict[str, pd.DataFrame] = {}
    for session_date, group in native_lane.groupby("session_date", sort=True):
        cache[str(session_date)] = (
            group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        )
    return cache


def locate_window(
    cache: dict[str, pd.DataFrame],
    metadata_row: pd.Series,
    points: int,
    cadence_minutes: float,
) -> pd.DataFrame:
    session_date = str(metadata_row["session_date"])
    session = cache.get(session_date)
    if session is None:
        raise ValueError(f"Missing native session for prefix calibration: {session_date}")
    start = pd.Timestamp(metadata_row["start_timestamp"])
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    else:
        start = start.tz_convert("UTC")
    timestamps = pd.to_datetime(session["timestamp"], errors="coerce", utc=True)
    matches = np.flatnonzero(timestamps.eq(start).to_numpy())
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one native start row for {session_date} {start}; found={len(matches)}"
        )
    index = int(matches[0])
    window = session.iloc[index : index + points].copy()
    if len(window) != points:
        raise ValueError("Historical window is shorter than expected")
    gaps = (
        pd.to_datetime(window["timestamp"], errors="coerce", utc=True)
        .diff()
        .dt.total_seconds()
        .div(60.0)
        .dropna()
        .to_numpy(float)
    )
    if len(gaps) and not np.allclose(
        gaps,
        cadence_minutes,
        atol=max(0.25, cadence_minutes * 0.10),
    ):
        raise ValueError("Historical window contains a native-cadence gap")
    return window


def causal_prefix_matrix(
    cache: dict[str, pd.DataFrame],
    metadata: pd.DataFrame,
    prefix_points: int,
    cadence_minutes: float,
) -> np.ndarray:
    vectors = [
        causal_prefix_vector(
            locate_window(cache, metadata.iloc[row], prefix_points, cadence_minutes),
            prefix_points,
        )
        for row in range(len(metadata))
    ]
    if not vectors:
        return np.empty((0, len(MOTIF.VECTOR_COMPONENTS) * prefix_points), dtype=float)
    return np.vstack(vectors)


def normalized_distances(values: np.ndarray, center: np.ndarray) -> np.ndarray:
    return V1.normalized_distances(values, center)


def calibration_payload(
    prefix_median: np.ndarray,
    prefix_scale: np.ndarray,
    prototype: np.ndarray,
    threshold: float,
    prefix_points: int,
    cadence_minutes: float,
) -> dict[str, Any]:
    payload = {
        "representation": "prefix_rows_only_motif_vector_v1",
        "prefix_fraction": PREFIX_FRACTION,
        "prefix_points": int(prefix_points),
        "prefix_duration_minutes": float(max(0, prefix_points - 1) * cadence_minutes),
        "vector_components": list(MOTIF.VECTOR_COMPONENTS),
        "vector_dimension": int(len(prototype)),
        "scaler_fit_scope": "observation_prefixes_only",
        "scaler_median": prefix_median.tolist(),
        "scaler_scale": prefix_scale.tolist(),
        "motif_prefix_prototype": prototype.tolist(),
        "distance_calibration_quantile": CALIBRATION_QUANTILE,
        "distance_threshold": float(threshold),
        "suffix_values_used": False,
    }
    payload["semantic_sha256"] = BASE.digest(payload)
    return payload


def analyse_window(
    native_lane: pd.DataFrame,
    lane_catalog: dict[str, Any],
    window_record: dict[str, Any],
) -> dict[str, Any]:
    minutes = int(window_record["window_minutes"])
    cadence = float(lane_catalog["native_cadence_minutes"])
    points = int(window_record["native_points"])
    prefix_points = max(2, int(math.ceil(points * PREFIX_FRACTION)))

    values, metadata = MOTIF.build_windows(
        native_lane,
        minutes,
        cadence,
        max_windows_per_session=20,
    )
    observation_sessions = set(map(str, lane_catalog["observation_sessions"]))
    replication_sessions = set(map(str, lane_catalog["replication_sessions"]))
    unopened_sessions = set(map(str, lane_catalog["unopened_sessions"]))
    dates = metadata["session_date"].astype(str)
    observation_mask = dates.isin(observation_sessions).to_numpy()
    replication_mask = dates.isin(replication_sessions).to_numpy()
    unopened_mask = dates.isin(unopened_sessions).to_numpy()

    observation_values = values[observation_mask]
    replication_values = values[replication_mask]
    observation_meta = metadata.loc[observation_mask].reset_index(drop=True)
    replication_meta = metadata.loc[replication_mask].reset_index(drop=True)

    full_scaler = dict(window_record["scaler"])
    full_median = np.asarray(full_scaler["median"], dtype=float)
    full_scale = np.asarray(full_scaler["iqr_or_fallback_scale"], dtype=float)
    x_observation = MOTIF.apply_scaler(observation_values, full_median, full_scale)
    x_replication = MOTIF.apply_scaler(replication_values, full_median, full_scale)
    model, observation_labels, replication_labels = V1.reconstruct_model(
        x_observation,
        x_replication,
        int(window_record["selected_clusters"]),
    )
    V1.verify_reconstruction(window_record, observation_labels, replication_labels)

    cache = session_cache(native_lane)
    observation_prefix_raw = causal_prefix_matrix(
        cache, observation_meta, prefix_points, cadence
    )
    replication_prefix_raw = causal_prefix_matrix(
        cache, replication_meta, prefix_points, cadence
    )
    prefix_median, prefix_scale = MOTIF.fit_robust_scaler(observation_prefix_raw)
    x_prefix_observation = MOTIF.apply_scaler(
        observation_prefix_raw, prefix_median, prefix_scale
    )
    x_prefix_replication = MOTIF.apply_scaler(
        replication_prefix_raw, prefix_median, prefix_scale
    )

    motifs: list[dict[str, Any]] = []
    for frozen in window_record.get("motifs", []):
        cluster = int(frozen["cluster"])
        members = np.flatnonzero(observation_labels == cluster)
        if members.size < 5:
            raise ValueError(
                f"Frozen motif {frozen['motif_id']} lacks causal-prefix calibration members"
            )

        prototype = np.median(x_prefix_observation[members], axis=0)
        observation_prefix_distance = normalized_distances(
            x_prefix_observation[members], prototype
        )
        prefix_threshold = float(
            np.quantile(observation_prefix_distance, CALIBRATION_QUANTILE)
        )

        center = model.cluster_centers_[cluster]
        full_threshold = float(
            np.quantile(
                normalized_distances(x_observation[members], center),
                CALIBRATION_QUANTILE,
            )
        )
        replication_prefix_distance = normalized_distances(
            x_prefix_replication, prototype
        )
        replication_full_distance = normalized_distances(x_replication, center)
        candidate_rows = np.flatnonzero(
            replication_prefix_distance <= prefix_threshold
        )
        completion_rows = candidate_rows[
            replication_full_distance[candidate_rows] <= full_threshold
        ]
        divergence_rows = candidate_rows[
            replication_full_distance[candidate_rows] > full_threshold
        ]

        ordered_candidates = candidate_rows[
            np.argsort(replication_prefix_distance[candidate_rows], kind="mergesort")
        ][:MAX_NEAREST_ANALOGUES]
        nearest = [
            V1.metadata_record(
                replication_meta,
                int(row),
                float(replication_prefix_distance[row]),
                float(replication_full_distance[row]),
                (
                    "geometry_completed"
                    if replication_full_distance[row] <= full_threshold
                    else "geometry_diverged"
                ),
            )
            for row in ordered_candidates
        ]
        pairs = V1.matched_pairs(
            x_prefix_replication,
            replication_meta,
            completion_rows,
            divergence_rows,
            limit=MAX_MATCHED_PAIRS,
        )
        descriptor = dict(frozen.get("observation_descriptor") or {})
        end_progress = float(descriptor.get("median_end_progress", float("nan")))
        calibration = calibration_payload(
            prefix_median,
            prefix_scale,
            prototype,
            prefix_threshold,
            prefix_points,
            cadence,
        )
        motif = {
            "motif_id": frozen["motif_id"],
            "cluster": cluster,
            "causal_prefix_calibration": calibration,
            "observation_calibration_members": int(members.size),
            "full_geometry_distance_threshold": full_threshold,
            "replication_prefix_qualified": int(candidate_rows.size),
            "replication_geometry_completed": int(completion_rows.size),
            "replication_geometry_diverged": int(divergence_rows.size),
            "geometry_completion_rate_given_prefix": (
                float(completion_rows.size / candidate_rows.size)
                if candidate_rows.size
                else None
            ),
            "nearest_replication_prefix_analogues": nearest,
            "matched_geometric_divergence_pairs": pairs,
            "cas_sensitivity": V1.classify_cas_sensitivity(end_progress),
            "cas_sensitivity_basis": {
                "type": "pre_cas_time_of_day_heuristic_only",
                "median_end_progress": end_progress,
                "post_cas_validated": False,
            },
        }
        motif["semantic_sha256"] = BASE.digest(motif)
        motifs.append(motif)

    scored_dates = set(observation_meta["session_date"].astype(str)) | set(
        replication_meta["session_date"].astype(str)
    )
    if scored_dates & unopened_sessions:
        raise ValueError("Unopened sessions reached causal-prefix analogue scoring")

    return {
        "window_minutes": minutes,
        "native_points": points,
        "causal_prefix_points": prefix_points,
        "frozen_motif_count": len(motifs),
        "observation_windows": int(len(observation_meta)),
        "replication_windows": int(len(replication_meta)),
        "unopened_windows_scored": 0,
        "unopened_windows_available_but_ignored": int(unopened_mask.sum()),
        "motifs": motifs,
    }


def build_report(catalog: dict[str, Any]) -> str:
    lines = [
        "# Observation-First Pattern Atlas — Causal-Prefix Matched Analogues V3",
        "",
        f"Principal verdict: `{catalog['principal_verdict']}`",
        "",
        "Prefix representations are recomputed from prefix rows only. Suffix mutation cannot affect a prefix vector.",
        "Replication suffix geometry is read only after prefix qualification to classify completion/divergence.",
        "Unopened sessions remain unscored.",
        "",
    ]
    for window in catalog["windows"]:
        lines.append(f"## {window['window_minutes']}m")
        lines.append("")
        for motif in window["motifs"]:
            lines.append(
                f"- `{motif['motif_id']}`: qualified `{motif['replication_prefix_qualified']}`, "
                f"completed `{motif['replication_geometry_completed']}`, "
                f"diverged `{motif['replication_geometry_diverged']}`"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--motif-catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha256", default=V3SOURCE.DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-size", type=int, default=V3SOURCE.DEFAULT_NIFTY_SOURCE_SIZE)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--regime", default=TARGET_REGIME)
    args = parser.parse_args()

    if args.regime != TARGET_REGIME:
        raise ValueError("Stage-4 V3 is PRE_CAS-only")

    motif_catalog = json.loads(args.motif_catalog.read_text(encoding="utf-8"))
    lane = V2.validate_recertified_catalog(
        motif_catalog, args.instrument, args.regime
    )
    native, source_authority = V1.authoritative_native_rows(
        args.source_file,
        args.source_sha256,
        args.source_size,
        args.source_basename,
        args.instrument,
        120,
        10000.0,
        0.90,
        1.25,
    )
    native_lane = native.loc[
        native["instrument"].eq(args.instrument)
        & native["regime"].eq(args.regime)
    ].copy()

    windows = [
        analyse_window(native_lane, lane, window)
        for window in lane.get("windows", [])
        if window.get("motifs")
    ]
    analysed = sum(len(item["motifs"]) for item in windows)
    with_divergence = sum(
        1
        for window in windows
        for motif in window["motifs"]
        if motif["replication_geometry_diverged"] > 0
    )
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "principal_verdict": (
            "PRE_CAS_CAUSAL_PREFIX_MATCHED_GEOMETRIC_ANALOGUES_FROZEN"
            if analysed
            else "NO_PRE_CAS_CAUSAL_PREFIX_ANALOGUE_AVAILABLE"
        ),
        "instrument": args.instrument,
        "regime": args.regime,
        "source_authority": source_authority,
        "source_motif_catalog_sha256": motif_catalog.get("semantic_sha256"),
        "frozen_motifs_analyzed": analysed,
        "motifs_with_geometric_divergence_analogues": with_divergence,
        "windows": windows,
        "policy": {
            "pre_cas_only": True,
            "trajectory_quality_accepted_sessions_only": True,
            "causal_prefix_representation": True,
            "prefix_scaler_fit_on_observation_prefixes_only": True,
            "suffix_values_used_in_prefix_trigger": False,
            "post_prefix_geometry_used_for_completion_only": True,
            "unopened_sessions_scored": False,
            "future_returns_calculated": False,
            "trade_outcomes_read": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "entry_exit_target_stop_constructed": False,
            "post_cas_validated": False,
            "allowed_for_live_execution": False,
        },
    }
    catalog["semantic_sha256"] = BASE.digest(catalog)
    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    BASE.stable_write(output / "matched_geometric_analogue_catalog_v3.json", catalog)
    (output / "ANALOGUE_V3_RESULT.md").write_text(
        build_report(catalog), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "principal_verdict": catalog["principal_verdict"],
                "frozen_motifs_analyzed": analysed,
                "motifs_with_geometric_divergence_analogues": with_divergence,
                "semantic_sha256": catalog["semantic_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
