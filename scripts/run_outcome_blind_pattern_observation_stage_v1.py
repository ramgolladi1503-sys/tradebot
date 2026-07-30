#!/usr/bin/env python3
"""Discover recurring market-state patterns without reading outcomes.

The campaign builds one causal state row per completed timestamp from the
repaired joint underlying-option warehouse and the constituent panel. It fits
state clusters on the earliest observation sessions, checks recurrence on a
later replication block, and freezes only stable state transitions. No future,
entry, exit, target, P&L, validation, or holdout field is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CAMPAIGN = "outcome_blind_pattern_observation_v1"
JOINT_SHA256 = "332b78126d61fe4e7a9bb4aa765af753c8eb7d150c66b1157e43e766a16e14b0"
CONSTITUENT_SHA256 = "ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0"
RANDOM_STATE = 20260730

UNDERLYING_NUMERIC = [
    "ret_1",
    "ret_5",
    "acceleration",
    "momentum_15",
    "slope_15",
    "trend_strength_proxy",
    "rolling_range_15",
    "atr_14",
    "vwap_distance",
    "close_location",
    "dist_session_high",
    "dist_session_low",
    "directional_persistence",
    "rejection_acceptance_proxy",
    "session_progress",
    "expansion_ratio",
    "volatility_compression",
    "body_expansion",
]
UNDERLYING_BOOL = [
    "inside_bar",
    "outside_bar",
    "higher_high_state",
    "lower_low_state",
    "vwap_cross_reclaim",
]
JOINT_REQUIRED = [
    "session_id",
    "event_timestamp",
    "option_type",
    "strike",
    "premium_velocity",
    "premium_acceleration",
    "premium_mean",
    "volume_sum",
    "open_interest_sum",
    "certified_for_replay",
    "is_completed_bar",
    "is_stale",
    "stale_price_flag",
    "underlying_completed_bar",
    "underlying_sparse_bar_flag",
    "underlying_stale_flag",
    *UNDERLYING_NUMERIC,
    *UNDERLYING_BOOL,
]
CONSTITUENT_REQUIRED = [
    "timestamp",
    "session",
    "symbol",
    "close",
    "volume",
    "fallback",
    "mock",
    "synthetic",
]


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def locate_by_sha(repo: Path, name: str, expected_sha: str) -> Path:
    root = repo / "research" / "local_evidence_consolidation_v1"
    candidates = sorted(path for path in root.rglob(name) if path.is_file())
    for path in candidates:
        if sha256(path) == expected_sha:
            return path
    raise FileNotFoundError(f"No {name} with expected SHA-256 {expected_sha}")


def existing_columns(path: Path, requested: list[str]) -> list[str]:
    available = set(pq.ParquetFile(path).schema_arrow.names)
    missing = sorted(set(requested) - available)
    if missing:
        raise ValueError(f"Missing required columns in {path.name}: {missing}")
    return requested


def top_share(frame: pd.DataFrame, keys: list[str], value: str, n: int = 3) -> pd.Series:
    clean = frame[keys + [value]].copy()
    clean[value] = pd.to_numeric(clean[value], errors="coerce").fillna(0.0).clip(lower=0.0)
    totals = clean.groupby(keys, observed=True)[value].sum()
    ranked = clean.sort_values(keys + [value], ascending=[True] * len(keys) + [False], kind="mergesort")
    leaders = ranked.groupby(keys, observed=True, sort=False).head(n).groupby(keys, observed=True)[value].sum()
    share = leaders.div(totals.replace(0.0, np.nan)).fillna(0.0)
    return share


def wing_features(frame: pd.DataFrame, side: str) -> pd.DataFrame:
    keys = ["session_id", "event_timestamp"]
    wing = frame.loc[frame["option_type"].astype(str).str.upper().eq(side)].copy()
    group = wing.groupby(keys, observed=True)
    output = group.agg(
        contract_count=("strike", "size"),
        velocity_median=("premium_velocity", "median"),
        acceleration_median=("premium_acceleration", "median"),
        premium_median=("premium_mean", "median"),
        volume_total=("volume_sum", "sum"),
        oi_total=("open_interest_sum", "sum"),
    )
    output["positive_share"] = group["premium_velocity"].apply(
        lambda values: float((pd.to_numeric(values, errors="coerce") > 0).mean())
    )
    quantiles = group["premium_velocity"].quantile([0.25, 0.75]).unstack(level=-1)
    output["velocity_iqr"] = quantiles.get(0.75, pd.Series(index=output.index, dtype=float)) - quantiles.get(
        0.25, pd.Series(index=output.index, dtype=float)
    )
    output["volume_top3_share"] = top_share(wing, keys, "volume_sum", 3)
    output["oi_top3_share"] = top_share(wing, keys, "open_interest_sum", 3)
    output["log_volume"] = np.log1p(pd.to_numeric(output["volume_total"], errors="coerce").clip(lower=0.0))
    output["log_oi"] = np.log1p(pd.to_numeric(output["oi_total"], errors="coerce").clip(lower=0.0))
    output["log_premium"] = np.log1p(pd.to_numeric(output["premium_median"], errors="coerce").clip(lower=0.0))
    keep = [
        "contract_count",
        "velocity_median",
        "acceleration_median",
        "positive_share",
        "velocity_iqr",
        "volume_top3_share",
        "oi_top3_share",
        "log_volume",
        "log_oi",
        "log_premium",
    ]
    output = output[keep].rename(columns={column: f"{side.lower()}_{column}" for column in keep})
    return output


def load_joint_state(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = existing_columns(path, JOINT_REQUIRED)
    frame = pq.read_table(path, columns=columns).to_pandas()
    raw_rows = len(frame)
    frame["event_timestamp"] = pd.to_datetime(frame["event_timestamp"], errors="coerce")
    frame["session_id"] = frame["session_id"].astype(str)

    quality = (
        frame["certified_for_replay"].fillna(False).astype(bool)
        & frame["is_completed_bar"].fillna(False).astype(bool)
        & ~frame["is_stale"].fillna(True).astype(bool)
        & ~frame["stale_price_flag"].fillna(True).astype(bool)
        & frame["underlying_completed_bar"].fillna(False).astype(bool)
        & ~frame["underlying_sparse_bar_flag"].fillna(True).astype(bool)
        & ~frame["underlying_stale_flag"].fillna(True).astype(bool)
        & frame["event_timestamp"].notna()
    )
    frame = frame.loc[quality].copy()
    keys = ["session_id", "event_timestamp"]

    underlying_columns = UNDERLYING_NUMERIC + UNDERLYING_BOOL
    consistency = frame.groupby(keys, observed=True)[underlying_columns].nunique(dropna=False)
    inconsistent_rows = int((consistency.max(axis=1) > 1).sum())
    underlying = frame.groupby(keys, observed=True)[underlying_columns].first()
    for column in UNDERLYING_BOOL:
        underlying[column] = underlying[column].fillna(False).astype(float)

    ce = wing_features(frame, "CE")
    pe = wing_features(frame, "PE")
    state = underlying.join(ce, how="inner").join(pe, how="inner").reset_index()
    state = state.loc[(state["ce_contract_count"] >= 3) & (state["pe_contract_count"] >= 3)].copy()
    state["wing_velocity_gap"] = state["ce_velocity_median"] - state["pe_velocity_median"]
    state["joint_abs_velocity"] = state["ce_velocity_median"].abs() + state["pe_velocity_median"].abs()
    state["wing_acceleration_gap"] = state["ce_acceleration_median"] - state["pe_acceleration_median"]
    state["wing_breadth_gap"] = state["ce_positive_share"] - state["pe_positive_share"]
    total_volume = np.exp(state["ce_log_volume"]) - 1.0 + np.exp(state["pe_log_volume"]) - 1.0
    state["ce_volume_share"] = (np.exp(state["ce_log_volume"]) - 1.0).div(total_volume.replace(0.0, np.nan)).fillna(0.5)
    state["surface_joint_positive"] = np.minimum(state["ce_positive_share"], state["pe_positive_share"])
    state["surface_joint_negative"] = np.minimum(1.0 - state["ce_positive_share"], 1.0 - state["pe_positive_share"])

    diagnostics = {
        "raw_joint_rows": raw_rows,
        "quality_joint_rows": len(frame),
        "state_rows_before_constituents": len(state),
        "state_sessions_before_constituents": int(state["session_id"].nunique()),
        "underlying_feature_inconsistent_timestamps": inconsistent_rows,
    }
    return state, diagnostics


def load_constituent_state(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = existing_columns(path, CONSTITUENT_REQUIRED)
    frame = pq.read_table(path, columns=columns).to_pandas()
    raw_rows = len(frame)
    quality = (
        ~frame["fallback"].fillna(True).astype(bool)
        & ~frame["mock"].fillna(True).astype(bool)
        & ~frame["synthetic"].fillna(True).astype(bool)
    )
    frame = frame.loc[quality].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")
    frame["session"] = frame["session"].astype(str)
    frame["symbol"] = frame["symbol"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.loc[frame["timestamp"].notna() & frame["close"].gt(0)].copy()
    frame = frame.sort_values(["session", "symbol", "timestamp"], kind="mergesort")
    frame["const_ret1"] = frame.groupby(["session", "symbol"], observed=True)["close"].pct_change(fill_method=None)

    counts = frame.groupby("symbol", observed=True).agg(rows=("symbol", "size"), median_close=("close", "median"))
    candidates = counts.loc[
        counts.index.to_series().astype(str).str.upper().str.contains("NIFTY", regex=False)
        & counts["median_close"].ge(10000)
    ].sort_values(["rows", "median_close"], ascending=[False, False])
    if candidates.empty:
        raise ValueError("Unable to identify NIFTY index symbol causally from constituent panel")
    index_symbol = str(candidates.index[0])

    index_rows = frame.loc[frame["symbol"].eq(index_symbol), ["session", "timestamp", "const_ret1"]].rename(
        columns={"session": "const_session", "timestamp": "const_timestamp", "const_ret1": "index_ret1"}
    )
    constituents = frame.loc[~frame["symbol"].eq(index_symbol) & frame["const_ret1"].notna()].copy()
    keys = ["session", "timestamp"]
    group = constituents.groupby(keys, observed=True)
    aggregate = group.agg(
        constituent_count=("symbol", "nunique"),
        constituent_ret_median=("const_ret1", "median"),
        constituent_ret_mean=("const_ret1", "mean"),
        constituent_up_share=("const_ret1", lambda values: float((values > 0).mean())),
        constituent_down_share=("const_ret1", lambda values: float((values < 0).mean())),
    )
    quantiles = group["const_ret1"].quantile([0.25, 0.75]).unstack(level=-1)
    aggregate["constituent_ret_iqr"] = quantiles.get(0.75, pd.Series(index=aggregate.index, dtype=float)) - quantiles.get(
        0.25, pd.Series(index=aggregate.index, dtype=float)
    )
    absolute = constituents[keys + ["const_ret1"]].copy()
    absolute["abs_ret"] = absolute["const_ret1"].abs()
    totals = absolute.groupby(keys, observed=True)["abs_ret"].sum()
    leaders = absolute.sort_values(keys + ["abs_ret"], ascending=[True, True, False], kind="mergesort")
    top5 = leaders.groupby(keys, observed=True, sort=False).head(5).groupby(keys, observed=True)["abs_ret"].sum()
    aggregate["constituent_top5_abs_share"] = top5.div(totals.replace(0.0, np.nan)).fillna(0.0)
    aggregate = aggregate.reset_index().rename(columns={"session": "const_session", "timestamp": "const_timestamp"})
    aggregate = aggregate.merge(index_rows, on=["const_session", "const_timestamp"], how="left")
    aggregate["index_constituent_gap"] = aggregate["index_ret1"] - aggregate["constituent_ret_median"]
    aggregate["constituent_abs_breadth"] = np.maximum(
        aggregate["constituent_up_share"], aggregate["constituent_down_share"]
    )

    diagnostics = {
        "raw_constituent_rows": raw_rows,
        "quality_constituent_rows": len(frame),
        "identified_index_symbol": index_symbol,
        "constituent_state_rows": len(aggregate),
        "constituent_state_sessions": int(aggregate["const_session"].nunique()),
    }
    return aggregate, diagnostics


def join_states(joint: pd.DataFrame, constituents: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    left = joint.sort_values("event_timestamp", kind="mergesort").copy()
    right = constituents.sort_values("const_timestamp", kind="mergesort").copy()
    merged = pd.merge_asof(
        left,
        right,
        left_on="event_timestamp",
        right_on="const_timestamp",
        direction="backward",
        tolerance=pd.Timedelta(minutes=5),
    )
    merged = merged.loc[merged["session_id"].eq(merged["const_session"])].copy()
    merged["constituent_lag_minutes"] = (
        merged["event_timestamp"] - merged["const_timestamp"]
    ).dt.total_seconds().div(60.0)
    merged = merged.loc[merged["constituent_lag_minutes"].between(0.0, 5.0, inclusive="both")].copy()
    diagnostics = {
        "joined_state_rows": len(merged),
        "joined_sessions": int(merged["session_id"].nunique()),
        "constituent_lag_min": float(merged["constituent_lag_minutes"].min()) if len(merged) else None,
        "constituent_lag_median": float(merged["constituent_lag_minutes"].median()) if len(merged) else None,
        "constituent_lag_max": float(merged["constituent_lag_minutes"].max()) if len(merged) else None,
    }
    return merged, diagnostics


def robust_fit(frame: pd.DataFrame, features: list[str]) -> tuple[list[str], pd.Series, pd.Series]:
    usable: list[str] = []
    medians: dict[str, float] = {}
    scales: dict[str, float] = {}
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce")
        finite = values[np.isfinite(values)]
        if len(finite) < int(len(frame) * 0.80):
            continue
        median = float(finite.median())
        iqr = float(finite.quantile(0.75) - finite.quantile(0.25))
        if not math.isfinite(iqr) or iqr <= 1e-12:
            continue
        usable.append(feature)
        medians[feature] = median
        scales[feature] = iqr
    if len(usable) < 12:
        raise ValueError(f"Insufficient robust features: {usable}")
    return usable, pd.Series(medians), pd.Series(scales)


def robust_transform(frame: pd.DataFrame, features: list[str], medians: pd.Series, scales: pd.Series) -> np.ndarray:
    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.fillna(medians)
    values = (numeric - medians).div(scales)
    return values.clip(-8.0, 8.0).to_numpy(dtype=float)


def js_divergence(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    left = left / left.sum()
    right = right / right.sum()
    middle = 0.5 * (left + right)
    eps = 1e-12
    return float(0.5 * np.sum(left * np.log((left + eps) / (middle + eps))) + 0.5 * np.sum(right * np.log((right + eps) / (middle + eps))))


def cluster_sessions(frame: pd.DataFrame, labels: np.ndarray, cluster: int) -> int:
    return int(frame.loc[labels == cluster, "session_id"].nunique())


def choose_state_model(
    observation: pd.DataFrame,
    replication: pd.DataFrame,
    x_observation: np.ndarray,
    x_replication: np.ndarray,
) -> tuple[KMeans, list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    models: dict[int, KMeans] = {}
    sample_size = min(5000, len(x_observation))
    rng = np.random.default_rng(RANDOM_STATE)
    sample_index = np.sort(rng.choice(len(x_observation), size=sample_size, replace=False)) if sample_size < len(x_observation) else np.arange(len(x_observation))
    for clusters in range(5, 11):
        model = KMeans(n_clusters=clusters, random_state=RANDOM_STATE, n_init=20, max_iter=500)
        obs_labels = model.fit_predict(x_observation)
        rep_labels = model.predict(x_replication)
        silhouette = float(silhouette_score(x_observation[sample_index], obs_labels[sample_index]))
        obs_counts = np.bincount(obs_labels, minlength=clusters).astype(float)
        rep_counts = np.bincount(rep_labels, minlength=clusters).astype(float)
        drifts: list[float] = []
        stable = 0
        cluster_records: list[dict[str, Any]] = []
        for cluster in range(clusters):
            obs_share = float(obs_counts[cluster] / len(obs_labels))
            rep_share = float(rep_counts[cluster] / len(rep_labels))
            obs_sessions = cluster_sessions(observation, obs_labels, cluster)
            rep_sessions = cluster_sessions(replication, rep_labels, cluster)
            if rep_counts[cluster] > 0:
                replication_median = np.median(x_replication[rep_labels == cluster], axis=0)
                drift = float(np.linalg.norm(replication_median - model.cluster_centers_[cluster]) / math.sqrt(x_replication.shape[1]))
                drifts.append(drift)
            else:
                drift = None
            is_stable = bool(obs_share >= 0.01 and rep_share >= 0.005 and obs_sessions >= 30 and rep_sessions >= 18 and drift is not None and drift <= 2.5)
            stable += int(is_stable)
            cluster_records.append({
                "cluster": cluster,
                "observation_share": obs_share,
                "replication_share": rep_share,
                "observation_sessions": obs_sessions,
                "replication_sessions": rep_sessions,
                "centroid_drift": drift,
                "stable": is_stable,
            })
        divergence = js_divergence(obs_counts, rep_counts)
        median_drift = float(np.median(drifts)) if drifts else 99.0
        stable_ratio = stable / clusters
        score = silhouette + 0.08 * stable_ratio - 0.04 * median_drift - 0.05 * divergence
        records.append({
            "clusters": clusters,
            "silhouette": silhouette,
            "occupancy_js_divergence": divergence,
            "median_centroid_drift": median_drift,
            "stable_clusters": stable,
            "stable_cluster_ratio": stable_ratio,
            "selection_score": score,
            "cluster_records": cluster_records,
        })
        models[clusters] = model
    best = sorted(records, key=lambda item: (item["selection_score"], -item["clusters"]), reverse=True)[0]
    return models[int(best["clusters"])], records, int(best["clusters"])


def state_signatures(model: KMeans, features: list[str], model_record: dict[str, Any]) -> list[dict[str, Any]]:
    stability = {int(item["cluster"]): item for item in model_record["cluster_records"]}
    catalog: list[dict[str, Any]] = []
    for cluster, center in enumerate(model.cluster_centers_):
        order = np.argsort(np.abs(center))[::-1]
        strongest = [
            {"feature": features[int(index)], "robust_z": float(center[int(index)])}
            for index in order[:8]
            if abs(float(center[int(index)])) >= 0.45
        ]
        record = {
            "state_id": f"S{cluster}",
            "cluster": cluster,
            "strongest_features": strongest,
            **stability[cluster],
        }
        catalog.append(record)
    return catalog


def sequence_catalog(frame: pd.DataFrame, label_column: str, length: int) -> tuple[Counter[str], dict[str, set[str]], int]:
    counts: Counter[str] = Counter()
    sessions: dict[str, set[str]] = defaultdict(set)
    total = 0
    for session, group in frame.sort_values(["session_id", "event_timestamp"], kind="mergesort").groupby("session_id", sort=False):
        labels = group[label_column].astype(str).tolist()
        timestamps = pd.to_datetime(group["event_timestamp"]).tolist()
        for index in range(len(labels) - length + 1):
            window = timestamps[index : index + length]
            gaps = [(window[position + 1] - window[position]).total_seconds() / 60.0 for position in range(length - 1)]
            if not all(0.0 < gap <= 6.0 for gap in gaps):
                continue
            motif = ">".join(labels[index : index + length])
            counts[motif] += 1
            sessions[motif].add(str(session))
            total += 1
    return counts, sessions, total


def motif_records(
    observation: pd.DataFrame,
    replication: pd.DataFrame,
    stable_states: set[str],
    length: int,
) -> list[dict[str, Any]]:
    obs_counts, obs_sessions, obs_total = sequence_catalog(observation, "state_id", length)
    rep_counts, rep_sessions, rep_total = sequence_catalog(replication, "state_id", length)
    obs_freq = observation["state_id"].value_counts(normalize=True).to_dict()
    rep_freq = replication["state_id"].value_counts(normalize=True).to_dict()
    records: list[dict[str, Any]] = []
    for motif, obs_count in obs_counts.items():
        states = motif.split(">")
        if not set(states).issubset(stable_states):
            continue
        rep_count = rep_counts.get(motif, 0)
        obs_share = obs_count / max(obs_total, 1)
        rep_share = rep_count / max(rep_total, 1)
        obs_baseline = float(np.prod([obs_freq.get(state, 0.0) for state in states]))
        rep_baseline = float(np.prod([rep_freq.get(state, 0.0) for state in states]))
        obs_lift = obs_share / obs_baseline if obs_baseline > 0 else 0.0
        rep_lift = rep_share / rep_baseline if rep_baseline > 0 else 0.0
        share_ratio = rep_share / obs_share if obs_share > 0 else 0.0
        passed = bool(
            obs_count >= (60 if length == 2 else 35)
            and rep_count >= (30 if length == 2 else 18)
            and len(obs_sessions[motif]) >= (28 if length == 2 else 22)
            and len(rep_sessions.get(motif, set())) >= (16 if length == 2 else 12)
            and obs_lift >= 1.25
            and rep_lift >= 1.20
            and 0.40 <= share_ratio <= 2.50
        )
        score = math.sqrt(obs_count * max(rep_count, 1)) * math.sqrt(max(obs_lift, 0.0) * max(rep_lift, 0.0))
        records.append({
            "motif": motif,
            "length": length,
            "observation_occurrences": obs_count,
            "replication_occurrences": rep_count,
            "observation_sessions": len(obs_sessions[motif]),
            "replication_sessions": len(rep_sessions.get(motif, set())),
            "observation_share": obs_share,
            "replication_share": rep_share,
            "observation_independence_lift": obs_lift,
            "replication_independence_lift": rep_lift,
            "replication_to_observation_share_ratio": share_ratio,
            "outcome_blind_freeze_gate": passed,
            "stability_score": score,
        })
    return sorted(records, key=lambda item: (item["outcome_blind_freeze_gate"], item["stability_score"], item["motif"]), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("runtime/research/outcome_blind_pattern_observation_v1"))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_root if args.output_root.is_absolute() else repo / args.output_root
    output.mkdir(parents=True, exist_ok=True)

    joint_path = locate_by_sha(repo, "repaired_joint_underlying_option_warehouse.parquet", JOINT_SHA256)
    constituent_path = locate_by_sha(repo, "constituent_index_5m.parquet", CONSTITUENT_SHA256)
    joint_state, joint_diagnostics = load_joint_state(joint_path)
    constituent_state, constituent_diagnostics = load_constituent_state(constituent_path)
    state, join_diagnostics = join_states(joint_state, constituent_state)
    if state.empty or state["session_id"].nunique() < 120:
        raise ValueError(f"Insufficient joined observation state: rows={len(state)} sessions={state['session_id'].nunique()}")

    sessions = sorted(state["session_id"].unique().tolist())
    observation_count = max(70, int(len(sessions) * 0.40))
    replication_count = max(40, int(len(sessions) * 0.25))
    if observation_count + replication_count >= len(sessions):
        replication_count = max(30, len(sessions) - observation_count - 20)
    observation_sessions = sessions[:observation_count]
    replication_sessions = sessions[observation_count : observation_count + replication_count]
    unopened_sessions = sessions[observation_count + replication_count :]
    observation = state.loc[state["session_id"].isin(observation_sessions)].copy()
    replication = state.loc[state["session_id"].isin(replication_sessions)].copy()

    surface_features = [
        "ce_velocity_median",
        "pe_velocity_median",
        "ce_acceleration_median",
        "pe_acceleration_median",
        "ce_positive_share",
        "pe_positive_share",
        "ce_velocity_iqr",
        "pe_velocity_iqr",
        "ce_volume_top3_share",
        "pe_volume_top3_share",
        "ce_oi_top3_share",
        "pe_oi_top3_share",
        "ce_log_volume",
        "pe_log_volume",
        "ce_log_oi",
        "pe_log_oi",
        "ce_log_premium",
        "pe_log_premium",
        "wing_velocity_gap",
        "joint_abs_velocity",
        "wing_acceleration_gap",
        "wing_breadth_gap",
        "ce_volume_share",
        "surface_joint_positive",
        "surface_joint_negative",
    ]
    constituent_features = [
        "index_ret1",
        "constituent_ret_median",
        "constituent_ret_mean",
        "constituent_ret_iqr",
        "constituent_up_share",
        "constituent_down_share",
        "constituent_abs_breadth",
        "constituent_top5_abs_share",
        "index_constituent_gap",
        "constituent_count",
    ]
    candidate_features = UNDERLYING_NUMERIC + UNDERLYING_BOOL + surface_features + constituent_features
    features, medians, scales = robust_fit(observation, candidate_features)
    x_observation = robust_transform(observation, features, medians, scales)
    x_replication = robust_transform(replication, features, medians, scales)

    model, model_records, selected_clusters = choose_state_model(observation, replication, x_observation, x_replication)
    observation["state_id"] = [f"S{value}" for value in model.predict(x_observation)]
    replication["state_id"] = [f"S{value}" for value in model.predict(x_replication)]
    selected_record = next(record for record in model_records if int(record["clusters"]) == selected_clusters)
    states = state_signatures(model, features, selected_record)
    stable_states = {record["state_id"] for record in states if record["stable"]}

    length2 = motif_records(observation, replication, stable_states, 2)
    length3 = motif_records(observation, replication, stable_states, 3)
    frozen = [record for record in [*length2, *length3] if record["outcome_blind_freeze_gate"]]
    frozen = sorted(frozen, key=lambda item: (item["stability_score"], item["motif"]), reverse=True)[:15]

    contract = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "stage": "outcome_blind_pattern_freeze",
        "joint_source": {"path": str(joint_path.relative_to(repo)), "sha256": JOINT_SHA256},
        "constituent_source": {"path": str(constituent_path.relative_to(repo)), "sha256": CONSTITUENT_SHA256},
        "observation_sessions": observation_sessions,
        "replication_sessions": replication_sessions,
        "unopened_sessions": unopened_sessions,
        "feature_policy": "explicit pre-outcome allowlist; robust scaling fit on observation sessions only",
        "model_policy": "K=5..10 chosen only by silhouette, occupancy stability, centroid drift, and recurring cluster support",
        "motif_policy": "two-step and three-step consecutive state transitions frozen only by frequency, cross-session support, independence lift, and replication stability",
        "outcomes_read": False,
        "pnl_calculated": False,
        "direction_selected": False,
        "hypothesis_named": False,
        "validation_opened": False,
        "holdout_opened": False,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_write(output / "observation_contract.json", contract)
    stable_write(output / "data_diagnostics.json", {**joint_diagnostics, **constituent_diagnostics, **join_diagnostics})
    stable_write(
        output / "feature_scaler.json",
        {
            "features": features,
            "observation_medians": {feature: float(medians[feature]) for feature in features},
            "observation_iqrs": {feature: float(scales[feature]) for feature in features},
        },
    )
    stable_write(output / "state_model_selection.json", {"selected_clusters": selected_clusters, "models": model_records})
    stable_write(output / "state_catalog.json", {"stable_state_ids": sorted(stable_states), "states": states})
    stable_write(output / "transition_catalog.json", {"length_2": length2, "length_3": length3})
    verdict = "OUTCOME_BLIND_PATTERNS_FROZEN_FOR_HYPOTHESIS_FORMATION" if frozen else "NO_STABLE_OUTCOME_BLIND_PATTERN_FOUND"
    result = {
        "principal_verdict": verdict,
        "selected_clusters": selected_clusters,
        "stable_state_ids": sorted(stable_states),
        "frozen_patterns": frozen,
        "observation_rows": len(observation),
        "replication_rows": len(replication),
        "observation_sessions": len(observation_sessions),
        "replication_sessions": len(replication_sessions),
        "unopened_sessions": len(unopened_sessions),
        "outcomes_read": False,
        "pnl_calculated": False,
        "hypothesis_named": False,
        "allowed_for_live_execution": False,
    }
    result["semantic_sha256"] = semantic_hash(result)
    stable_write(output / "frozen_observed_patterns.json", result)

    state_lookup = {record["state_id"]: record for record in states}
    lines = [
        "# Outcome-Blind Pattern Observation V1",
        "",
        f"Principal verdict: `{verdict}`",
        "",
        f"Selected state count: `{selected_clusters}`; stable states: `{len(stable_states)}`; frozen transitions: `{len(frozen)}`.",
        "",
        "No future, entry, exit, target, P&L, validation, or holdout outcome was read.",
        "",
        "## Stable state signatures",
        "",
    ]
    for state_id in sorted(stable_states):
        signature = state_lookup[state_id]
        features_text = ", ".join(
            f"{item['feature']}={item['robust_z']:+.2f}" for item in signature["strongest_features"]
        ) or "no dominant feature"
        lines.append(f"- `{state_id}`: {features_text}")
    lines.extend(["", "## Frozen recurring transitions", ""])
    if frozen:
        for record in frozen:
            lines.append(
                f"- `{record['motif']}`: observation {record['observation_occurrences']} occurrences / "
                f"{record['observation_sessions']} sessions, replication {record['replication_occurrences']} / "
                f"{record['replication_sessions']} sessions, lifts "
                f"{record['observation_independence_lift']:.2f} and {record['replication_independence_lift']:.2f}."
            )
    else:
        lines.append("- None met the outcome-blind recurrence and replication gates.")
    lines.extend(["", "Hypotheses must be formulated only after reviewing these frozen state signatures.", ""])
    (output / "OBSERVATION_RESULT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
