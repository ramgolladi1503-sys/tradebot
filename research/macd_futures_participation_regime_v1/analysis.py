from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

H1_THRESHOLD_INR = 8.5
MIN_ACTIVE_SIGNAL_SESSIONS = 30
PRIMARY_COST_BPS = 6.0
SCHEMA_VERSION = "MACD_FUTURES_PARTICIPATION_REGIME_V1"


class CampaignBlocked(RuntimeError):
    """Raised when source authority/schema prevents a truthful computation."""


@dataclass(frozen=True)
class SourcePaths:
    aligned_parquet: Path
    assignments: Path
    signal_paths: Path
    placebo_payoffs: Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise CampaignBlocked(f"MISSING_SOURCE:{path}")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise CampaignBlocked(f"UNSUPPORTED_SOURCE_TYPE:{path}")


def _require(df: pd.DataFrame, cols: Iterable[str], label: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise CampaignBlocked(f"{label}_SCHEMA_MISSING:{','.join(missing)}")


def _ist(series: pd.Series, label: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise CampaignBlocked(f"{label}_INVALID_TIMESTAMP_ROWS:{int(ts.isna().sum())}")
    try:
        tz = ts.dt.tz
    except AttributeError as exc:
        raise CampaignBlocked(f"{label}_MIXED_TIMESTAMP_SEMANTICS") from exc
    if tz is None:
        ts = ts.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    else:
        ts = ts.dt.tz_convert("Asia/Kolkata")
    return ts


def build_basis_state(aligned: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the already-frozen HYP_B1 literal state causally.

    HYP_B1 authority used raw_basis=futures_close-spot_close and a 15-row
    within-session difference on the minute-aligned panel. This function does
    not inspect any future outcome.
    """
    _require(
        aligned,
        ["timestamp", "session_date", "spot_close", "futures_close"],
        "ALIGNED",
    )
    df = aligned[["timestamp", "session_date", "spot_close", "futures_close"]].copy()
    df["timestamp"] = _ist(df["timestamp"], "ALIGNED")
    df["session_date"] = df["session_date"].astype(str)
    df = df.sort_values(["session_date", "timestamp"], kind="stable").reset_index(drop=True)
    if df.duplicated(["timestamp"]).any():
        raise CampaignBlocked("ALIGNED_DUPLICATE_TIMESTAMPS")
    if (df[["spot_close", "futures_close"]].isna().any(axis=1)).any():
        raise CampaignBlocked("ALIGNED_MISSING_PRICE_ROWS")

    df["raw_basis"] = df["futures_close"].astype(float) - df["spot_close"].astype(float)
    df["basis_chg_15m"] = df.groupby("session_date", sort=False)["raw_basis"].diff(15)
    df["basis_acceleration_15m"] = df.groupby("session_date", sort=False)["basis_chg_15m"].diff(15)

    df["h1_active"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    h1_known = df["basis_chg_15m"].notna()
    df.loc[h1_known, "h1_active"] = (
        df.loc[h1_known, "basis_chg_15m"] > H1_THRESHOLD_INR
    ).astype(bool)

    df["h2_active"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    h2_known = df["basis_chg_15m"].notna() & df["basis_acceleration_15m"].notna()
    df.loc[h2_known, "h2_active"] = (
        (df.loc[h2_known, "basis_chg_15m"] > 0.0)
        & (df.loc[h2_known, "basis_acceleration_15m"] > 0.0)
    ).astype(bool)
    return df[["timestamp", "session_date", "basis_chg_15m", "basis_acceleration_15m", "h1_active", "h2_active"]]


def bind_macd_ledgers(
    assignments: pd.DataFrame,
    signal_paths: pd.DataFrame,
    placebo_payoffs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bind old canonical MACD signal/placebo payoffs without recomputing MACD."""
    _require(
        assignments,
        ["replication_id", "signal_trade_id", "signal_origin", "matched_placebo_origin"],
        "ASSIGNMENTS",
    )
    _require(signal_paths, ["trade_id", "entry_timestamp", "net_6bps"], "SIGNAL_PATHS")
    _require(placebo_payoffs, ["replication_id", "origin_timestamp", "net_6bps"], "PLACEBO_PAYOFFS")

    a = assignments.copy()
    s = signal_paths.copy()
    p = placebo_payoffs.copy()
    a["signal_origin"] = _ist(a["signal_origin"], "ASSIGNMENT_SIGNAL_ORIGIN")
    a["matched_placebo_origin"] = _ist(a["matched_placebo_origin"], "ASSIGNMENT_PLACEBO_ORIGIN")
    s["entry_timestamp"] = _ist(s["entry_timestamp"], "SIGNAL_ENTRY")
    p["origin_timestamp"] = _ist(p["origin_timestamp"], "PLACEBO_ORIGIN")

    for frame, col in [(a, "signal_trade_id"), (s, "trade_id")]:
        frame[col] = frame[col].astype(str)
    for frame in (a, p):
        frame["replication_id"] = frame["replication_id"].astype(str)

    signal_origin_map = a[["signal_trade_id", "signal_origin"]].drop_duplicates()
    dup = signal_origin_map.duplicated("signal_trade_id", keep=False)
    if dup.any():
        raise CampaignBlocked("SIGNAL_TRADE_HAS_MULTIPLE_ORIGINS")

    signals = s.merge(
        signal_origin_map,
        left_on="trade_id",
        right_on="signal_trade_id",
        how="left",
        validate="one_to_one",
    )
    if signals["signal_origin"].isna().any():
        raise CampaignBlocked(
            f"SIGNAL_ORIGIN_BIND_MISSING:{int(signals['signal_origin'].isna().sum())}"
        )

    payoff_key = ["replication_id", "origin_timestamp"]
    if p.duplicated(payoff_key).any():
        raise CampaignBlocked("PLACEBO_PAYOFF_DUPLICATE_KEY")

    assigned = a.merge(
        p[["replication_id", "origin_timestamp", "net_6bps"]],
        left_on=["replication_id", "matched_placebo_origin"],
        right_on=["replication_id", "origin_timestamp"],
        how="left",
        validate="many_to_one",
    )
    if assigned["net_6bps"].isna().any():
        raise CampaignBlocked(
            f"PLACEBO_PAYOFF_BIND_MISSING:{int(assigned['net_6bps'].isna().sum())}"
        )

    return signals, assigned


def add_state_exact(
    origins: pd.DataFrame,
    state: pd.DataFrame,
    origin_col: str,
    state_col: str,
) -> pd.DataFrame:
    lookup = state[
        ["timestamp", "session_date", state_col, "basis_chg_15m", "basis_acceleration_15m"]
    ].copy()
    out = origins.merge(
        lookup,
        left_on=origin_col,
        right_on="timestamp",
        how="left",
        validate="many_to_one",
    )
    missing = out["timestamp"].isna()
    if missing.any():
        raise CampaignBlocked(
            f"STATE_TIMESTAMP_NOT_FOUND:{origin_col}:{int(missing.sum())}"
        )
    if out[state_col].isna().any():
        raise CampaignBlocked(
            f"STATE_UNAVAILABLE:{origin_col}:{int(out[state_col].isna().sum())}"
        )
    return out


def signal_state_support(
    signals: pd.DataFrame,
    state: pd.DataFrame,
    state_col: str,
) -> dict:
    """Count frozen-state signal support before any payoff analysis."""
    sig = add_state_exact(signals, state, "signal_origin", state_col)
    active = sig[sig[state_col] == True].copy()  # noqa: E712
    inactive = sig[sig[state_col] == False].copy()  # noqa: E712
    active_sessions = int(active["session_date"].nunique())
    return {
        "state_col": state_col,
        "signal_trades_total": int(len(sig)),
        "active_signal_trades": int(len(active)),
        "active_signal_sessions": active_sessions,
        "inactive_signal_trades": int(len(inactive)),
        "inactive_signal_sessions": int(inactive["session_date"].nunique()),
        "min_active_signal_sessions": MIN_ACTIVE_SIGNAL_SESSIONS,
        "support_gate_pass": active_sessions >= MIN_ACTIVE_SIGNAL_SESSIONS,
    }


def prepare_interaction(
    signals: pd.DataFrame,
    assigned: pd.DataFrame,
    state: pd.DataFrame,
    state_col: str,
) -> pd.DataFrame:
    sig = add_state_exact(signals, state, "signal_origin", state_col)
    sig = sig.rename(
        columns={state_col: "signal_state", "session_date": "signal_session_date"}
    )

    ass = add_state_exact(assigned, state, "matched_placebo_origin", state_col)
    ass = ass.rename(columns={state_col: "placebo_state"})

    sig_state = sig[
        [
            "trade_id",
            "signal_trade_id",
            "signal_origin",
            "signal_state",
            "signal_session_date",
            "net_6bps",
        ]
    ].copy()
    sig_state = sig_state.rename(columns={"net_6bps": "signal_net_6bps"})
    paired = ass.merge(
        sig_state,
        on=["signal_trade_id", "signal_origin"],
        how="inner",
        validate="many_to_one",
    )
    paired = paired[paired["placebo_state"] == paired["signal_state"]].copy()
    if paired.empty:
        raise CampaignBlocked("NO_STATE_COMPATIBLE_PLACEBOS")

    per_signal = (
        paired.groupby(
            [
                "signal_trade_id",
                "signal_origin",
                "signal_session_date",
                "signal_state",
                "signal_net_6bps",
            ],
            as_index=False,
        )
        .agg(
            compatible_placebo_n=("net_6bps", "size"),
            placebo_mean_net_6bps=("net_6bps", "mean"),
        )
    )
    per_signal["delta_net_6bps"] = (
        per_signal["signal_net_6bps"].astype(float)
        - per_signal["placebo_mean_net_6bps"].astype(float)
    )
    return per_signal


def _block_bootstrap_ci(
    values_by_session: pd.DataFrame,
    value_col: str,
    seed: int = 20260908,
    reps: int = 5000,
) -> tuple[float, float]:
    grouped = values_by_session.groupby("signal_session_date", as_index=False)[
        value_col
    ].mean()
    x = grouped[value_col].to_numpy(dtype=float)
    if len(x) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(reps, len(x)))
    means = x[idx].mean(axis=1)
    return tuple(np.quantile(means, [0.025, 0.975]).astype(float))


def summarize_interaction(per_signal: pd.DataFrame) -> dict:
    active = per_signal[per_signal["signal_state"] == True].copy()  # noqa: E712
    inactive = per_signal[per_signal["signal_state"] == False].copy()  # noqa: E712

    active_sessions = int(active["signal_session_date"].nunique())
    inactive_sessions = int(inactive["signal_session_date"].nunique())
    active_delta = (
        float(active["delta_net_6bps"].mean()) if len(active) else float("nan")
    )
    inactive_delta = (
        float(inactive["delta_net_6bps"].mean()) if len(inactive) else float("nan")
    )
    ci = (
        _block_bootstrap_ci(active, "delta_net_6bps")
        if len(active)
        else (float("nan"), float("nan"))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "active_signal_trades": int(len(active)),
        "active_signal_sessions": active_sessions,
        "inactive_signal_trades": int(len(inactive)),
        "inactive_signal_sessions": inactive_sessions,
        "active_signal_mean_net_6bps": (
            float(active["signal_net_6bps"].mean()) if len(active) else None
        ),
        "active_placebo_mean_net_6bps": (
            float(active["placebo_mean_net_6bps"].mean()) if len(active) else None
        ),
        "active_delta_net_6bps": (
            active_delta if np.isfinite(active_delta) else None
        ),
        "active_delta_block_bootstrap_95ci": (
            [float(ci[0]), float(ci[1])] if np.all(np.isfinite(ci)) else None
        ),
        "inactive_signal_mean_net_6bps": (
            float(inactive["signal_net_6bps"].mean()) if len(inactive) else None
        ),
        "inactive_placebo_mean_net_6bps": (
            float(inactive["placebo_mean_net_6bps"].mean()) if len(inactive) else None
        ),
        "inactive_delta_net_6bps": (
            inactive_delta if np.isfinite(inactive_delta) else None
        ),
        "interaction_lift_bps": (
            float(active_delta - inactive_delta)
            if np.isfinite(active_delta) and np.isfinite(inactive_delta)
            else None
        ),
        "median_compatible_placebos_per_signal": float(
            per_signal["compatible_placebo_n"].median()
        ),
        "min_compatible_placebos_per_signal": int(
            per_signal["compatible_placebo_n"].min()
        ),
    }


def frozen_hypothesis_result(summary: dict, hypothesis_id: str) -> dict:
    if summary["active_delta_net_6bps"] is None:
        status = "BLOCKED"
    else:
        status = "PRIMARY_ESTIMAND_COMPUTED_REQUIRES_FULL_GATES"
    return {"hypothesis_id": hypothesis_id, "status": status, **summary}


def source_manifest(paths: SourcePaths) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": {
            k: {"path": str(v), "sha256": sha256_file(v)}
            for k, v in {
                "aligned_parquet": paths.aligned_parquet,
                "assignments": paths.assignments,
                "signal_paths": paths.signal_paths,
                "placebo_payoffs": paths.placebo_payoffs,
            }.items()
        },
        "claim_boundary": [
            "retrospective research exposed 2024-2026 evidence only",
            "no untouched holdout claim",
            "no execution viability claim",
            "no broker/paper/live/order authority",
        ],
    }


def write_json(path: Path, obj: dict) -> None:
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
