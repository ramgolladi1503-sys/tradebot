from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd


class HypothesisDevelopmentError(ValueError):
    """Raised when preregistered development evidence is invalid."""


_REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")


def _as_ist(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="raise")
    timezone = getattr(parsed.dt, "tz", None)
    if timezone is None:
        return parsed.dt.tz_localize("Asia/Kolkata")
    return parsed.dt.tz_convert("Asia/Kolkata")


def _time_value(frame: pd.DataFrame, hhmm: str, column: str) -> float | None:
    hour, minute = (int(part) for part in hhmm.split(":"))
    rows = frame[
        (frame["_ts"].dt.hour == hour)
        & (frame["_ts"].dt.minute == minute)
    ]
    if len(rows) != 1:
        return None
    value = float(rows.iloc[0][column])
    return value if math.isfinite(value) and value > 0 else None


def build_session_features(bars: pd.DataFrame) -> pd.DataFrame:
    missing = [name for name in _REQUIRED_COLUMNS if name not in bars.columns]
    if missing:
        raise HypothesisDevelopmentError(
            f"bars missing required columns: {missing}"
        )
    frame = bars.loc[:, list(_REQUIRED_COLUMNS)].copy()
    frame["_ts"] = _as_ist(frame["timestamp"])
    if frame["_ts"].duplicated().any():
        raise HypothesisDevelopmentError("duplicate timestamps are forbidden")
    for name in ("open", "high", "low", "close"):
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if not np.isfinite(frame[name].to_numpy(dtype=float)).all():
            raise HypothesisDevelopmentError(
                f"non-finite {name} values are forbidden"
            )
        if (frame[name] <= 0).any():
            raise HypothesisDevelopmentError(
                f"non-positive {name} values are forbidden"
            )
    invalid_geometry = (
        frame["high"] < frame[["open", "close", "low"]].max(axis=1)
    ) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    if invalid_geometry.any():
        raise HypothesisDevelopmentError("invalid OHLC geometry")
    frame = frame.sort_values("_ts", kind="mergesort").reset_index(drop=True)
    frame["session_date"] = frame["_ts"].dt.date.astype(str)

    daily = (
        frame.groupby("session_date", sort=True)
        .agg(
            session_high=("high", "max"),
            session_low=("low", "min"),
            session_close=("close", "last"),
        )
        .reset_index()
    )
    daily["previous_close"] = daily["session_close"].shift(1)
    true_range = pd.concat(
        [
            daily["session_high"] - daily["session_low"],
            (daily["session_high"] - daily["previous_close"]).abs(),
            (daily["session_low"] - daily["previous_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["prior_atr_20"] = true_range.rolling(
        20, min_periods=10
    ).mean().shift(1)
    context = daily.set_index("session_date")

    rows: list[dict[str, Any]] = []
    for session_date, session in frame.groupby("session_date", sort=True):
        daily_row = context.loc[session_date]
        previous_close = (
            float(daily_row["previous_close"])
            if pd.notna(daily_row["previous_close"])
            else math.nan
        )
        prior_atr = (
            float(daily_row["prior_atr_20"])
            if pd.notna(daily_row["prior_atr_20"])
            else math.nan
        )
        if (
            not math.isfinite(previous_close)
            or not math.isfinite(prior_atr)
            or prior_atr <= 0
        ):
            continue
        session = session.sort_values("_ts", kind="mergesort")
        opening = session[
            (session["_ts"].dt.hour == 9)
            & session["_ts"].dt.minute.between(15, 44)
        ]
        extension = session[
            (session["_ts"].dt.hour == 9)
            & session["_ts"].dt.minute.between(15, 29)
        ]
        if len(opening) < 25 or len(extension) < 10:
            continue

        session_open = float(opening.iloc[0]["open"])
        opening_close = float(opening.iloc[-1]["close"])
        opening_direction = int(np.sign(opening_close - session_open))
        path = np.concatenate(
            ([session_open], opening["close"].to_numpy(dtype=float))
        )
        path_length = float(np.abs(np.diff(path)).sum())
        efficiency = (
            abs(opening_close - session_open) / path_length
            if path_length > 0
            else 0.0
        )
        opening_move_atr = abs(opening_close - session_open) / prior_atr

        him_entry = _time_value(session, "14:55", "open")
        him_exit = _time_value(session, "15:25", "open")
        him_outcome = math.nan
        if opening_direction and him_entry and him_exit:
            him_outcome = (
                opening_direction
                * (him_exit - him_entry)
                / him_entry
                * 10000.0
            )

        gap = session_open - previous_close
        gap_direction = int(np.sign(gap))
        gap_atr = abs(gap) / prior_atr
        if gap_direction > 0:
            extension_atr = (
                float(extension["high"].max()) - session_open
            ) / prior_atr
        elif gap_direction < 0:
            extension_atr = (
                session_open - float(extension["low"].min())
            ) / prior_atr
        else:
            extension_atr = 0.0
        failure_close = float(opening.iloc[-1]["close"])
        reclaim_failure = bool(
            (gap_direction > 0 and failure_close < session_open)
            or (gap_direction < 0 and failure_close > session_open)
        )
        eogf_entry = _time_value(session, "09:45", "open")
        eogf_exit = _time_value(session, "10:15", "open")
        eogf_outcome = math.nan
        if gap_direction and reclaim_failure and eogf_entry and eogf_exit:
            eogf_outcome = (
                -gap_direction
                * (eogf_exit - eogf_entry)
                / eogf_entry
                * 10000.0
            )

        rows.append(
            {
                "session_date": session_date,
                "opening_direction": opening_direction,
                "opening_move_prior_atr": opening_move_atr,
                "directional_efficiency": efficiency,
                "him_outcome_bps": him_outcome,
                "gap_direction": gap_direction,
                "absolute_gap_prior_atr": gap_atr,
                "extension_prior_atr": extension_atr,
                "opening_reclaim_failure": reclaim_failure,
                "eogf_outcome_bps": eogf_outcome,
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise HypothesisDevelopmentError("no eligible completed sessions")
    return result.sort_values(
        "session_date", kind="mergesort"
    ).reset_index(drop=True)


def variant_mask(
    features: pd.DataFrame,
    hypothesis_id: str,
    variant: Mapping[str, Any],
) -> pd.Series:
    if hypothesis_id == "HIM_30":
        return (
            features["opening_direction"].ne(0)
            & features["opening_move_prior_atr"].ge(
                float(variant["opening_move_prior_atr_min"])
            )
            & features["directional_efficiency"].ge(
                float(variant["directional_efficiency_min"])
            )
            & features["him_outcome_bps"].notna()
        )
    if hypothesis_id == "EOGF_30":
        return (
            features["gap_direction"].ne(0)
            & features["opening_reclaim_failure"].eq(True)
            & features["absolute_gap_prior_atr"].ge(
                float(variant["absolute_gap_prior_atr_min"])
            )
            & features["extension_prior_atr"].ge(
                float(variant["extension_prior_atr_min"])
            )
            & features["eogf_outcome_bps"].notna()
        )
    raise HypothesisDevelopmentError(
        f"unsupported hypothesis: {hypothesis_id}"
    )


def outcome_column(hypothesis_id: str) -> str:
    if hypothesis_id == "HIM_30":
        return "him_outcome_bps"
    if hypothesis_id == "EOGF_30":
        return "eogf_outcome_bps"
    raise HypothesisDevelopmentError(
        f"unsupported hypothesis: {hypothesis_id}"
    )
