from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .common import *


def robust_fit(values: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    arr = values.to_numpy(float)
    median = np.nanmedian(arr, axis=0)
    q25 = np.nanquantile(arr, 0.25, axis=0)
    q75 = np.nanquantile(arr, 0.75, axis=0)
    scale = q75 - q25
    std = np.nanstd(arr, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, np.where(std > 1e-12, std, 1.0))
    return median.astype(float), scale.astype(float)


def robust_apply(values: pd.DataFrame, median: np.ndarray, scale: np.ndarray) -> np.ndarray:
    arr = values.to_numpy(float)
    transformed = (arr - median) / scale
    return np.clip(transformed, -8.0, 8.0)


@dataclass
class FamilyModel:
    family: str
    features: tuple[str, ...]
    median: np.ndarray
    scale: np.ndarray
    k: int
    centers: np.ndarray
    confidence_threshold: float
    observation_silhouette: float
    model_semantic_sha256: str


def fit_family_model(frame: pd.DataFrame, family: str, features: Sequence[str]) -> FamilyModel | None:
    obs = frame.loc[frame["split"].eq("observation"), [*features]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(obs) < 1000:
        return None
    std = obs.std(axis=0, ddof=0).to_numpy(float)
    if int(np.sum(np.isfinite(std) & (std > 1e-12))) < max(4, len(features) - 1):
        return None
    median, scale = robust_fit(obs)
    x = robust_apply(obs, median, scale)
    if len(x) > 1200:
        rng = np.random.default_rng(RANDOM_STATE + len(x) + len(family))
        sample_idx = np.sort(rng.choice(len(x), size=1200, replace=False))
        x_score = x[sample_idx]
    else:
        x_score = x
    best: tuple[float, int, KMeans] | None = None
    for k in K_CANDIDATES:
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = model.fit_predict(x)
        counts = np.bincount(labels, minlength=k)
        if counts.min() < max(50, int(0.02 * len(x))):
            continue
        try:
            score_labels = model.predict(x_score)
            score = float(silhouette_score(x_score, score_labels))
        except Exception:
            continue
        if best is None or score > best[0]:
            best = (score, k, model)
    if best is None:
        return None
    score, k, model = best
    distances = model.transform(x)
    order = np.sort(distances, axis=1)
    margin = (order[:, 1] - order[:, 0]) / np.maximum(order[:, 1], 1e-12)
    confidence_threshold = float(np.quantile(margin, 0.20))
    payload = {
        "family": family,
        "features": list(features),
        "median": median.tolist(),
        "scale": scale.tolist(),
        "k": int(k),
        "centers": model.cluster_centers_.tolist(),
        "confidence_threshold": confidence_threshold,
        "observation_silhouette": score,
        "fit_scope": "observation_only",
        "outcomes_seen": False,
    }
    return FamilyModel(
        family=family,
        features=tuple(features),
        median=median,
        scale=scale,
        k=int(k),
        centers=np.asarray(model.cluster_centers_, dtype=float),
        confidence_threshold=confidence_threshold,
        observation_silhouette=score,
        model_semantic_sha256=digest(payload),
    )


def assign_family(frame: pd.DataFrame, model: FamilyModel) -> pd.DataFrame:
    valid = frame[[*model.features]].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    result = frame.loc[valid, ["session_date", "timestamp", "split", "session_progress", "index_close", "index_ret1", "index_ret3", "index_vol6"]].copy()
    x = robust_apply(frame.loc[valid, list(model.features)], model.median, model.scale)
    delta = x[:, None, :] - model.centers[None, :, :]
    dist = np.sqrt(np.sum(delta * delta, axis=2))
    labels = np.argmin(dist, axis=1)
    ordered = np.sort(dist, axis=1)
    margin = (ordered[:, 1] - ordered[:, 0]) / np.maximum(ordered[:, 1], 1e-12)
    result["state"] = labels.astype(int)
    result["assignment_margin"] = margin
    result["confident"] = margin >= model.confidence_threshold
    result["family"] = model.family
    return result.reset_index(drop=True)


def compressed_sequence(group: pd.DataFrame) -> list[dict[str, Any]]:
    ordered = group.sort_values("timestamp", kind="mergesort")
    seq: list[dict[str, Any]] = []
    prior_state: int | None = None
    for row in ordered.itertuples(index=False):
        if not bool(getattr(row, "confident")):
            prior_state = None
            continue
        state = int(getattr(row, "state"))
        if prior_state == state:
            continue
        seq.append({
            "state": state,
            "timestamp": pd.Timestamp(getattr(row, "timestamp")),
            "session_progress": float(getattr(row, "session_progress")),
            "assignment_margin": float(getattr(row, "assignment_margin")),
        })
        prior_state = state
    return seq


def motif_counts(assigned: pd.DataFrame, split: str, lengths: Sequence[int] = (2, 3)) -> tuple[Counter[tuple[int, ...]], Counter[tuple[int, ...]]]:
    occurrences: Counter[tuple[int, ...]] = Counter()
    sessions: Counter[tuple[int, ...]] = Counter()
    lane = assigned.loc[assigned["split"].eq(split)]
    for _, group in lane.groupby("session_date", sort=True):
        seq = compressed_sequence(group)
        seen: set[tuple[int, ...]] = set()
        states = [int(item["state"]) for item in seq]
        for length in lengths:
            for i in range(0, len(states) - length + 1):
                motif = tuple(states[i:i + length])
                if len(set(motif)) == 1:
                    continue
                occurrences[motif] += 1
                seen.add(motif)
        sessions.update(seen)
    return occurrences, sessions


def freeze_family_motifs(assigned: pd.DataFrame, model: FamilyModel, splits: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
    obs_occ, obs_sessions = motif_counts(assigned, "observation")
    rep_occ, rep_sessions = motif_counts(assigned, "replication")
    obs_n = len(splits["observation"])
    rep_n = len(splits["replication"])
    candidates: list[dict[str, Any]] = []
    for motif, obs_session_count in obs_sessions.items():
        rep_session_count = int(rep_sessions.get(motif, 0))
        if obs_session_count < 20 or rep_session_count < 10:
            continue
        obs_share = obs_session_count / obs_n
        rep_share = rep_session_count / rep_n
        ratio = rep_share / max(obs_share, 1e-12)
        if not 0.50 <= ratio <= 2.00:
            continue
        score = min(obs_share, rep_share) * min(ratio, 1.0 / ratio)
        candidates.append({
            "family": model.family,
            "motif": list(motif),
            "motif_length": len(motif),
            "observation_occurrences": int(obs_occ[motif]),
            "observation_sessions": int(obs_session_count),
            "replication_occurrences": int(rep_occ.get(motif, 0)),
            "replication_sessions": int(rep_session_count),
            "observation_session_share": float(obs_share),
            "replication_session_share": float(rep_share),
            "replication_share_ratio": float(ratio),
            "recurrence_score": float(score),
            "outcomes_seen_when_frozen": False,
        })
    candidates.sort(key=lambda x: (-x["recurrence_score"], -x["replication_sessions"], tuple(x["motif"])))
    chosen = candidates[:MAX_MOTIFS_PER_FAMILY]
    for i, item in enumerate(chosen):
        item["motif_id"] = f"{model.family}:M{i}:{'-'.join(map(str, item['motif']))}"
        item["semantic_sha256"] = digest(item)
    return chosen


def freeze_discovery(frame: pd.DataFrame, splits: Mapping[str, Sequence[str]]) -> tuple[dict[str, FamilyModel], dict[str, pd.DataFrame], dict[str, Any]]:
    models: dict[str, FamilyModel] = {}
    assignments: dict[str, pd.DataFrame] = {}
    families: list[dict[str, Any]] = []
    all_motifs: list[dict[str, Any]] = []
    development_frame = frame.loc[frame["split"].isin(["observation", "replication", "validation"])].copy()
    for family, features in FAMILY_FEATURES.items():
        model = fit_family_model(frame, family, features)
        if model is None:
            families.append({"family": family, "principal_verdict": "FAMILY_NOT_MODELABLE_OUTCOME_BLIND", "motif_count": 0})
            continue
        assigned = assign_family(development_frame, model)
        motifs = freeze_family_motifs(assigned, model, splits)
        models[family] = model
        assignments[family] = assigned
        model_payload = {
            "family": family,
            "features": list(model.features),
            "k": model.k,
            "centers": model.centers.tolist(),
            "median": model.median.tolist(),
            "scale": model.scale.tolist(),
            "confidence_threshold": model.confidence_threshold,
            "observation_silhouette": model.observation_silhouette,
            "model_semantic_sha256": model.model_semantic_sha256,
            "fit_scope": "observation_only",
            "outcomes_seen": False,
        }
        families.append({
            "family": family,
            "principal_verdict": "OUTCOME_BLIND_RECURRENT_TRANSITIONS_FROZEN" if motifs else "NO_RECURRENT_TRANSITION_PASSED_STABILITY_GATES",
            "motif_count": len(motifs),
            "model": model_payload,
            "motifs": motifs,
        })
        all_motifs.extend(motifs)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "principal_verdict": "AUTONOMOUS_OUTCOME_BLIND_FAMILY_DISCOVERY_FROZEN",
        "families_attempted": list(FAMILY_FEATURES),
        "family_count": len(FAMILY_FEATURES),
        "families": families,
        "total_frozen_motifs": len(all_motifs),
        "policy": {
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "family_definitions_predeclared": True,
            "global_multiple_testing_budget": True,
            "failed_family_reopening_authorized": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return models, assignments, catalog


def hypothesis_catalog(discovery: Mapping[str, Any]) -> dict[str, Any]:
    hypotheses: list[dict[str, Any]] = []
    for family_record in discovery.get("families", []):
        for motif in family_record.get("motifs", []):
            for horizon in HORIZONS:
                item = {
                    "hypothesis_id": f"H::{motif['motif_id']}::H{horizon}",
                    "family": motif["family"],
                    "motif_id": motif["motif_id"],
                    "motif": motif["motif"],
                    "horizon_bars": int(horizon),
                    "horizon_minutes": int(horizon * 5),
                    "signal_definition": "first_chronological_confident_state_sequence_completion_per_session",
                    "entry_delay_bars": 1,
                    "direction_selected": False,
                    "outcomes_seen_when_frozen": False,
                }
                item["semantic_sha256"] = digest(item)
                hypotheses.append(item)
    catalog = {
        "principal_verdict": "AUTONOMOUS_MECHANISM_HYPOTHESES_FROZEN" if hypotheses else "NO_AUTONOMOUS_MECHANISM_HYPOTHESES_FROZEN",
        "hypothesis_count": len(hypotheses),
        "hypotheses": hypotheses,
        "policy": {
            "outcomes_seen_when_frozen": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def first_motif_signal(group: pd.DataFrame, motif: Sequence[int]) -> pd.Timestamp | None:
    seq = compressed_sequence(group)
    states = [int(item["state"]) for item in seq]
    m = tuple(map(int, motif))
    length = len(m)
    for i in range(0, len(states) - length + 1):
        if tuple(states[i:i + length]) == m:
            return pd.Timestamp(seq[i + length - 1]["timestamp"])
    return None


def precompute_motif_signals(
    discovery: Mapping[str, Any],
    assignments: Mapping[str, pd.DataFrame],
) -> dict[str, dict[str, pd.Timestamp]]:
    result: dict[str, dict[str, pd.Timestamp]] = {}
    motifs_by_family: dict[str, list[tuple[str, tuple[int, ...]]]] = defaultdict(list)
    for family_record in discovery.get("families", []):
        for motif in family_record.get("motifs", []):
            mid = str(motif["motif_id"])
            motifs_by_family[str(motif["family"])].append((mid, tuple(map(int, motif["motif"]))))
            result[mid] = {}
    for family, motif_specs in motifs_by_family.items():
        assigned = assignments.get(family)
        if assigned is None or assigned.empty:
            continue
        for session_date, group in assigned.groupby("session_date", sort=True):
            seq = compressed_sequence(group)
            states = [int(item["state"]) for item in seq]
            if not states:
                continue
            for mid, motif in motif_specs:
                length = len(motif)
                for i in range(0, len(states) - length + 1):
                    if tuple(states[i:i + length]) == motif:
                        result[mid][str(session_date)] = pd.Timestamp(seq[i + length - 1]["timestamp"])
                        break
    return result
