from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

COST_BPS = 6.0
STOP_FRACTION = 0.98
TIMEOUT_BARS = 18
IST = "Asia/Kolkata"


class DelayReplayBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class ReplayResult:
    origin_timestamp: pd.Timestamp
    entry_timestamp: pd.Timestamp
    entry_price: float
    exit_timestamp: pd.Timestamp
    exit_price: float
    exit_reason: str
    holding_bars: int
    gross_bps: float
    net_6bps: float


def _require(df: pd.DataFrame, cols: Iterable[str], label: str) -> None:
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise DelayReplayBlocked(f"{label}_SCHEMA_MISSING:{','.join(missing)}")


def _ist(series: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(series, errors="coerce")
    if timestamps.isna().any():
        raise DelayReplayBlocked("INVALID_TIMESTAMP")
    if timestamps.dt.tz is None:
        return timestamps.dt.tz_localize(IST)
    return timestamps.dt.tz_convert(IST)


def build_clock(aligned: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require(
        aligned,
        [
            "timestamp",
            "session_date",
            "spot_close",
            "futures_open",
            "futures_high",
            "futures_low",
            "futures_close",
        ],
        "ALIGNED",
    )
    frame = aligned.copy()
    frame["timestamp"] = _ist(frame["timestamp"])
    frame["session_date"] = frame["session_date"].astype(str)
    if "spot_present" in frame.columns:
        frame = frame[frame["spot_present"].astype(bool)].copy()
    frame = frame.sort_values(["session_date", "timestamp"], kind="stable")

    bars15 = (
        frame.set_index("timestamp")
        .groupby("session_date")
        .resample(
            "15min",
            origin="start_day",
            offset="9h15min",
            label="left",
            closed="left",
        )
        .agg(
            spot_close=("spot_close", "last"),
            futures_open=("futures_open", "first"),
            futures_high=("futures_high", "max"),
            futures_low=("futures_low", "min"),
            futures_close=("futures_close", "last"),
            minute_rows=("spot_close", "size"),
        )
        .reset_index()
    )
    bars15 = bars15.dropna(
        subset=[
            "spot_close",
            "futures_open",
            "futures_high",
            "futures_low",
            "futures_close",
        ]
    ).copy()
    bars15 = bars15.sort_values(["session_date", "timestamp"], kind="stable").reset_index(
        drop=True
    )
    bars15["bar_ordinal"] = bars15.groupby("session_date").cumcount()
    bars15["hour_group"] = bars15["bar_ordinal"] // 4

    group_size = bars15.groupby(["session_date", "hour_group"])["timestamp"].transform(
        "size"
    )
    completed = bars15[group_size == 4].copy()
    hourly = (
        completed.groupby(["session_date", "hour_group"], sort=True)
        .agg(
            timestamp=("timestamp", "first"),
            close=("spot_close", "last"),
            bars=("timestamp", "size"),
        )
        .reset_index()
    )
    fast = hourly["close"].ewm(span=12, adjust=False, min_periods=26).mean()
    slow = hourly["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    hourly["macd"] = fast - slow
    hourly["signal"] = hourly["macd"].ewm(
        span=5, adjust=False, min_periods=5
    ).mean()
    hourly["bull_cross"] = (hourly["macd"] > hourly["signal"]) & (
        hourly["macd"].shift(1) <= hourly["signal"].shift(1)
    )
    hourly["bear_cross"] = (hourly["macd"] < hourly["signal"]) & (
        hourly["macd"].shift(1) >= hourly["signal"].shift(1)
    )
    hourly["available_timestamp"] = hourly["timestamp"] + pd.Timedelta(minutes=60)
    return bars15, hourly


def _same_session_indices(bars15: pd.DataFrame, session: str) -> np.ndarray:
    return np.flatnonzero(bars15["session_date"].to_numpy() == session)


def replay_origin(
    bars15: pd.DataFrame,
    hourly: pd.DataFrame,
    origin: pd.Timestamp,
    delay_bars: int = 0,
) -> ReplayResult | None:
    origin = pd.Timestamp(origin)
    if origin.tzinfo is None:
        origin = origin.tz_localize(IST)
    else:
        origin = origin.tz_convert(IST)

    decision_available = origin + pd.Timedelta(minutes=60)
    session = str(origin.date())
    eligible = np.flatnonzero(
        (
            (bars15["session_date"] == session)
            & (bars15["timestamp"] > decision_available)
        ).to_numpy()
    )
    if len(eligible) <= delay_bars:
        return None

    entry_pos = int(eligible[delay_bars])
    entry = bars15.iloc[entry_pos]
    entry_price = float(entry["futures_open"])
    stop_price = entry_price * STOP_FRACTION

    bearish = hourly[
        hourly["bear_cross"] & (hourly["available_timestamp"] >= entry["timestamp"])
    ].copy()
    bearish_exit_positions: set[int] = set()
    for _, row in bearish.iterrows():
        if str(row["session_date"]) != session:
            continue
        positions = np.flatnonzero(
            (
                (bars15["session_date"] == session)
                & (bars15["timestamp"] > pd.Timestamp(row["available_timestamp"]))
            ).to_numpy()
        )
        if len(positions):
            bearish_exit_positions.add(int(positions[0]))

    session_positions = _same_session_indices(bars15, session)
    end_limit = min(entry_pos + TIMEOUT_BARS - 1, int(session_positions[-1]))
    if end_limit - entry_pos + 1 < TIMEOUT_BARS:
        return None

    for position in range(entry_pos, end_limit + 1):
        row = bars15.iloc[position]
        if float(row["futures_low"]) <= stop_price:
            exit_price = stop_price
            exit_reason = "STOP"
            exit_timestamp = pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=15)
            holding_bars = position - entry_pos + 1
            break
        if position in bearish_exit_positions:
            exit_price = float(row["futures_open"])
            exit_reason = "BEARISH_CROSS"
            exit_timestamp = pd.Timestamp(row["timestamp"])
            holding_bars = position - entry_pos
            break
        if position == end_limit:
            exit_price = float(row["futures_close"])
            exit_reason = "TIMEOUT"
            exit_timestamp = pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=15)
            holding_bars = TIMEOUT_BARS
            break

    gross_bps = (exit_price / entry_price - 1.0) * 1e4
    return ReplayResult(
        origin_timestamp=origin,
        entry_timestamp=pd.Timestamp(entry["timestamp"]),
        entry_price=entry_price,
        exit_timestamp=exit_timestamp,
        exit_price=exit_price,
        exit_reason=exit_reason,
        holding_bars=int(holding_bars),
        gross_bps=float(gross_bps),
        net_6bps=float(gross_bps - COST_BPS),
    )


def _normalize_reason(value: object) -> str:
    text = str(value).upper().replace("-", "_").replace(" ", "_")
    if "BEAR" in text:
        return "BEARISH_CROSS"
    if "STOP" in text:
        return "STOP"
    if "TIME" in text:
        return "TIMEOUT"
    return text


def baseline_parity(
    signal_origins: pd.DataFrame,
    signal_paths: pd.DataFrame,
    bars15: pd.DataFrame,
    hourly: pd.DataFrame,
    tol_bps: float = 1e-6,
) -> tuple[pd.DataFrame, dict]:
    _require(signal_origins, ["signal_trade_id", "signal_origin"], "ORIGINS")
    _require(
        signal_paths,
        [
            "trade_id",
            "entry_timestamp",
            "exit_timestamp",
            "exit_reason",
            "holding_bars",
            "gross_bps",
            "net_6bps",
        ],
        "SIGNAL_PATHS",
    )
    origins = signal_origins.copy()
    paths = signal_paths.copy()
    origins["signal_trade_id"] = origins["signal_trade_id"].astype(str)
    paths["trade_id"] = paths["trade_id"].astype(str)
    origins["signal_origin"] = _ist(origins["signal_origin"])
    paths["entry_timestamp"] = _ist(paths["entry_timestamp"])
    paths["exit_timestamp"] = _ist(paths["exit_timestamp"])
    merged = origins.merge(
        paths,
        left_on="signal_trade_id",
        right_on="trade_id",
        how="inner",
        validate="one_to_one",
    )

    rows = []
    for _, row in merged.iterrows():
        replay = replay_origin(bars15, hourly, row["signal_origin"], 0)
        if replay is None:
            rows.append(
                {"signal_trade_id": row["signal_trade_id"], "mismatch": "REPLAY_NONE"}
            )
            continue
        mismatches = []
        if replay.entry_timestamp != row["entry_timestamp"]:
            mismatches.append("entry_timestamp")
        if replay.exit_timestamp != row["exit_timestamp"]:
            mismatches.append("exit_timestamp")
        if _normalize_reason(replay.exit_reason) != _normalize_reason(row["exit_reason"]):
            mismatches.append("exit_reason")
        if int(replay.holding_bars) != int(row["holding_bars"]):
            mismatches.append("holding_bars")
        if abs(replay.gross_bps - float(row["gross_bps"])) > tol_bps:
            mismatches.append("gross_bps")
        if abs(replay.net_6bps - float(row["net_6bps"])) > tol_bps:
            mismatches.append("net_6bps")
        rows.append(
            {
                "signal_trade_id": row["signal_trade_id"],
                "mismatch": "|".join(mismatches),
                "replay_gross_bps": replay.gross_bps,
                "canonical_gross_bps": float(row["gross_bps"]),
            }
        )

    audit = pd.DataFrame(rows)
    mismatch_count = int((audit["mismatch"] != "").sum())
    return audit, {
        "signal_count": int(len(merged)),
        "mismatch_count": mismatch_count,
        "exact_parity": bool(len(merged) == 148 and mismatch_count == 0),
    }


def generate_delayed_interactions(
    *,
    aligned: pd.DataFrame,
    assignments: pd.DataFrame,
    signal_paths: pd.DataFrame,
    state: pd.DataFrame,
    delays: tuple[int, ...] = (1, 2),
) -> tuple[dict[int, dict[str, pd.DataFrame]], pd.DataFrame, dict]:
    """Generate H1/H2 delayed ledgers only after exact delay-0 parity."""
    from research.macd_futures_participation_regime_v1.analysis import (
        prepare_interaction,
    )

    _require(
        assignments,
        [
            "replication_id",
            "signal_trade_id",
            "signal_origin",
            "matched_placebo_origin",
        ],
        "ASSIGNMENTS",
    )
    assignment_frame = assignments.copy()
    assignment_frame["signal_trade_id"] = assignment_frame["signal_trade_id"].astype(str)
    assignment_frame["signal_origin"] = _ist(assignment_frame["signal_origin"])
    assignment_frame["matched_placebo_origin"] = _ist(
        assignment_frame["matched_placebo_origin"]
    )
    origins = assignment_frame[["signal_trade_id", "signal_origin"]].drop_duplicates()
    if origins.duplicated("signal_trade_id").any():
        raise DelayReplayBlocked("SIGNAL_TRADE_HAS_MULTIPLE_ORIGINS")

    bars15, hourly = build_clock(aligned)
    audit, parity = baseline_parity(origins, signal_paths, bars15, hourly)
    if not parity["exact_parity"]:
        raise DelayReplayBlocked(
            f"BASELINE_CANONICAL_PARITY_FAIL:{parity['mismatch_count']}"
        )

    output: dict[int, dict[str, pd.DataFrame]] = {}
    unique_placebos = pd.Series(
        assignment_frame["matched_placebo_origin"].unique()
    ).sort_values()
    for delay in delays:
        signal_rows = []
        for _, row in origins.iterrows():
            replay = replay_origin(bars15, hourly, row["signal_origin"], delay)
            if replay is None:
                raise DelayReplayBlocked(
                    f"DELAY_{delay}_SIGNAL_NOT_REPLAYABLE:{row['signal_trade_id']}"
                )
            signal_rows.append(
                {
                    "trade_id": row["signal_trade_id"],
                    "signal_trade_id": row["signal_trade_id"],
                    "signal_origin": row["signal_origin"],
                    "entry_timestamp": replay.entry_timestamp,
                    "net_6bps": replay.net_6bps,
                    "gross_bps": replay.gross_bps,
                    "exit_timestamp": replay.exit_timestamp,
                    "exit_reason": replay.exit_reason,
                    "holding_bars": replay.holding_bars,
                }
            )
        delayed_signals = pd.DataFrame(signal_rows)

        placebo_map = {}
        for origin in unique_placebos:
            replay = replay_origin(bars15, hourly, origin, delay)
            if replay is not None:
                placebo_map[pd.Timestamp(origin)] = replay.net_6bps
        delayed_assigned = assignment_frame.copy()
        delayed_assigned["net_6bps"] = delayed_assigned["matched_placebo_origin"].map(
            placebo_map
        )
        delayed_assigned = delayed_assigned[
            delayed_assigned["net_6bps"].notna()
        ].copy()
        if delayed_assigned.empty:
            raise DelayReplayBlocked(f"DELAY_{delay}_NO_REPLAYABLE_PLACEBOS")

        h1 = prepare_interaction(delayed_signals, delayed_assigned, state, "h1_active")
        h2 = prepare_interaction(delayed_signals, delayed_assigned, state, "h2_active")
        expected_ids = set(origins["signal_trade_id"])
        for label, frame in (("H1", h1), ("H2", h2)):
            observed_ids = set(frame["signal_trade_id"].astype(str))
            if observed_ids != expected_ids:
                raise DelayReplayBlocked(
                    f"DELAY_{delay}_{label}_SIGNAL_ID_SET_MISMATCH:"
                    f"missing={len(expected_ids-observed_ids)}:"
                    f"extra={len(observed_ids-expected_ids)}"
                )
        output[int(delay)] = {
            "h1": h1,
            "h2": h2,
            "signals": delayed_signals,
            "assigned": delayed_assigned,
        }
    return output, audit, parity
