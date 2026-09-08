from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked

ROBUSTNESS_SCHEMA = "MACD_FUTURES_PARTICIPATION_REGIME_V1_ROBUSTNESS"
DEFAULT_FOLDS = 4
DEFAULT_BOOTSTRAP_REPS = 5000
DEFAULT_SEED = 20260908


@dataclass(frozen=True)
class FoldResult:
    fold: int
    start_session: str
    end_session: str
    signal_trades: int
    active_signal_trades: int
    active_signal_sessions: int
    active_delta_net_6bps: float | None
    inactive_delta_net_6bps: float | None
    interaction_lift_bps: float | None


def _validate(per_signal: pd.DataFrame) -> pd.DataFrame:
    required = {
        "signal_trade_id",
        "signal_origin",
        "signal_session_date",
        "signal_state",
        "delta_net_6bps",
    }
    missing = sorted(required - set(per_signal.columns))
    if missing:
        raise CampaignBlocked(f"ROBUSTNESS_SCHEMA_MISSING:{','.join(missing)}")
    if per_signal.empty:
        raise CampaignBlocked("ROBUSTNESS_EMPTY_PER_SIGNAL")
    df = per_signal.copy()
    df["signal_session_date"] = df["signal_session_date"].astype(str)
    df["signal_origin"] = pd.to_datetime(df["signal_origin"], errors="coerce")
    if df["signal_origin"].isna().any():
        raise CampaignBlocked("ROBUSTNESS_INVALID_SIGNAL_ORIGIN")
    df["delta_net_6bps"] = pd.to_numeric(df["delta_net_6bps"], errors="coerce")
    if df["delta_net_6bps"].isna().any():
        raise CampaignBlocked("ROBUSTNESS_INVALID_DELTA")
    return df


def _means(df: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    active = df[df["signal_state"] == True]  # noqa: E712
    inactive = df[df["signal_state"] == False]  # noqa: E712
    a = float(active["delta_net_6bps"].mean()) if len(active) else None
    i = float(inactive["delta_net_6bps"].mean()) if len(inactive) else None
    lift = float(a - i) if a is not None and i is not None else None
    return a, i, lift


def chronological_fold_results(
    per_signal: pd.DataFrame, n_folds: int = DEFAULT_FOLDS
) -> pd.DataFrame:
    """Evaluate one frozen interaction over non-overlapping chronological sessions."""
    df = _validate(per_signal)
    sessions = np.array(sorted(df["signal_session_date"].unique()), dtype=object)
    if len(sessions) < n_folds:
        raise CampaignBlocked(
            f"ROBUSTNESS_INSUFFICIENT_SESSIONS_FOR_FOLDS:{len(sessions)}<{n_folds}"
        )
    partitions = np.array_split(sessions, n_folds)
    rows: list[dict] = []
    for idx, partition in enumerate(partitions, start=1):
        part = df[df["signal_session_date"].isin(partition)].copy()
        active = part[part["signal_state"] == True]  # noqa: E712
        a, i, lift = _means(part)
        rows.append(
            {
                "fold": idx,
                "start_session": str(partition[0]),
                "end_session": str(partition[-1]),
                "signal_trades": int(len(part)),
                "active_signal_trades": int(len(active)),
                "active_signal_sessions": int(active["signal_session_date"].nunique()),
                "active_delta_net_6bps": a,
                "inactive_delta_net_6bps": i,
                "interaction_lift_bps": lift,
            }
        )
    return pd.DataFrame(rows)


def session_bootstrap_interaction_ci(
    per_signal: pd.DataFrame,
    reps: int = DEFAULT_BOOTSTRAP_REPS,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Session-cluster bootstrap for active delta and interaction lift."""
    df = _validate(per_signal)
    sessions = sorted(df["signal_session_date"].unique())
    if len(sessions) < 2:
        return {
            "reps_requested": int(reps),
            "reps_valid_active": 0,
            "reps_valid_interaction": 0,
            "active_delta_95ci": None,
            "interaction_lift_95ci": None,
        }
    groups = {s: df[df["signal_session_date"] == s].copy() for s in sessions}
    rng = np.random.default_rng(seed)
    active_values: list[float] = []
    lift_values: list[float] = []
    for _ in range(reps):
        sampled = rng.choice(sessions, size=len(sessions), replace=True)
        pieces = [groups[str(s)] for s in sampled]
        boot = pd.concat(pieces, ignore_index=True)
        a, i, lift = _means(boot)
        if a is not None:
            active_values.append(a)
        if lift is not None:
            lift_values.append(lift)

    def ci(values: list[float]) -> list[float] | None:
        if not values:
            return None
        return [float(x) for x in np.quantile(np.asarray(values), [0.025, 0.975])]

    return {
        "reps_requested": int(reps),
        "seed": int(seed),
        "reps_valid_active": int(len(active_values)),
        "reps_valid_interaction": int(len(lift_values)),
        "active_delta_95ci": ci(active_values),
        "interaction_lift_95ci": ci(lift_values),
    }


def top_positive_session_removal(
    per_signal: pd.DataFrame, n_sessions: int = 5
) -> dict:
    """Remove the strongest active-state sessions and recompute the estimand."""
    df = _validate(per_signal)
    active = df[df["signal_state"] == True].copy()  # noqa: E712
    if active.empty:
        return {
            "removed_sessions": [],
            "remaining_active_signal_sessions": 0,
            "active_delta_after_removal": None,
            "interaction_lift_after_removal": None,
        }
    contribution = (
        active.groupby("signal_session_date", as_index=False)["delta_net_6bps"]
        .sum()
        .sort_values("delta_net_6bps", ascending=False, kind="stable")
    )
    removed = contribution.head(n_sessions)["signal_session_date"].tolist()
    remaining = df[~df["signal_session_date"].isin(removed)].copy()
    a, _, lift = _means(remaining)
    remaining_active = remaining[remaining["signal_state"] == True]  # noqa: E712
    return {
        "n_sessions_requested": int(n_sessions),
        "removed_sessions": [str(x) for x in removed],
        "remaining_active_signal_sessions": int(
            remaining_active["signal_session_date"].nunique()
        ),
        "active_delta_after_removal": a,
        "interaction_lift_after_removal": lift,
    }


def leave_one_quarter_out(per_signal: pd.DataFrame) -> list[dict]:
    """Temporal concentration diagnostic; no threshold re-selection is permitted."""
    df = _validate(per_signal)
    naive = df["signal_origin"].dt.tz_localize(None) if df["signal_origin"].dt.tz is not None else df["signal_origin"]
    df["quarter"] = naive.dt.to_period("Q").astype(str)
    rows: list[dict] = []
    for quarter in sorted(df["quarter"].unique()):
        kept = df[df["quarter"] != quarter].copy()
        a, i, lift = _means(kept)
        active = kept[kept["signal_state"] == True]  # noqa: E712
        rows.append(
            {
                "omitted_quarter": str(quarter),
                "remaining_signal_trades": int(len(kept)),
                "remaining_active_signal_sessions": int(
                    active["signal_session_date"].nunique()
                ),
                "active_delta_net_6bps": a,
                "inactive_delta_net_6bps": i,
                "interaction_lift_bps": lift,
            }
        )
    return rows


def robustness_bundle(per_signal: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = _validate(per_signal)
    folds = chronological_fold_results(df)
    fold_active = pd.to_numeric(folds["active_delta_net_6bps"], errors="coerce").dropna()
    fold_lift = pd.to_numeric(folds["interaction_lift_bps"], errors="coerce").dropna()
    bundle = {
        "schema": ROBUSTNESS_SCHEMA,
        "signal_trades": int(len(df)),
        "signal_sessions": int(df["signal_session_date"].nunique()),
        "bootstrap": session_bootstrap_interaction_ci(df),
        "top_five_session_removal": top_positive_session_removal(df, 5),
        "leave_one_quarter_out": leave_one_quarter_out(df),
        "temporal_summary": {
            "fold_count": int(len(folds)),
            "positive_active_delta_folds": int((fold_active > 0).sum()),
            "folds_with_active_delta": int(len(fold_active)),
            "median_fold_active_delta": (
                float(fold_active.median()) if len(fold_active) else None
            ),
            "positive_interaction_lift_folds": int((fold_lift > 0).sum()),
            "folds_with_interaction_lift": int(len(fold_lift)),
            "median_fold_interaction_lift": (
                float(fold_lift.median()) if len(fold_lift) else None
            ),
        },
        "claim_boundary": [
            "retrospective descriptive robustness only",
            "no untouched holdout claim",
            "no structural edge certification",
            "delay and permutation controls still separate required gates",
        ],
    }
    return folds, bundle
