"""Strategy timeline aggregation helpers for dashboard analysis."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


_BUCKET_RULES = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
}


def bucket_rule(bucket_size: str) -> str:
    return _BUCKET_RULES.get(str(bucket_size or "5m").strip().lower(), "5min")


def floor_timestamp_to_bucket(ts: Any, bucket_size: str = "5m") -> pd.Timestamp | None:
    try:
        parsed = pd.to_datetime(ts, utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.floor(bucket_rule(bucket_size))


def _top_value(series: pd.Series, default: str = "NONE") -> str:
    vals = [str(v).strip() for v in series if str(v).strip()]
    if not vals:
        return default
    count = Counter(vals)
    return sorted(count.items(), key=lambda item: (-item[1], item[0]))[0][0]


def compute_strategy_timeline_metrics(df: pd.DataFrame, bucket_size: str = "5m", ts_col: str = "ts_sort") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "time_bucket",
                "strategy_family",
                "candidates",
                "high_execute",
                "executed",
                "demoted",
                "demoted_rate",
                "execution_rate",
                "top_blocker",
            ]
        )

    work = df.copy()
    if ts_col not in work.columns:
        return pd.DataFrame()

    work["time_bucket"] = pd.to_datetime(work[ts_col], utc=True, errors="coerce").dt.floor(bucket_rule(bucket_size))
    work = work[work["time_bucket"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work["strategy_family"] = work.get("strategy_family", "UNKNOWN").fillna("UNKNOWN").astype(str)
    work["permission_bucket"] = work.get("permission_bucket", "ADVISORY").fillna("ADVISORY").astype(str).str.upper()
    work["final_action"] = work.get("final_action", "ADVISORY_ONLY").fillna("ADVISORY_ONLY").astype(str).str.upper()
    work["final_blocker"] = work.get("final_blocker", "NONE").fillna("NONE").astype(str)

    work["_is_high_execute"] = work["permission_bucket"].eq("HIGH_EXECUTE")
    work["_is_executed"] = work["final_action"].eq("EXECUTE")
    work["_is_demoted"] = work["_is_high_execute"] & (~work["_is_executed"])

    grouped = (
        work.groupby(["time_bucket", "strategy_family"], dropna=False)
        .agg(
            candidates=("strategy_family", "size"),
            high_execute=("_is_high_execute", "sum"),
            executed=("_is_executed", "sum"),
            demoted=("_is_demoted", "sum"),
            top_blocker=("final_blocker", _top_value),
        )
        .reset_index()
    )

    grouped["demoted_rate"] = grouped["demoted"] / grouped["high_execute"].clip(lower=1)
    grouped["execution_rate"] = grouped["executed"] / grouped["candidates"].clip(lower=1)

    if "outcome" in work.columns:
        outcome_work = work.copy()
        outcome_work["outcome"] = outcome_work["outcome"].fillna("").astype(str).str.upper()
        outcome_work["_is_missed_winner"] = outcome_work["outcome"].eq("HIT") & (~outcome_work["_is_executed"])
        missed = (
            outcome_work.groupby(["time_bucket", "strategy_family"], dropna=False)
            .agg(missed_winners=("_is_missed_winner", "sum"))
            .reset_index()
        )
        grouped = grouped.merge(missed, on=["time_bucket", "strategy_family"], how="left")
        grouped["missed_winners"] = grouped["missed_winners"].fillna(0).astype(int)

    grouped = grouped.sort_values(["time_bucket", "strategy_family"], ascending=[True, True])
    return grouped.reset_index(drop=True)
