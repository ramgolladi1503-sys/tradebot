from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .common import INDEX_SYMBOL, MIN_CONSTITUENTS, RANDOM_STATE, digest
from .discovery import FamilyModel, assign_family, fit_family_model, freeze_family_motifs

BATCH_C_FEATURES: dict[str, tuple[str, ...]] = {
    "CORRELATION_SPECTRUM": (
        "avg_pairwise_corr6",
        "abs_pairwise_corr6",
        "negative_corr_share6",
        "first_eigen_share6",
        "effective_rank6",
        "corr_dispersion6",
    ),
    "RANK_MOBILITY": (
        "rank_corr_lag1",
        "rank_corr_lag3",
        "mean_rank_displacement1",
        "top_quintile_turnover1",
        "bottom_quintile_turnover1",
        "rank_sign_persistence1",
    ),
    "CROSS_SECTIONAL_SERIAL_DEPENDENCE": (
        "cross_serial_corr1",
        "cross_serial_corr2",
        "sign_persistence_share1",
        "sign_reversal_share1",
        "large_move_persistence1",
        "large_move_reversal1",
    ),
    "BETA_STRUCTURE": (
        "median_beta12",
        "beta_dispersion12",
        "high_beta_share12",
        "beta_return_cov12",
        "beta_sign_alignment12",
        "beta_tail_concentration12",
    ),
    "STANDARDIZED_EXTREME_COINCIDENCE": (
        "extreme_share12",
        "extreme_sign_imbalance12",
        "max_abs_z12",
        "top5_abs_z_share12",
        "extreme_same_sign_share12",
        "extreme_return_concentration12",
    ),
    "COMMON_FACTOR_RESIDUAL_STRUCTURE": (
        "factor_to_abs_ratio",
        "residual_dispersion",
        "residual_skew",
        "residual_sign_imbalance",
        "residual_tail_concentration",
        "residual_entropy",
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


def _entropy_from_signs(values: np.ndarray) -> float:
    x = values[np.isfinite(values)]
    if x.size == 0:
        return np.nan
    p = float(np.mean(x > 0))
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p)))


def _top_share(values: np.ndarray, n: int = 5) -> float:
    x = np.abs(values[np.isfinite(values)])
    total = float(x.sum())
    if total <= 1e-12:
        return 1.0
    return float(np.sort(x)[-min(n, len(x)):].sum() / total)


def _rank(values: np.ndarray) -> np.ndarray:
    s = pd.Series(values)
    return s.rank(method="average", pct=True).to_numpy(float)


def _distribution_skew(values: np.ndarray) -> float:
    x = values[np.isfinite(values)]
    if x.size < 10:
        return np.nan
    mean = float(np.mean(x))
    centered = x - mean
    m2 = float(np.mean(centered * centered))
    if m2 <= 1e-24:
        return 0.0
    return float(np.mean(centered ** 3) / (m2 ** 1.5))


def _session_metrics(session_returns: pd.DataFrame, index_returns: pd.Series) -> pd.DataFrame:
    values = session_returns.to_numpy(float)
    timestamps = session_returns.index
    symbols = list(session_returns.columns)
    idx = pd.to_numeric(index_returns.reindex(timestamps), errors="coerce").to_numpy(float)
    rows: list[dict[str, Any]] = []
    own_std = session_returns.shift(1).rolling(12, min_periods=6).std(ddof=0)

    for i, ts in enumerate(timestamps):
        current = values[i]
        finite = np.isfinite(current)
        if int(finite.sum()) < MIN_CONSTITUENTS:
            continue
        x = current[finite]
        row: dict[str, Any] = {"timestamp": pd.Timestamp(ts)}

        # Correlation spectrum from trailing six completed constituent return vectors.
        start6 = max(0, i - 5)
        window6 = values[start6 : i + 1]
        valid_cols = np.isfinite(window6).all(axis=0)
        w = window6[:, valid_cols]
        if w.shape[0] >= 4 and w.shape[1] >= MIN_CONSTITUENTS:
            corr = np.corrcoef(w, rowvar=False)
            upper = corr[np.triu_indices(corr.shape[0], k=1)]
            finite_upper = upper[np.isfinite(upper)]
            eig = np.linalg.eigvalsh(np.nan_to_num(corr, nan=0.0))
            eig = np.clip(eig, 0.0, None)
            eig_sum = float(eig.sum())
            probs = eig / eig_sum if eig_sum > 1e-12 else np.zeros_like(eig)
            entropy = -float(np.sum(probs[probs > 0] * np.log(probs[probs > 0])))
            row.update({
                "avg_pairwise_corr6": float(np.mean(finite_upper)) if finite_upper.size else np.nan,
                "abs_pairwise_corr6": float(np.mean(np.abs(finite_upper))) if finite_upper.size else np.nan,
                "negative_corr_share6": float(np.mean(finite_upper < 0)) if finite_upper.size else np.nan,
                "first_eigen_share6": float(eig[-1] / eig_sum) if eig_sum > 1e-12 else np.nan,
                "effective_rank6": float(np.exp(entropy)) if eig_sum > 1e-12 else np.nan,
                "corr_dispersion6": float(np.std(finite_upper, ddof=0)) if finite_upper.size else np.nan,
            })
        else:
            for name in BATCH_C_FEATURES["CORRELATION_SPECTRUM"]:
                row[name] = np.nan

        # Cross-sectional rank mobility.
        if i >= 1:
            prev = values[i - 1]
            common = finite & np.isfinite(prev)
            if int(common.sum()) >= MIN_CONSTITUENTS:
                now_rank, prev_rank = _rank(current[common]), _rank(prev[common])
                q = max(1, int(math.ceil(len(now_rank) * 0.20)))
                now_order, prev_order = np.argsort(now_rank), np.argsort(prev_rank)
                top_now, top_prev = set(now_order[-q:]), set(prev_order[-q:])
                bot_now, bot_prev = set(now_order[:q]), set(prev_order[:q])
                row["rank_corr_lag1"] = _safe_corr(now_rank, prev_rank)
                row["mean_rank_displacement1"] = float(np.mean(np.abs(now_rank - prev_rank)))
                row["top_quintile_turnover1"] = 1.0 - len(top_now & top_prev) / q
                row["bottom_quintile_turnover1"] = 1.0 - len(bot_now & bot_prev) / q
                row["rank_sign_persistence1"] = float(np.mean(np.sign(current[common]) == np.sign(prev[common])))
            else:
                for name in ("rank_corr_lag1", "mean_rank_displacement1", "top_quintile_turnover1", "bottom_quintile_turnover1", "rank_sign_persistence1"):
                    row[name] = np.nan
        else:
            for name in ("rank_corr_lag1", "mean_rank_displacement1", "top_quintile_turnover1", "bottom_quintile_turnover1", "rank_sign_persistence1"):
                row[name] = np.nan
        if i >= 3:
            lag3 = values[i - 3]
            common3 = finite & np.isfinite(lag3)
            row["rank_corr_lag3"] = _safe_corr(_rank(current[common3]), _rank(lag3[common3])) if int(common3.sum()) >= MIN_CONSTITUENTS else np.nan
        else:
            row["rank_corr_lag3"] = np.nan

        # Cross-sectional serial dependence.
        if i >= 1:
            prev = values[i - 1]
            common = finite & np.isfinite(prev)
            if int(common.sum()) >= MIN_CONSTITUENTS:
                a, b = current[common], prev[common]
                threshold = float(np.nanquantile(np.abs(b), 0.75))
                large = np.abs(b) >= threshold
                row["cross_serial_corr1"] = _safe_corr(a, b)
                row["sign_persistence_share1"] = float(np.mean(np.sign(a) == np.sign(b)))
                row["sign_reversal_share1"] = float(np.mean(np.sign(a) == -np.sign(b)))
                row["large_move_persistence1"] = float(np.mean(np.sign(a[large]) == np.sign(b[large]))) if large.any() else np.nan
                row["large_move_reversal1"] = float(np.mean(np.sign(a[large]) == -np.sign(b[large]))) if large.any() else np.nan
            else:
                for name in ("cross_serial_corr1", "sign_persistence_share1", "sign_reversal_share1", "large_move_persistence1", "large_move_reversal1"):
                    row[name] = np.nan
        else:
            for name in ("cross_serial_corr1", "sign_persistence_share1", "sign_reversal_share1", "large_move_persistence1", "large_move_reversal1"):
                row[name] = np.nan
        if i >= 2:
            lag2 = values[i - 2]
            common2 = finite & np.isfinite(lag2)
            row["cross_serial_corr2"] = _safe_corr(current[common2], lag2[common2]) if int(common2.sum()) >= MIN_CONSTITUENTS else np.nan
        else:
            row["cross_serial_corr2"] = np.nan

        # Rolling constituent beta structure versus the index, using only past/current completed bars.
        start12 = max(0, i - 11)
        wret = values[start12 : i + 1]
        widx = idx[start12 : i + 1]
        if len(widx) >= 6 and np.isfinite(widx).all() and float(np.var(widx)) > 1e-14:
            valid_beta_cols = np.isfinite(wret).all(axis=0)
            wb = wret[:, valid_beta_cols]
            if wb.shape[1] >= MIN_CONSTITUENTS:
                centered_idx = widx - np.mean(widx)
                centered_wb = wb - np.mean(wb, axis=0)
                betas = np.mean(centered_wb * centered_idx[:, None], axis=0) / np.var(widx)
                current_beta_ret = current[valid_beta_cols]
                absb = np.abs(betas)
                high = absb >= np.nanquantile(absb, 0.75)
                row["median_beta12"] = float(np.median(betas))
                row["beta_dispersion12"] = float(np.std(betas, ddof=0))
                row["high_beta_share12"] = float(np.mean(high))
                row["beta_return_cov12"] = float(np.cov(betas, current_beta_ret, ddof=0)[0, 1])
                row["beta_sign_alignment12"] = float(np.mean(np.sign(betas) == np.sign(current_beta_ret)))
                row["beta_tail_concentration12"] = _top_share(betas, 5)
            else:
                for name in BATCH_C_FEATURES["BETA_STRUCTURE"]:
                    row[name] = np.nan
        else:
            for name in BATCH_C_FEATURES["BETA_STRUCTURE"]:
                row[name] = np.nan

        # Standardized extreme coincidence from each symbol's own trailing volatility.
        std_row = own_std.iloc[i].to_numpy(float)
        valid_z = finite & np.isfinite(std_row) & (std_row > 1e-12)
        if int(valid_z.sum()) >= MIN_CONSTITUENTS:
            z = current[valid_z] / std_row[valid_z]
            extreme = np.abs(z) >= 1.5
            if extreme.any():
                extreme_z = z[extreme]
                extreme_ret = current[valid_z][extreme]
                dominant = 1 if np.sum(extreme_z > 0) >= np.sum(extreme_z < 0) else -1
                row["extreme_share12"] = float(np.mean(extreme))
                row["extreme_sign_imbalance12"] = float(np.mean(extreme_z > 0) - np.mean(extreme_z < 0))
                row["max_abs_z12"] = float(np.max(np.abs(z)))
                row["top5_abs_z_share12"] = _top_share(z, 5)
                row["extreme_same_sign_share12"] = float(np.mean(np.sign(extreme_z) == dominant))
                row["extreme_return_concentration12"] = _top_share(extreme_ret, 5)
            else:
                row.update({"extreme_share12": 0.0, "extreme_sign_imbalance12": 0.0, "max_abs_z12": float(np.max(np.abs(z))), "top5_abs_z_share12": _top_share(z, 5), "extreme_same_sign_share12": 0.0, "extreme_return_concentration12": 0.0})
        else:
            for name in BATCH_C_FEATURES["STANDARDIZED_EXTREME_COINCIDENCE"]:
                row[name] = np.nan

        # Common-factor residual structure at the current completed interval.
        factor = float(np.mean(x))
        residual = x - factor
        mean_abs = float(np.mean(np.abs(x)))
        tail_cut = float(np.quantile(np.abs(residual), 0.80))
        tail = residual[np.abs(residual) >= tail_cut]
        row["factor_to_abs_ratio"] = float(abs(factor) / max(mean_abs, 1e-12))
        row["residual_dispersion"] = float(np.std(residual, ddof=0))
        row["residual_skew"] = _distribution_skew(residual)
        row["residual_sign_imbalance"] = float(np.mean(residual > 0) - np.mean(residual < 0))
        row["residual_tail_concentration"] = _top_share(tail, 5) if tail.size else 0.0
        row["residual_entropy"] = _entropy_from_signs(residual)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def build_batch_c_frame(
    raw: pd.DataFrame,
    universe: Sequence[str],
    accepted_sessions: Sequence[str],
    base_cross: pd.DataFrame,
) -> pd.DataFrame:
    allowed = set(map(str, accepted_sessions))
    selected = raw.loc[
        raw["symbol"].isin([*universe, INDEX_SYMBOL])
        & raw["session_date"].astype(str).isin(allowed)
    ].copy()
    selected = selected.sort_values(["symbol", "session_date", "timestamp"], kind="mergesort")
    selected["log_ret1"] = selected.groupby(["symbol", "session_date"], observed=True, sort=False)["close"].transform(lambda s: np.log(s).diff())
    parts: list[pd.DataFrame] = []
    for session_date, group in selected.groupby("session_date", sort=True):
        cons = group.loc[group["symbol"].isin(universe)]
        idx = group.loc[group["symbol"].eq(INDEX_SYMBOL)].set_index("timestamp")["log_ret1"]
        pivot = cons.pivot_table(index="timestamp", columns="symbol", values="log_ret1", aggfunc="last").sort_index()
        if pivot.empty:
            continue
        metrics = _session_metrics(pivot, idx)
        metrics["session_date"] = str(session_date)
        parts.append(metrics)
    if not parts:
        raise ValueError("batch C produced no session metrics")
    metrics = pd.concat(parts, ignore_index=True)
    result = base_cross.merge(metrics, on=["session_date", "timestamp"], how="inner", validate="one_to_one")
    return result.sort_values(["session_date", "timestamp"], kind="mergesort").reset_index(drop=True)


def freeze_batch_c_discovery(
    frame: pd.DataFrame,
    splits: Mapping[str, Sequence[str]],
) -> tuple[dict[str, FamilyModel], dict[str, pd.DataFrame], dict[str, Any]]:
    models: dict[str, FamilyModel] = {}
    assignments: dict[str, pd.DataFrame] = {}
    families: list[dict[str, Any]] = []
    development = frame.loc[frame["split"].isin(["observation", "replication", "validation"])].copy()
    total = 0
    for family, features in BATCH_C_FEATURES.items():
        model = fit_family_model(frame, family, features)
        if model is None:
            families.append({"family": family, "batch": "C", "principal_verdict": "FAMILY_NOT_MODELABLE_OUTCOME_BLIND", "motif_count": 0})
            continue
        assigned = assign_family(development, model)
        motifs = freeze_family_motifs(assigned, model, splits)
        models[family] = model
        assignments[family] = assigned
        total += len(motifs)
        families.append({
            "family": family,
            "batch": "C",
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
        "principal_verdict": "AUTONOMOUS_BATCH_C_OUTCOME_BLIND_DISCOVERY_FROZEN",
        "batch": "C",
        "family_count": len(BATCH_C_FEATURES),
        "families_attempted": list(BATCH_C_FEATURES),
        "families": families,
        "total_frozen_motifs": total,
        "selection_basis": "information_primitive_taxonomy_absent_from_batches_A_B_not_prior_outcome_performance",
        "policy": {
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "failed_batch_a_b_families_reopened": False,
            "global_multiple_testing_budget": True,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return models, assignments, catalog
