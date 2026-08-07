from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .common import INDEX_SYMBOL, MIN_CONSTITUENTS, digest
from .discovery import FamilyModel, assign_family, fit_family_model, freeze_family_motifs

BATCH_D_FEATURES: dict[str, tuple[str, ...]] = {
    "RETURN_VOLUME_COUPLING": (
        "ret_volume_corr",
        "absret_volume_corr",
        "high_volume_breadth",
        "winner_loser_volume_gap",
        "signed_volume_imbalance",
        "high_volume_return_share",
    ),
    "VOLATILITY_TERM_STRUCTURE": (
        "median_vol6",
        "median_vol12",
        "vol_term_slope",
        "vol_cross_dispersion12",
        "high_vol_concentration12",
        "index_constituent_vol_ratio12",
    ),
    "RELATIVE_STRENGTH_MEMORY": (
        "rank_alignment_3_6",
        "rank_alignment_6_12",
        "top_quintile_persistence_3_6",
        "bottom_quintile_persistence_3_6",
        "relative_strength_dispersion6",
        "relative_strength_tail_spread6",
    ),
    "EXCURSION_ASYMMETRY": (
        "median_drawup6",
        "median_drawdown6",
        "excursion_asymmetry6",
        "positive_excursion_share6",
        "excursion_dispersion6",
        "extreme_excursion_concentration6",
    ),
    "VOLUME_LEADERSHIP_MIGRATION": (
        "top5_volume_share",
        "top_volume_turnover1",
        "top_volume_turnover3",
        "volume_rank_corr1",
        "volume_leader_return_alignment",
        "volume_concentration_delta1",
    ),
    "CONSTITUENT_ACCELERATION_GEOMETRY": (
        "acceleration_breadth",
        "acceleration_dispersion",
        "acceleration_tail_share",
        "ret_acceleration_corr",
        "acceleration_sign_entropy",
        "acceleration_concentration",
    ),
}


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 10:
        return np.nan
    x, y = a[mask], b[mask]
    if np.std(x) <= 1e-12 or np.std(y) <= 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _rank(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average", pct=True).to_numpy(float)


def _top_share(values: np.ndarray, n: int = 5) -> float:
    x = np.abs(values[np.isfinite(values)])
    total = float(x.sum())
    if total <= 1e-12:
        return 1.0
    return float(np.sort(x)[-min(n, len(x)):].sum() / total)


def _sign_entropy(values: np.ndarray) -> float:
    x = values[np.isfinite(values)]
    if x.size == 0:
        return np.nan
    p = float(np.mean(x > 0))
    if p <= 0 or p >= 1:
        return 0.0
    return float(-(p * math.log2(p) + (1 - p) * math.log2(1 - p)))


def _quintile_sets(ranks: np.ndarray) -> tuple[set[int], set[int]]:
    q = max(1, int(math.ceil(len(ranks) * 0.20)))
    order = np.argsort(ranks)
    return set(order[-q:]), set(order[:q])


def _session_metrics(ret: pd.DataFrame, volume: pd.DataFrame, index_ret: pd.Series) -> pd.DataFrame:
    timestamps = ret.index
    values = ret.to_numpy(float)
    volumes = volume.reindex(index=timestamps, columns=ret.columns).to_numpy(float)
    idx = pd.to_numeric(index_ret.reindex(timestamps), errors="coerce").to_numpy(float)
    vol_med20 = pd.DataFrame(volumes, index=timestamps, columns=ret.columns).shift(1).rolling(20, min_periods=5).median().to_numpy(float)
    volume_ratio = volumes / np.where(vol_med20 > 0, vol_med20, np.nan)
    vol6 = ret.shift(1).rolling(6, min_periods=4).std(ddof=0).to_numpy(float)
    vol12 = ret.shift(1).rolling(12, min_periods=6).std(ddof=0).to_numpy(float)
    idx_series = pd.Series(idx, index=timestamps)
    idx_vol12 = idx_series.shift(1).rolling(12, min_periods=6).std(ddof=0).to_numpy(float)
    cum3 = ret.rolling(3, min_periods=3).sum().to_numpy(float)
    cum6 = ret.rolling(6, min_periods=4).sum().to_numpy(float)
    cum12 = ret.rolling(12, min_periods=6).sum().to_numpy(float)
    acceleration = ret.diff().to_numpy(float)
    rows: list[dict[str, Any]] = []
    prior_top_volume: set[int] | None = None
    top_volume_history: list[set[int]] = []
    prior_top_share = np.nan

    for i, ts in enumerate(timestamps):
        current = values[i]
        finite = np.isfinite(current)
        if int(finite.sum()) < MIN_CONSTITUENTS:
            continue
        row: dict[str, Any] = {"timestamp": pd.Timestamp(ts)}

        # Return-volume cross-sectional coupling.
        vr = volume_ratio[i]
        common = finite & np.isfinite(vr)
        if int(common.sum()) >= MIN_CONSTITUENTS:
            r, v = current[common], vr[common]
            high = v >= np.nanquantile(v, 0.75)
            winners = r > 0
            losers = r < 0
            row["ret_volume_corr"] = _safe_corr(r, v)
            row["absret_volume_corr"] = _safe_corr(np.abs(r), v)
            row["high_volume_breadth"] = float(np.mean(r[high] > 0) - np.mean(r[high] < 0)) if high.any() else 0.0
            row["winner_loser_volume_gap"] = float(np.nanmedian(v[winners]) - np.nanmedian(v[losers])) if winners.any() and losers.any() else 0.0
            row["signed_volume_imbalance"] = float(np.sum(np.sign(r) * v) / max(np.sum(np.abs(v)), 1e-12))
            row["high_volume_return_share"] = float(np.sum(np.abs(r[high])) / max(np.sum(np.abs(r)), 1e-12)) if high.any() else 0.0
        else:
            for name in BATCH_D_FEATURES["RETURN_VOLUME_COUPLING"]:
                row[name] = np.nan

        # Cross-sectional own-volatility term structure.
        v6, v12 = vol6[i], vol12[i]
        valid_vol = np.isfinite(v6) & np.isfinite(v12)
        if int(valid_vol.sum()) >= MIN_CONSTITUENTS:
            a, b = v6[valid_vol], v12[valid_vol]
            high = b >= np.nanquantile(b, 0.75)
            row["median_vol6"] = float(np.median(a))
            row["median_vol12"] = float(np.median(b))
            row["vol_term_slope"] = float(np.median(a - b))
            row["vol_cross_dispersion12"] = float(np.std(b, ddof=0))
            row["high_vol_concentration12"] = float(np.sum(b[high]) / max(np.sum(b), 1e-12)) if high.any() else 0.0
            row["index_constituent_vol_ratio12"] = float(idx_vol12[i] / max(np.median(b), 1e-12)) if np.isfinite(idx_vol12[i]) else np.nan
        else:
            for name in BATCH_D_FEATURES["VOLATILITY_TERM_STRUCTURE"]:
                row[name] = np.nan

        # Cross-horizon relative-strength memory.
        c3, c6, c12 = cum3[i], cum6[i], cum12[i]
        valid_rs = np.isfinite(c3) & np.isfinite(c6) & np.isfinite(c12)
        if int(valid_rs.sum()) >= MIN_CONSTITUENTS:
            r3, r6, r12 = _rank(c3[valid_rs]), _rank(c6[valid_rs]), _rank(c12[valid_rs])
            top3, bot3 = _quintile_sets(r3)
            top6, bot6 = _quintile_sets(r6)
            q = max(1, len(top3))
            x6 = c6[valid_rs]
            row["rank_alignment_3_6"] = _safe_corr(r3, r6)
            row["rank_alignment_6_12"] = _safe_corr(r6, r12)
            row["top_quintile_persistence_3_6"] = float(len(top3 & top6) / q)
            row["bottom_quintile_persistence_3_6"] = float(len(bot3 & bot6) / q)
            row["relative_strength_dispersion6"] = float(np.std(x6, ddof=0))
            row["relative_strength_tail_spread6"] = float(np.quantile(x6, 0.90) - np.quantile(x6, 0.10))
        else:
            for name in BATCH_D_FEATURES["RELATIVE_STRENGTH_MEMORY"]:
                row[name] = np.nan

        # Per-constituent rolling excursion geometry over six bars.
        if i >= 5:
            w = values[i-5:i+1]
            valid_path = np.isfinite(w).all(axis=0)
            if int(valid_path.sum()) >= MIN_CONSTITUENTS:
                path = np.cumsum(w[:, valid_path], axis=0)
                drawup = np.max(path, axis=0)
                drawdown = -np.min(path, axis=0)
                asym = drawup - drawdown
                magnitude = np.maximum(drawup, drawdown)
                row["median_drawup6"] = float(np.median(drawup))
                row["median_drawdown6"] = float(np.median(drawdown))
                row["excursion_asymmetry6"] = float(np.median(asym))
                row["positive_excursion_share6"] = float(np.mean(asym > 0))
                row["excursion_dispersion6"] = float(np.std(asym, ddof=0))
                row["extreme_excursion_concentration6"] = _top_share(magnitude, 5)
            else:
                for name in BATCH_D_FEATURES["EXCURSION_ASYMMETRY"]:
                    row[name] = np.nan
        else:
            for name in BATCH_D_FEATURES["EXCURSION_ASYMMETRY"]:
                row[name] = np.nan

        # Volume leadership identity/migration.
        current_volume = volumes[i]
        valid_volume = np.isfinite(current_volume) & (current_volume >= 0)
        if int(valid_volume.sum()) >= MIN_CONSTITUENTS:
            vv = current_volume[valid_volume]
            rr = current[valid_volume]
            q = max(1, int(math.ceil(len(vv) * 0.20)))
            order = np.argsort(vv)
            top = set(order[-q:])
            top_share = float(np.sort(vv)[-5:].sum() / max(vv.sum(), 1e-12))
            row["top5_volume_share"] = top_share
            row["top_volume_turnover1"] = 1.0 - len(top & prior_top_volume) / q if prior_top_volume is not None else np.nan
            lag3 = top_volume_history[-3] if len(top_volume_history) >= 3 else None
            row["top_volume_turnover3"] = 1.0 - len(top & lag3) / q if lag3 is not None else np.nan
            row["volume_rank_corr1"] = _safe_corr(_rank(vv), _rank(volumes[i-1][valid_volume])) if i >= 1 and np.isfinite(volumes[i-1][valid_volume]).all() else np.nan
            dominant_sign = 1 if np.sum(rr[top_order := np.array(sorted(top), dtype=int)] > 0) >= np.sum(rr[top_order] < 0) else -1
            row["volume_leader_return_alignment"] = float(np.mean(np.sign(rr[top_order]) == dominant_sign))
            row["volume_concentration_delta1"] = float(top_share - prior_top_share) if np.isfinite(prior_top_share) else np.nan
            prior_top_volume = top
            top_volume_history.append(top)
            prior_top_share = top_share
        else:
            for name in BATCH_D_FEATURES["VOLUME_LEADERSHIP_MIGRATION"]:
                row[name] = np.nan

        # Constituent return acceleration geometry.
        acc = acceleration[i]
        valid_acc = np.isfinite(acc) & finite
        if int(valid_acc.sum()) >= MIN_CONSTITUENTS:
            a, r = acc[valid_acc], current[valid_acc]
            scale = float(np.std(a, ddof=0))
            tail = np.abs(a) >= (1.5 * scale) if scale > 1e-12 else np.zeros(len(a), dtype=bool)
            row["acceleration_breadth"] = float(np.mean(a > 0) - np.mean(a < 0))
            row["acceleration_dispersion"] = scale
            row["acceleration_tail_share"] = float(np.mean(tail))
            row["ret_acceleration_corr"] = _safe_corr(r, a)
            row["acceleration_sign_entropy"] = _sign_entropy(a)
            row["acceleration_concentration"] = _top_share(a, 5)
        else:
            for name in BATCH_D_FEATURES["CONSTITUENT_ACCELERATION_GEOMETRY"]:
                row[name] = np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def build_batch_d_frame(raw: pd.DataFrame, universe: Sequence[str], accepted_sessions: Sequence[str], base_cross: pd.DataFrame) -> pd.DataFrame:
    allowed = set(map(str, accepted_sessions))
    selected = raw.loc[raw["symbol"].isin([*universe, INDEX_SYMBOL]) & raw["session_date"].astype(str).isin(allowed)].copy()
    selected = selected.sort_values(["symbol", "session_date", "timestamp"], kind="mergesort")
    selected["log_ret1"] = selected.groupby(["symbol", "session_date"], observed=True, sort=False)["close"].transform(lambda s: np.log(s).diff())
    parts: list[pd.DataFrame] = []
    for session_date, group in selected.groupby("session_date", sort=True):
        cons = group.loc[group["symbol"].isin(universe)]
        idx = group.loc[group["symbol"].eq(INDEX_SYMBOL)].set_index("timestamp")["log_ret1"]
        ret = cons.pivot_table(index="timestamp", columns="symbol", values="log_ret1", aggfunc="last").sort_index()
        vol = cons.pivot_table(index="timestamp", columns="symbol", values="volume", aggfunc="last").sort_index()
        if ret.empty:
            continue
        metrics = _session_metrics(ret, vol, idx)
        metrics["session_date"] = str(session_date)
        parts.append(metrics)
    if not parts:
        raise ValueError("batch D produced no session metrics")
    metrics = pd.concat(parts, ignore_index=True)
    return base_cross.merge(metrics, on=["session_date", "timestamp"], how="inner", validate="one_to_one").sort_values(["session_date", "timestamp"], kind="mergesort").reset_index(drop=True)


def freeze_batch_d_discovery(frame: pd.DataFrame, splits: Mapping[str, Sequence[str]]) -> tuple[dict[str, FamilyModel], dict[str, pd.DataFrame], dict[str, Any]]:
    models: dict[str, FamilyModel] = {}
    assignments: dict[str, pd.DataFrame] = {}
    families: list[dict[str, Any]] = []
    development = frame.loc[frame["split"].isin(["observation", "replication", "validation"])].copy()
    total = 0
    for family, features in BATCH_D_FEATURES.items():
        model = fit_family_model(frame, family, features)
        if model is None:
            families.append({"family": family, "batch": "D", "principal_verdict": "FAMILY_NOT_MODELABLE_OUTCOME_BLIND", "motif_count": 0})
            continue
        assigned = assign_family(development, model)
        motifs = freeze_family_motifs(assigned, model, splits)
        models[family] = model
        assignments[family] = assigned
        total += len(motifs)
        families.append({
            "family": family,
            "batch": "D",
            "principal_verdict": "OUTCOME_BLIND_RECURRENT_TRANSITIONS_FROZEN" if motifs else "NO_RECURRENT_TRANSITION_PASSED_STABILITY_GATES",
            "motif_count": len(motifs),
            "model": {
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
            },
            "motifs": motifs,
        })
    catalog = {
        "principal_verdict": "AUTONOMOUS_BATCH_D_OUTCOME_BLIND_DISCOVERY_FROZEN",
        "batch": "D",
        "family_count": len(BATCH_D_FEATURES),
        "families_attempted": list(BATCH_D_FEATURES),
        "families": families,
        "total_frozen_motifs": total,
        "selection_basis": "remaining_close_volume_constituent_information_primitives_absent_from_batches_A_B_C",
        "policy": {
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "failed_prior_families_reopened": False,
            "global_multiple_testing_budget": True,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return models, assignments, catalog
