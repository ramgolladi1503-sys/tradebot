from __future__ import annotations

import math

import pandas as pd

H1_THRESHOLD_INR = 8.5
ORACLE_TOLERANCE = 1e-9


class OracleError(RuntimeError):
    pass


def _require(df: pd.DataFrame, cols: list[str], label: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise OracleError(f"{label}_MISSING:{','.join(missing)}")


def _ist(series: pd.Series, label: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise OracleError(f"{label}_INVALID_TIMESTAMP")
    if ts.dt.tz is None:
        return ts.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    return ts.dt.tz_convert("Asia/Kolkata")


def reconstruct_state(aligned: pd.DataFrame, state_id: str) -> pd.DataFrame:
    """Independent literal state reconstruction; does not import primary builder."""
    _require(
        aligned,
        ["timestamp", "session_date", "spot_close", "futures_close"],
        "ALIGNED",
    )
    df = aligned[["timestamp", "session_date", "spot_close", "futures_close"]].copy()
    df["timestamp"] = _ist(df["timestamp"], "ALIGNED")
    df["session_date"] = df["session_date"].astype(str)
    df = df.sort_values(["session_date", "timestamp"], kind="mergesort").reset_index(drop=True)
    if df.duplicated("timestamp").any():
        raise OracleError("ALIGNED_DUPLICATE_TIMESTAMP")
    df["basis"] = pd.to_numeric(df["futures_close"], errors="raise") - pd.to_numeric(
        df["spot_close"], errors="raise"
    )
    df["d15"] = df.groupby("session_date", sort=False)["basis"].diff(15)
    df["a15"] = df.groupby("session_date", sort=False)["d15"].diff(15)

    if state_id == "H1":
        known = df["d15"].notna()
        values = pd.Series(pd.NA, index=df.index, dtype="boolean")
        values.loc[known] = (df.loc[known, "d15"] > H1_THRESHOLD_INR).astype(bool)
    elif state_id == "H2":
        known = df["d15"].notna() & df["a15"].notna()
        values = pd.Series(pd.NA, index=df.index, dtype="boolean")
        values.loc[known] = (
            (df.loc[known, "d15"] > 0.0) & (df.loc[known, "a15"] > 0.0)
        ).astype(bool)
    else:
        raise OracleError(f"UNKNOWN_STATE_ID:{state_id}")

    return pd.DataFrame({"timestamp": df["timestamp"], "oracle_state": values})


def _state_join(df: pd.DataFrame, state: pd.DataFrame, origin_col: str) -> pd.DataFrame:
    out = df.merge(
        state,
        left_on=origin_col,
        right_on="timestamp",
        how="left",
        validate="many_to_one",
    )
    if out["timestamp"].isna().any():
        raise OracleError(f"STATE_TIMESTAMP_NOT_FOUND:{origin_col}")
    if out["oracle_state"].isna().any():
        raise OracleError(f"STATE_UNAVAILABLE:{origin_col}")
    return out


def reconstruct_per_signal(
    aligned: pd.DataFrame,
    assignments: pd.DataFrame,
    signal_paths: pd.DataFrame,
    placebo_payoffs: pd.DataFrame,
    state_id: str,
) -> pd.DataFrame:
    _require(
        assignments,
        ["replication_id", "signal_trade_id", "signal_origin", "matched_placebo_origin"],
        "ASSIGNMENTS",
    )
    _require(signal_paths, ["trade_id", "net_6bps"], "SIGNALS")
    _require(
        placebo_payoffs,
        ["replication_id", "origin_timestamp", "net_6bps"],
        "PLACEBOS",
    )

    a = assignments.copy()
    s = signal_paths.copy()
    p = placebo_payoffs.copy()
    a["signal_origin"] = _ist(a["signal_origin"], "SIGNAL_ORIGIN")
    a["matched_placebo_origin"] = _ist(a["matched_placebo_origin"], "PLACEBO_ORIGIN")
    p["origin_timestamp"] = _ist(p["origin_timestamp"], "PLACEBO_PAYOFF_ORIGIN")
    a["replication_id"] = a["replication_id"].astype(str)
    p["replication_id"] = p["replication_id"].astype(str)
    a["signal_trade_id"] = a["signal_trade_id"].astype(str)
    s["trade_id"] = s["trade_id"].astype(str)

    signal_origins = a[["signal_trade_id", "signal_origin"]].drop_duplicates()
    if signal_origins.duplicated("signal_trade_id").any():
        raise OracleError("SIGNAL_ORIGIN_NOT_UNIQUE")

    signal = s[["trade_id", "net_6bps"]].merge(
        signal_origins,
        left_on="trade_id",
        right_on="signal_trade_id",
        how="inner",
        validate="one_to_one",
    )
    signal = signal.rename(columns={"net_6bps": "signal_net_6bps"})

    if p.duplicated(["replication_id", "origin_timestamp"]).any():
        raise OracleError("PLACEBO_KEY_NOT_UNIQUE")
    assigned = a.merge(
        p[["replication_id", "origin_timestamp", "net_6bps"]],
        left_on=["replication_id", "matched_placebo_origin"],
        right_on=["replication_id", "origin_timestamp"],
        how="left",
        validate="many_to_one",
    )
    if assigned["net_6bps"].isna().any():
        raise OracleError("PLACEBO_PAYOFF_MISSING")

    state = reconstruct_state(aligned, state_id)
    signal = _state_join(signal, state, "signal_origin").rename(
        columns={"oracle_state": "signal_state"}
    )
    assigned = _state_join(assigned, state, "matched_placebo_origin").rename(
        columns={"oracle_state": "placebo_state"}
    )

    paired = assigned.merge(
        signal[
            [
                "signal_trade_id",
                "signal_origin",
                "signal_state",
                "signal_net_6bps",
            ]
        ],
        on=["signal_trade_id", "signal_origin"],
        how="inner",
        validate="many_to_one",
    )
    paired = paired[paired["placebo_state"] == paired["signal_state"]].copy()
    if paired.empty:
        raise OracleError("NO_COMPATIBLE_PLACEBOS")

    result = (
        paired.groupby(
            ["signal_trade_id", "signal_origin", "signal_state", "signal_net_6bps"],
            as_index=False,
        )
        .agg(
            compatible_placebo_n=("net_6bps", "size"),
            placebo_mean_net_6bps=("net_6bps", "mean"),
        )
        .sort_values("signal_trade_id", kind="mergesort")
        .reset_index(drop=True)
    )
    result["delta_net_6bps"] = (
        result["signal_net_6bps"].astype(float)
        - result["placebo_mean_net_6bps"].astype(float)
    )
    return result


def verify_primary_output(
    aligned: pd.DataFrame,
    assignments: pd.DataFrame,
    signal_paths: pd.DataFrame,
    placebo_payoffs: pd.DataFrame,
    primary_per_signal: pd.DataFrame,
    state_id: str,
) -> dict:
    oracle = reconstruct_per_signal(
        aligned, assignments, signal_paths, placebo_payoffs, state_id
    )
    _require(
        primary_per_signal,
        [
            "signal_trade_id",
            "signal_state",
            "signal_net_6bps",
            "compatible_placebo_n",
            "placebo_mean_net_6bps",
            "delta_net_6bps",
        ],
        "PRIMARY",
    )
    primary = primary_per_signal.copy()
    primary["signal_trade_id"] = primary["signal_trade_id"].astype(str)
    primary = primary.sort_values("signal_trade_id", kind="mergesort").reset_index(drop=True)

    merged = oracle.merge(
        primary[
            [
                "signal_trade_id",
                "signal_state",
                "signal_net_6bps",
                "compatible_placebo_n",
                "placebo_mean_net_6bps",
                "delta_net_6bps",
            ]
        ],
        on="signal_trade_id",
        how="outer",
        suffixes=("_oracle", "_primary"),
        indicator=True,
    )
    mismatches = []
    for _, row in merged.iterrows():
        trade_id = str(row.get("signal_trade_id"))
        if row["_merge"] != "both":
            mismatches.append({"trade_id": trade_id, "reason": str(row["_merge"])})
            continue
        if bool(row["signal_state_oracle"]) != bool(row["signal_state_primary"]):
            mismatches.append({"trade_id": trade_id, "reason": "STATE_MISMATCH"})
            continue
        if int(row["compatible_placebo_n_oracle"]) != int(
            row["compatible_placebo_n_primary"]
        ):
            mismatches.append({"trade_id": trade_id, "reason": "PLACEBO_N_MISMATCH"})
            continue
        for field in (
            "signal_net_6bps",
            "placebo_mean_net_6bps",
            "delta_net_6bps",
        ):
            left = float(row[f"{field}_oracle"])
            right = float(row[f"{field}_primary"])
            if not math.isclose(left, right, rel_tol=0.0, abs_tol=ORACLE_TOLERANCE):
                mismatches.append({"trade_id": trade_id, "reason": f"{field.upper()}_MISMATCH"})
                break

    return {
        "oracle": "MACD_FUTURES_PARTICIPATION_REGIME_V1_INDEPENDENT_ORACLE",
        "state_id": state_id,
        "oracle_rows": int(len(oracle)),
        "primary_rows": int(len(primary)),
        "mismatch_count": int(len(mismatches)),
        "mismatches_first_20": mismatches[:20],
        "verdict": "PASS" if not mismatches else "FAIL",
        "imports_primary_state_builder": False,
        "imports_primary_pairing_builder": False,
        "structural_edge_certified": False,
    }
