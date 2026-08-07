from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import RobustScaler

from research.autonomous_structural_edge_exhaustion_v1 import common as C

CAMPAIGN = "history_first_pattern_miner_v1"
RANDOM_STATE = 20260808
DAY_FEATURES = (
    "index_path",
    "breadth_imbalance",
    "dispersion_std",
    "top5_abs_share",
    "index_eqw_divergence",
    "median_volume_ratio",
)
PREFIX_FEATURES = (
    "index_path",
    "breadth_imbalance",
    "dispersion_std",
    "top5_abs_share",
    "index_eqw_divergence",
    "median_volume_ratio",
    "leader_churn",
    "participation_ratio",
)
DAY_GRID = np.linspace(0.05, 1.0, 20)
PREFIX_CUTOFFS = (0.20, 0.35, 0.50, 0.65)
PREFIX_GRID_POINTS = 8
K_CANDIDATES = (3, 4, 5, 6, 7, 8)
MIN_OBS_CLUSTER = 12
MIN_REP_CLUSTER = 6
MIN_BRANCH_OBS = 8
MIN_BRANCH_REP = 4
MIN_BRANCH_SHARE_OBS = 0.18
MIN_BRANCH_SHARE_REP = 0.12
MIN_EFFECT_OBS = 0.50
MIN_EFFECT_REP = 0.25


def _digest(value: Any) -> str:
    return C.digest(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _prepare_structural_frame(cross: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for session_date, group in cross.groupby("session_date", sort=True):
        x = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
        if x.empty:
            continue
        open_close = float(x["index_close"].iloc[0])
        if not math.isfinite(open_close) or open_close <= 0:
            continue
        x["index_path"] = np.log(pd.to_numeric(x["index_close"], errors="coerce") / open_close)
        parts.append(x)
    if not parts:
        raise ValueError("no structural sessions")
    return pd.concat(parts, ignore_index=True).sort_values(["session_date", "timestamp"], kind="mergesort")


def _interp_session(group: pd.DataFrame, features: Sequence[str], grid: np.ndarray) -> np.ndarray | None:
    x = group.sort_values("session_progress", kind="mergesort")
    progress = pd.to_numeric(x["session_progress"], errors="coerce").to_numpy(float)
    if len(progress) < 10 or not np.isfinite(progress).any():
        return None
    values: list[float] = []
    for feature in features:
        arr = pd.to_numeric(x[feature], errors="coerce").to_numpy(float)
        mask = np.isfinite(progress) & np.isfinite(arr)
        if int(mask.sum()) < 6:
            return None
        xp = progress[mask]
        fp = arr[mask]
        keep = np.r_[True, np.diff(xp) > 0]
        xp = xp[keep]
        fp = fp[keep]
        if len(xp) < 4:
            return None
        values.extend(np.interp(grid, xp, fp, left=fp[0], right=fp[-1]).tolist())
    return np.asarray(values, dtype=float)


def build_session_embeddings(frame: pd.DataFrame, features: Sequence[str], grid: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for session_date, group in frame.groupby("session_date", sort=True):
        vector = _interp_session(group, features, grid)
        if vector is None or not np.isfinite(vector).all():
            continue
        split = str(group["split"].iloc[0])
        rows.append({"session_date": str(session_date), "split": split, "vector": vector})
    if not rows:
        raise ValueError("no session embeddings")
    return pd.DataFrame(rows)


def _fit_cluster_model(vectors: np.ndarray, min_cluster: int = MIN_OBS_CLUSTER) -> tuple[RobustScaler, PCA, KMeans, dict[str, Any]]:
    scaler = RobustScaler(quantile_range=(10.0, 90.0)).fit(vectors)
    scaled = scaler.transform(vectors)
    n_components = max(2, min(12, scaled.shape[1], scaled.shape[0] - 1))
    pca = PCA(n_components=n_components, random_state=RANDOM_STATE).fit(scaled)
    reduced = pca.transform(scaled)
    best: tuple[float, KMeans, np.ndarray] | None = None
    diagnostics = []
    for k in K_CANDIDATES:
        if len(reduced) < k * min_cluster:
            continue
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20).fit(reduced)
        labels = model.labels_
        counts = np.bincount(labels, minlength=k)
        if int(counts.min()) < min_cluster:
            diagnostics.append({"k": k, "accepted": False, "reason": "small_cluster", "min_cluster": int(counts.min())})
            continue
        score = float(silhouette_score(reduced, labels))
        diagnostics.append({"k": k, "accepted": True, "silhouette": score, "counts": counts.tolist()})
        if best is None or score > best[0]:
            best = (score, model, labels)
    if best is None:
        raise ValueError("no stable observation clustering candidate")
    score, model, labels = best
    authority = {
        "fit_scope": "observation_only",
        "chosen_k": int(model.n_clusters),
        "silhouette": score,
        "observation_cluster_counts": np.bincount(labels, minlength=model.n_clusters).tolist(),
        "pca_explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "candidate_diagnostics": diagnostics,
    }
    authority["semantic_sha256"] = _digest(authority)
    return scaler, pca, model, authority


def discover_day_archetypes(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, tuple[RobustScaler, PCA, KMeans]]:
    embeddings = build_session_embeddings(frame, DAY_FEATURES, DAY_GRID)
    obs = embeddings.loc[embeddings["split"].eq("observation")].copy()
    rep = embeddings.loc[embeddings["split"].eq("replication")].copy()
    if len(obs) < 100 or len(rep) < 30:
        raise ValueError(f"insufficient observation/replication embeddings obs={len(obs)} rep={len(rep)}")
    obs_matrix = np.stack(obs["vector"].to_list())
    scaler, pca, model, fit = _fit_cluster_model(obs_matrix)

    def assign(table: pd.DataFrame) -> pd.DataFrame:
        out = table.copy()
        matrix = np.stack(out["vector"].to_list())
        reduced = pca.transform(scaler.transform(matrix))
        out["day_archetype"] = model.predict(reduced).astype(int)
        out["centroid_distance"] = np.linalg.norm(reduced - model.cluster_centers_[out["day_archetype"].to_numpy(int)], axis=1)
        return out

    assigned = pd.concat([assign(obs), assign(rep)], ignore_index=True)
    obs_counts = assigned.loc[assigned["split"].eq("observation"), "day_archetype"].value_counts().sort_index()
    rep_counts = assigned.loc[assigned["split"].eq("replication"), "day_archetype"].value_counts().sort_index()
    recurrent = []
    for label in range(model.n_clusters):
        n_obs = int(obs_counts.get(label, 0))
        n_rep = int(rep_counts.get(label, 0))
        if n_obs >= MIN_OBS_CLUSTER and n_rep >= MIN_REP_CLUSTER:
            recurrent.append(label)
    catalog = {
        "principal_verdict": "OUTCOME_BLIND_DAY_ARCHETYPES_DISCOVERED" if recurrent else "NO_RECURRENT_DAY_ARCHETYPES",
        "features": list(DAY_FEATURES),
        "grid": DAY_GRID.tolist(),
        "fit": fit,
        "observation_sessions": int(len(obs)),
        "replication_sessions": int(len(rep)),
        "recurrent_archetypes": recurrent,
        "replication_counts": {str(int(k)): int(v) for k, v in rep_counts.items()},
        "outcomes_opened": False,
        "unopened_sessions_used": False,
    }
    catalog["semantic_sha256"] = _digest(catalog)
    return catalog, assigned, (scaler, pca, model)


def _prefix_grid(cutoff: float) -> np.ndarray:
    return np.linspace(max(0.02, cutoff / PREFIX_GRID_POINTS), cutoff, PREFIX_GRID_POINTS)


def _prefix_endpoint_table(frame: pd.DataFrame, day_assignments: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    subset = frame.loc[frame["split"].isin(["observation", "replication"])].copy()
    embeddings = build_session_embeddings(subset, PREFIX_FEATURES, _prefix_grid(cutoff))
    endpoints = day_assignments[["session_date", "split", "day_archetype"]].copy()
    return embeddings.merge(endpoints, on=["session_date", "split"], how="inner", validate="one_to_one")


def discover_prefix_branches(frame: pd.DataFrame, day_assignments: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    all_records: list[dict[str, Any]] = []
    branch_tables: list[dict[str, Any]] = []
    for cutoff in PREFIX_CUTOFFS:
        table = _prefix_endpoint_table(frame, day_assignments, cutoff)
        obs = table.loc[table["split"].eq("observation")].copy()
        rep = table.loc[table["split"].eq("replication")].copy()
        if len(obs) < 100 or len(rep) < 30:
            continue
        scaler, pca, model, fit = _fit_cluster_model(np.stack(obs["vector"].to_list()), min_cluster=10)
        for part in (obs, rep):
            matrix = np.stack(part["vector"].to_list())
            reduced = pca.transform(scaler.transform(matrix))
            part["prefix_cluster"] = model.predict(reduced).astype(int)
        combined = pd.concat([obs, rep], ignore_index=True)
        for cluster_id in range(model.n_clusters):
            cluster = combined.loc[combined["prefix_cluster"].eq(cluster_id)].copy()
            obs_c = cluster.loc[cluster["split"].eq("observation")]
            rep_c = cluster.loc[cluster["split"].eq("replication")]
            obs_end = obs_c["day_archetype"].value_counts()
            rep_end = rep_c["day_archetype"].value_counts()
            qualifying = []
            for endpoint, n_obs in obs_end.items():
                n_rep = int(rep_end.get(endpoint, 0))
                obs_share = float(n_obs / max(1, len(obs_c)))
                rep_share = float(n_rep / max(1, len(rep_c)))
                if int(n_obs) >= MIN_BRANCH_OBS and n_rep >= MIN_BRANCH_REP and obs_share >= MIN_BRANCH_SHARE_OBS and rep_share >= MIN_BRANCH_SHARE_REP:
                    qualifying.append({
                        "day_archetype": int(endpoint),
                        "observation_count": int(n_obs),
                        "replication_count": n_rep,
                        "observation_share": obs_share,
                        "replication_share": rep_share,
                    })
            if len(qualifying) < 2:
                continue
            record = {
                "branch_id": f"P{int(round(cutoff * 100)):02d}_C{cluster_id}",
                "cutoff": cutoff,
                "prefix_cluster": cluster_id,
                "fit": fit,
                "observation_prefix_count": int(len(obs_c)),
                "replication_prefix_count": int(len(rep_c)),
                "qualifying_endings": sorted(qualifying, key=lambda r: (-r["observation_count"], r["day_archetype"])),
                "outcomes_opened": False,
            }
            all_records.append(record)
            branch_tables.append({"record": record, "table": cluster})
    catalog = {
        "principal_verdict": "RECURRENT_SIMILAR_PREFIX_DIVERGENT_ENDINGS_FOUND" if all_records else "NO_RECURRENT_PREFIX_DIVERGENCE_FOUND",
        "cutoffs": list(PREFIX_CUTOFFS),
        "features": list(PREFIX_FEATURES),
        "branch_count": len(all_records),
        "branches": all_records,
        "outcomes_opened": False,
        "unopened_sessions_used": False,
    }
    catalog["semantic_sha256"] = _digest(catalog)
    return catalog, branch_tables


def _latest_prefix_features(frame: pd.DataFrame, sessions: Sequence[str], cutoff: float) -> pd.DataFrame:
    wanted = set(map(str, sessions))
    rows = []
    for session_date, group in frame.loc[frame["session_date"].astype(str).isin(wanted)].groupby("session_date", sort=True):
        x = group.loc[group["session_progress"].le(cutoff)].sort_values("timestamp", kind="mergesort")
        if x.empty:
            continue
        row = x.iloc[-1]
        payload = {"session_date": str(session_date)}
        for feature in PREFIX_FEATURES:
            payload[feature] = _safe_float(row.get(feature), np.nan)
        payload["breadth_delta3"] = _safe_float(row.get("breadth_delta3"), np.nan)
        payload["dispersion_delta3"] = _safe_float(row.get("dispersion_delta3"), np.nan)
        payload["concentration_delta3"] = _safe_float(row.get("concentration_delta3"), np.nan)
        payload["divergence_delta3"] = _safe_float(row.get("divergence_delta3"), np.nan)
        rows.append(payload)
    return pd.DataFrame(rows)


def _effect(a: np.ndarray, b: np.ndarray) -> float:
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 4 or len(b) < 4:
        return 0.0
    pooled = math.sqrt(max(1e-18, (float(np.var(a, ddof=1)) + float(np.var(b, ddof=1))) / 2.0))
    return float((np.mean(a) - np.mean(b)) / pooled)


def discover_branch_discriminators(frame: pd.DataFrame, branch_tables: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    candidate_features = (*PREFIX_FEATURES, "breadth_delta3", "dispersion_delta3", "concentration_delta3", "divergence_delta3")
    for item in branch_tables:
        record = dict(item["record"])
        table = item["table"]
        endings = [int(x["day_archetype"]) for x in record["qualifying_endings"][:2]]
        if len(endings) < 2:
            continue
        obs = table.loc[table["split"].eq("observation") & table["day_archetype"].isin(endings)]
        rep = table.loc[table["split"].eq("replication") & table["day_archetype"].isin(endings)]
        obs_feat = _latest_prefix_features(frame, obs["session_date"].astype(str).tolist(), float(record["cutoff"])).merge(
            obs[["session_date", "day_archetype"]], on="session_date", how="inner"
        )
        rep_feat = _latest_prefix_features(frame, rep["session_date"].astype(str).tolist(), float(record["cutoff"])).merge(
            rep[["session_date", "day_archetype"]], on="session_date", how="inner"
        )
        effects = []
        for feature in candidate_features:
            oa = pd.to_numeric(obs_feat.loc[obs_feat["day_archetype"].eq(endings[0]), feature], errors="coerce").to_numpy(float)
            ob = pd.to_numeric(obs_feat.loc[obs_feat["day_archetype"].eq(endings[1]), feature], errors="coerce").to_numpy(float)
            ra = pd.to_numeric(rep_feat.loc[rep_feat["day_archetype"].eq(endings[0]), feature], errors="coerce").to_numpy(float)
            rb = pd.to_numeric(rep_feat.loc[rep_feat["day_archetype"].eq(endings[1]), feature], errors="coerce").to_numpy(float)
            obs_effect = _effect(oa, ob)
            rep_effect = _effect(ra, rb)
            stable = abs(obs_effect) >= MIN_EFFECT_OBS and abs(rep_effect) >= MIN_EFFECT_REP and np.sign(obs_effect) == np.sign(rep_effect)
            effects.append({"feature": feature, "observation_effect": obs_effect, "replication_effect": rep_effect, "stable": bool(stable)})
        stable_effects = sorted((x for x in effects if x["stable"]), key=lambda x: -abs(x["observation_effect"]))
        if not stable_effects:
            continue
        records.append({
            "branch_id": record["branch_id"],
            "cutoff": record["cutoff"],
            "ending_pair": endings,
            "stable_discriminators": stable_effects[:5],
            "all_effects": effects,
            "outcomes_opened": False,
        })
    catalog = {
        "principal_verdict": "OUTCOME_BLIND_BRANCH_DISCRIMINATORS_FROZEN" if records else "NO_STABLE_PRE_BRANCH_DISCRIMINATOR_FOUND",
        "record_count": len(records),
        "records": records,
        "selection_rule": {
            "observation_abs_effect_min": MIN_EFFECT_OBS,
            "replication_abs_effect_min": MIN_EFFECT_REP,
            "same_sign_required": True,
        },
        "outcomes_opened": False,
        "validation_sessions_used": False,
        "unopened_sessions_used": False,
    }
    catalog["semantic_sha256"] = _digest(catalog)
    return catalog


def run_discovery(source_file: Path) -> dict[str, Any]:
    source = C.verify_source(source_file)
    raw = C.canonicalize_source(source_file)
    index_rows, accepted = C.accepted_index_sessions(raw)
    splits = C.split_sessions(accepted)
    universe = C.select_observation_universe(raw, index_rows, splits)
    cross = C.build_cross_sectional_frame(raw, index_rows, universe["selected_symbols"], accepted)
    cross = C.add_split_column(cross, splits)
    structural = _prepare_structural_frame(cross)
    discovery_frame = structural.loc[structural["split"].isin(["observation", "replication"])].copy()

    day_catalog, day_assignments, _ = discover_day_archetypes(discovery_frame)
    prefix_catalog, branch_tables = discover_prefix_branches(discovery_frame, day_assignments)
    discriminator_catalog = discover_branch_discriminators(discovery_frame, branch_tables)

    result = {
        "campaign": CAMPAIGN,
        "source_authority": source,
        "chronological_split": {k: list(v) for k, v in splits.items()},
        "universe_authority": universe,
        "day_archetypes": day_catalog,
        "prefix_divergence": prefix_catalog,
        "branch_discriminators": discriminator_catalog,
        "policy": {
            "discovery_inputs": ["observation", "replication"],
            "future_market_returns_opened": False,
            "validation_market_outcomes_opened": False,
            "unopened_sessions_touched": False,
            "strategy_rules_created": False,
            "hypotheses_ready_for_downstream_freeze": bool(discriminator_catalog["record_count"]),
        },
    }
    result["semantic_sha256"] = _digest(result)
    return result


def write_discovery(output_root: Path, result: Mapping[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for key in ("source_authority", "chronological_split", "universe_authority", "day_archetypes", "prefix_divergence", "branch_discriminators"):
        C.stable_write(output_root / f"{key}.json", result[key])
    C.stable_write(output_root / "final_discovery_authority.json", result)
    report = [
        "# History-First Pattern Miner V1",
        "",
        "Discovery is outcome-blind. Observation and replication structural paths are used; validation and unopened market outcomes remain sealed.",
        "",
        f"- Day archetypes: `{result['day_archetypes']['principal_verdict']}`",
        f"- Recurrent archetype IDs: {result['day_archetypes']['recurrent_archetypes']}",
        f"- Similar-prefix divergent branches: {result['prefix_divergence']['branch_count']}",
        f"- Branches with stable pre-branch discriminators: {result['branch_discriminators']['record_count']}",
        "",
        "## Next authority",
        "",
        "Only stable outcome-blind branch/discriminator records may be converted into frozen mechanism hypotheses for a separate downstream outcome test.",
        "No strategy, P&L, entry, stop, target, option, shadow, paper, live, or order authority is created here.",
    ]
    (output_root / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
