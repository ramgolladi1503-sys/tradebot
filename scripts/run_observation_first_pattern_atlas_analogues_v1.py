#!/usr/bin/env python3
"""Build PRE-CAS matched geometric analogues for frozen Pattern Atlas motifs.

A matched geometric analogue is outcome-blind with respect to trading:
- the first half of a historical native-cadence window resembles a frozen motif;
- the second half either remains inside the motif's calibrated geometry envelope
  ("geometry_completed") or diverges from it ("geometry_diverged").

Only observation and replication sessions from the frozen motif catalog are used.
Unopened sessions are never scored. No future return, trade direction, entry,
exit, target, stop, P&L, expectancy, or live/paper authority is read or produced.
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
from sklearn.cluster import MiniBatchKMeans

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "pre_cas_matched_geometric_analogues_v1"
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


V3 = load_sibling(
    "pattern_atlas_external_index_trajectory_v3",
    "run_observation_first_pattern_atlas_external_index_trajectory_v3.py",
)
MOTIF = load_sibling(
    "pattern_atlas_native_motifs_v1",
    "run_observation_first_pattern_atlas_motifs_v1.py",
)
BASE = V3.BASE


def validate_catalog(catalog: dict[str, Any], instrument: str, regime: str) -> dict[str, Any]:
    policy = dict(catalog.get("policy") or {})
    unsafe = {
        "outcomes_read": policy.get("outcomes_read"),
        "future_returns_calculated": policy.get("future_returns_calculated"),
        "pnl_calculated": policy.get("pnl_calculated"),
        "direction_selected": policy.get("direction_selected"),
        "unopened_sessions_scored": policy.get("unopened_sessions_scored"),
    }
    if any(value is True for value in unsafe.values()):
        raise ValueError(f"Motif catalog violates outcome-blind authority: {unsafe}")
    if policy.get("regimes_mixed") is True:
        raise ValueError("Motif catalog mixed CAS regimes")

    lanes = [
        lane for lane in catalog.get("lanes", [])
        if str(lane.get("instrument")) == instrument and str(lane.get("regime")) == regime
    ]
    if len(lanes) != 1:
        raise ValueError(
            f"Expected exactly one frozen motif lane for {instrument}/{regime}; found={len(lanes)}"
        )
    lane = lanes[0]
    if lane.get("verdict") != "OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN":
        raise ValueError(f"Motif lane is not frozen: {lane.get('verdict')}")
    if lane.get("unopened_sessions_scored") is not False:
        raise ValueError("Frozen motif lane does not prove unopened sessions stayed unopened")

    observation = set(map(str, lane.get("observation_sessions") or []))
    replication = set(map(str, lane.get("replication_sessions") or []))
    unopened = set(map(str, lane.get("unopened_sessions") or []))
    if observation & replication or observation & unopened or replication & unopened:
        raise ValueError("Chronological motif blocks overlap")
    return lane


def authoritative_native_rows(
    source_file: Path,
    source_sha256: str,
    source_size: int,
    source_basename: str,
    instrument: str,
    minimum_source_sessions: int,
    minimum_median_price: float,
    minimum_native_coverage: float,
    maximum_staleness_multiple: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = V3.inspect_external_parquet(
        source_file,
        source_sha256,
        source_size,
        source_basename,
    )
    selected_columns = BASE.allowed_columns("constituent", source["columns"])
    raw = BASE.read_parquet(Path(source["path"]), selected_columns)
    index_raw, selection = V3.V2.select_exact_index_rows(
        raw,
        instrument,
        minimum_source_sessions,
        minimum_median_price,
    )
    clean = BASE.canonicalize(
        index_raw,
        source["logical_basename"],
        "constituent",
        BASE.TZ,
    )
    clean["instrument"] = instrument
    cadence = V3.V2.infer_native_cadence(clean)
    minute = BASE.resample_minutes(clean).merge(
        cadence,
        on=["instrument", "session_date"],
        how="left",
        validate="many_to_one",
    )
    causal = BASE.add_causal_features(minute)
    accepted, rejected = V3.V2.build_cadence_aware_vectors(
        causal,
        points=96,
        minimum_native_coverage=minimum_native_coverage,
        maximum_staleness_multiple=maximum_staleness_multiple,
    )
    accepted_dates = {str(item["session_date"]) for item in accepted}
    native = MOTIF.prepare_native_rows(causal)
    native["session_date_str"] = native["session_date"].astype(str)
    native = native.loc[native["session_date_str"].isin(accepted_dates)].copy()
    native = native.drop(columns=["session_date_str"])
    authority = {
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "source_size_bytes": source["size_bytes"],
        "source_rows": source["rows"],
        "source_sessions": selection["selected_sessions"],
        "accepted_sessions": len(accepted),
        "rejected_sessions": len(rejected),
        "rejected_session_reasons": sorted(
            {
                reason
                for item in rejected
                for reason in item.get("reasons", [])
            }
        ),
        "source_storage_mode": source["storage_mode"],
    }
    return native, authority


def prefix_indices(points: int, components: int, fraction: float = PREFIX_FRACTION) -> np.ndarray:
    if points < 2 or components < 1:
        raise ValueError("Invalid motif vector shape")
    prefix_points = max(2, int(math.ceil(points * fraction)))
    indexes: list[int] = []
    for component in range(components):
        start = component * points
        indexes.extend(range(start, start + prefix_points))
    return np.asarray(indexes, dtype=int)


def normalized_distances(values: np.ndarray, center: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    center = np.asarray(center, dtype=float)
    if values.ndim == 1:
        values = values.reshape(1, -1)
    if values.shape[1] != center.shape[0]:
        raise ValueError("Distance dimensionality mismatch")
    return np.linalg.norm(values - center, axis=1) / math.sqrt(values.shape[1])


def reconstruct_model(
    observation_values: np.ndarray,
    replication_values: np.ndarray,
    clusters: int,
) -> tuple[MiniBatchKMeans, np.ndarray, np.ndarray]:
    model = MiniBatchKMeans(
        n_clusters=clusters,
        random_state=MOTIF.RANDOM_STATE,
        n_init=3,
        max_iter=100,
        batch_size=min(1024, max(64, len(observation_values))),
        reassignment_ratio=0.01,
    )
    observation_labels = model.fit_predict(observation_values)
    replication_labels = model.predict(replication_values)
    return model, observation_labels, replication_labels


def verify_reconstruction(
    window_record: dict[str, Any],
    observation_labels: np.ndarray,
    replication_labels: np.ndarray,
) -> None:
    selected_clusters = int(window_record["selected_clusters"])
    selected_record = next(
        item
        for item in window_record.get("model_selection", [])
        if int(item.get("clusters", -1)) == selected_clusters
    )
    expected = {
        int(item["cluster"]): (
            int(item["observation_occurrences"]),
            int(item["replication_occurrences"]),
        )
        for item in selected_record.get("cluster_records", [])
    }
    actual = {
        cluster: (
            int(np.sum(observation_labels == cluster)),
            int(np.sum(replication_labels == cluster)),
        )
        for cluster in range(selected_clusters)
    }
    if actual != expected:
        raise ValueError(
            "Deterministic motif reconstruction differs from frozen catalog; "
            "do not continue to analogue matching"
        )


def classify_cas_sensitivity(median_end_progress: float) -> str:
    """Heuristic only; no post-CAS validation is implied."""
    if not math.isfinite(median_end_progress):
        return "CAS_SENSITIVITY_UNKNOWN"
    if median_end_progress >= 0.96:
        return "CAS_DIRECT_CLOSING_ZONE_REVALIDATION_REQUIRED"
    if median_end_progress >= 0.88:
        return "CAS_HIGH_SENSITIVITY"
    if median_end_progress >= 0.75:
        return "CAS_MEDIUM_SENSITIVITY"
    return "CAS_LOW_SENSITIVITY_CANDIDATE"


def metadata_record(
    metadata: pd.DataFrame,
    row: int,
    prefix_distance: float,
    full_distance: float,
    state: str,
) -> dict[str, Any]:
    item = metadata.iloc[int(row)]
    return {
        "session_date": str(item["session_date"]),
        "start_timestamp": str(item["start_timestamp"]),
        "end_timestamp": str(item["end_timestamp"]),
        "start_progress": float(item["start_progress"]),
        "end_progress": float(item["end_progress"]),
        "prefix_distance": float(prefix_distance),
        "full_distance": float(full_distance),
        "geometry_state": state,
    }


def matched_pairs(
    prefix_values: np.ndarray,
    metadata: pd.DataFrame,
    completion_rows: np.ndarray,
    divergence_rows: np.ndarray,
    limit: int = MAX_MATCHED_PAIRS,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    if completion_rows.size == 0 or divergence_rows.size == 0:
        return pairs
    for divergence_row in divergence_rows[:limit]:
        divergence_vector = prefix_values[divergence_row]
        divergence_progress = float(metadata.iloc[divergence_row]["start_progress"])
        candidates = []
        for completion_row in completion_rows:
            if (
                str(metadata.iloc[completion_row]["session_date"])
                == str(metadata.iloc[divergence_row]["session_date"])
            ):
                continue
            vector_distance = float(
                np.linalg.norm(prefix_values[completion_row] - divergence_vector)
                / math.sqrt(prefix_values.shape[1])
            )
            progress_gap = abs(
                float(metadata.iloc[completion_row]["start_progress"])
                - divergence_progress
            )
            match_score = vector_distance + 2.0 * progress_gap
            candidates.append((match_score, vector_distance, progress_gap, completion_row))
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item[0], item[1], item[2], int(item[3])))
        score, vector_distance, progress_gap, completion_row = candidates[0]
        pairs.append(
            {
                "divergence_session_date": str(metadata.iloc[divergence_row]["session_date"]),
                "divergence_start_timestamp": str(
                    metadata.iloc[divergence_row]["start_timestamp"]
                ),
                "completion_session_date": str(metadata.iloc[completion_row]["session_date"]),
                "completion_start_timestamp": str(
                    metadata.iloc[completion_row]["start_timestamp"]
                ),
                "prefix_match_distance": vector_distance,
                "start_progress_gap": progress_gap,
                "match_score": score,
            }
        )
    return pairs


def analyze_motif(
    motif: dict[str, Any],
    model: MiniBatchKMeans,
    observation_values: np.ndarray,
    replication_values: np.ndarray,
    observation_meta: pd.DataFrame,
    replication_meta: pd.DataFrame,
    observation_labels: np.ndarray,
    points: int,
) -> dict[str, Any]:
    cluster = int(motif["cluster"])
    center = model.cluster_centers_[cluster]
    prefix_index = prefix_indices(points, len(MOTIF.VECTOR_COMPONENTS))
    observation_members = np.flatnonzero(observation_labels == cluster)
    if observation_members.size < 5:
        raise ValueError(f"Frozen motif cluster {cluster} lacks calibration members")

    obs_prefix = observation_values[observation_members][:, prefix_index]
    center_prefix = center[prefix_index]
    prefix_threshold = float(
        np.quantile(
            normalized_distances(obs_prefix, center_prefix),
            CALIBRATION_QUANTILE,
        )
    )
    full_threshold = float(
        np.quantile(
            normalized_distances(observation_values[observation_members], center),
            CALIBRATION_QUANTILE,
        )
    )

    replication_prefix = replication_values[:, prefix_index]
    prefix_distance = normalized_distances(replication_prefix, center_prefix)
    full_distance = normalized_distances(replication_values, center)
    candidate_rows = np.flatnonzero(prefix_distance <= prefix_threshold)
    completion_rows = candidate_rows[full_distance[candidate_rows] <= full_threshold]
    divergence_rows = candidate_rows[full_distance[candidate_rows] > full_threshold]

    ordered_candidates = candidate_rows[
        np.argsort(prefix_distance[candidate_rows], kind="mergesort")
    ][:MAX_NEAREST_ANALOGUES]
    nearest = [
        metadata_record(
            replication_meta,
            int(row),
            float(prefix_distance[row]),
            float(full_distance[row]),
            (
                "geometry_completed"
                if full_distance[row] <= full_threshold
                else "geometry_diverged"
            ),
        )
        for row in ordered_candidates
    ]

    pair_records = matched_pairs(
        replication_prefix,
        replication_meta,
        completion_rows,
        divergence_rows,
    )
    descriptor = dict(motif.get("observation_descriptor") or {})
    end_progress = float(descriptor.get("median_end_progress", float("nan")))

    result = {
        "motif_id": motif["motif_id"],
        "cluster": cluster,
        "prefix_fraction": PREFIX_FRACTION,
        "calibration_quantile": CALIBRATION_QUANTILE,
        "observation_calibration_members": int(observation_members.size),
        "prefix_distance_threshold": prefix_threshold,
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
        "matched_geometric_divergence_pairs": pair_records,
        "cas_sensitivity": classify_cas_sensitivity(end_progress),
        "cas_sensitivity_basis": {
            "type": "pre_cas_time_of_day_heuristic_only",
            "median_end_progress": end_progress,
            "post_cas_validated": False,
        },
    }
    result["semantic_sha256"] = BASE.digest(result)
    return result


def analyze_window(
    native_lane: pd.DataFrame,
    lane_catalog: dict[str, Any],
    window_record: dict[str, Any],
) -> dict[str, Any]:
    minutes = int(window_record["window_minutes"])
    cadence = float(lane_catalog["native_cadence_minutes"])
    values, metadata = MOTIF.build_windows(
        native_lane,
        minutes,
        cadence,
        max_windows_per_session=20,
    )
    observation_sessions = set(map(str, lane_catalog["observation_sessions"]))
    replication_sessions = set(map(str, lane_catalog["replication_sessions"]))
    unopened_sessions = set(map(str, lane_catalog["unopened_sessions"]))

    unopened_mask = metadata["session_date"].astype(str).isin(unopened_sessions)
    observation_mask = metadata["session_date"].astype(str).isin(observation_sessions).to_numpy()
    replication_mask = metadata["session_date"].astype(str).isin(replication_sessions).to_numpy()

    observation_values = values[observation_mask]
    replication_values = values[replication_mask]
    observation_meta = metadata.loc[observation_mask].reset_index(drop=True)
    replication_meta = metadata.loc[replication_mask].reset_index(drop=True)

    scaler = dict(window_record["scaler"])
    median = np.asarray(scaler["median"], dtype=float)
    scale = np.asarray(scaler["iqr_or_fallback_scale"], dtype=float)
    x_observation = MOTIF.apply_scaler(observation_values, median, scale)
    x_replication = MOTIF.apply_scaler(replication_values, median, scale)
    clusters = int(window_record["selected_clusters"])
    model, observation_labels, replication_labels = reconstruct_model(
        x_observation,
        x_replication,
        clusters,
    )
    verify_reconstruction(window_record, observation_labels, replication_labels)

    motifs = [
        analyze_motif(
            motif,
            model,
            x_observation,
            x_replication,
            observation_meta,
            replication_meta,
            observation_labels,
            int(window_record["native_points"]),
        )
        for motif in window_record.get("motifs", [])
    ]

    scored_dates = set(observation_meta["session_date"].astype(str)) | set(
        replication_meta["session_date"].astype(str)
    )
    if scored_dates & unopened_sessions:
        raise ValueError("Unopened sessions reached matched-analogue scoring")

    return {
        "window_minutes": minutes,
        "frozen_motif_count": len(motifs),
        "observation_windows": int(len(observation_meta)),
        "replication_windows": int(len(replication_meta)),
        "unopened_windows_scored": 0,
        "unopened_windows_available_but_ignored": int(unopened_mask.sum()),
        "motifs": motifs,
    }


def build_report(catalog: dict[str, Any]) -> str:
    lines = [
        "# Observation-First Pattern Atlas — PRE-CAS Matched Geometric Analogues V1",
        "",
        f"Principal verdict: `{catalog['principal_verdict']}`",
        "",
        "This stage uses post-prefix geometry only to distinguish motif completion from geometric divergence.",
        "It does not read future return, P&L, trade outcome, direction, entry, exit, target or stop.",
        "Unopened sessions remain unscored.",
        "",
    ]
    for window in catalog["windows"]:
        lines.extend(
            [
                f"## {window['window_minutes']}m",
                "",
                f"Frozen motifs analyzed: `{window['frozen_motif_count']}`",
                "",
            ]
        )
        for motif in window["motifs"]:
            lines.append(
                f"- `{motif['motif_id']}`: prefix-qualified "
                f"`{motif['replication_prefix_qualified']}`, completed "
                f"`{motif['replication_geometry_completed']}`, diverged "
                f"`{motif['replication_geometry_diverged']}`, "
                f"CAS sensitivity `{motif['cas_sensitivity']}`"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--motif-catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha256", default=V3.DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-size", type=int, default=V3.DEFAULT_NIFTY_SOURCE_SIZE)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--regime", default=TARGET_REGIME)
    parser.add_argument("--minimum-source-sessions", type=int, default=120)
    parser.add_argument("--minimum-median-price", type=float, default=10000.0)
    parser.add_argument("--minimum-native-coverage", type=float, default=0.90)
    parser.add_argument("--maximum-staleness-multiple", type=float, default=1.25)
    args = parser.parse_args()

    if args.regime != TARGET_REGIME:
        raise ValueError(
            "Stage 4 V1 is PRE_CAS-only. POST_CAS requires its own sufficiently populated lane."
        )

    motif_catalog = json.loads(args.motif_catalog.read_text(encoding="utf-8"))
    lane_catalog = validate_catalog(motif_catalog, args.instrument, args.regime)
    native, source_authority = authoritative_native_rows(
        args.source_file,
        args.source_sha256,
        args.source_size,
        args.source_basename,
        args.instrument,
        args.minimum_source_sessions,
        args.minimum_median_price,
        args.minimum_native_coverage,
        args.maximum_staleness_multiple,
    )
    native_lane = native.loc[
        native["instrument"].eq(args.instrument) & native["regime"].eq(args.regime)
    ].copy()

    windows = [
        analyze_window(native_lane, lane_catalog, window)
        for window in lane_catalog.get("windows", [])
        if window.get("motifs")
    ]
    analysed = sum(len(window["motifs"]) for window in windows)
    with_divergence = sum(
        1
        for window in windows
        for motif in window["motifs"]
        if motif["replication_geometry_diverged"] > 0
    )
    catalog = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "principal_verdict": (
            "PRE_CAS_MATCHED_GEOMETRIC_ANALOGUES_FROZEN"
            if analysed
            else "NO_PRE_CAS_MATCHED_GEOMETRIC_ANALOGUE_AVAILABLE"
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
            "post_prefix_geometry_used_for_completion_only": True,
            "unopened_sessions_scored": False,
            "future_returns_calculated": False,
            "trade_outcomes_read": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "entry_exit_target_stop_constructed": False,
            "cas_sensitivity_is_heuristic_only": True,
            "post_cas_validated": False,
            "allowed_for_live_execution": False,
        },
    }
    catalog["semantic_sha256"] = BASE.digest(catalog)
    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    BASE.stable_write(output / "matched_geometric_analogue_catalog.json", catalog)
    (output / "ANALOGUE_RESULT.md").write_text(build_report(catalog), encoding="utf-8")
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
