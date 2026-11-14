from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import CLAIM_BOUNDARY_UNDERLYING, ForwardMoveLabelConfig

_REQUIRED = {"open", "high", "low", "close"}


def _session_end_positions(bars: pd.DataFrame) -> np.ndarray:
    size = len(bars)
    if "session_date" not in bars.columns:
        return np.full(size, size - 1, dtype=int)
    sessions = bars["session_date"].astype(str).to_numpy()
    ends = np.empty(size, dtype=int)
    current_end = size - 1
    for index in range(size - 1, -1, -1):
        if index == size - 1 or sessions[index] != sessions[index + 1]:
            current_end = index
        ends[index] = current_end
    return ends


def _decision_timestamp(frame: pd.DataFrame) -> pd.Series:
    for column in ("bar_end_timestamp", "decision_timestamp", "timestamp"):
        if column in frame.columns:
            return pd.to_datetime(frame[column], utc=True, errors="raise")
    return pd.Series(pd.RangeIndex(len(frame)), index=frame.index, dtype="object")


def compute_forward_move_labels(
    bars: pd.DataFrame,
    *,
    config: ForwardMoveLabelConfig | None = None,
) -> pd.DataFrame:
    """Create same-session forward NIFTY movement labels from the next legal bar open.

    These columns are labels only. They must never be admitted to a feature matrix.
    For a decision made after bar ``i`` closes, entry is bar ``i+1`` open. A
    ``15`` minute horizon on 1-minute bars terminates at bar ``i+15`` close.
    """

    config = config or ForwardMoveLabelConfig()
    missing = _REQUIRED.difference(bars.columns)
    if missing:
        raise ValueError(f"missing required OHLC columns: {sorted(missing)}")

    frame = bars.reset_index(drop=True).copy()
    for column in _REQUIRED:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    values = frame[list(_REQUIRED)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("OHLC values must be finite")

    session_ends = _session_end_positions(frame)
    decision_ts = _decision_timestamp(frame)
    output = pd.DataFrame(index=frame.index)
    output["decision_timestamp"] = decision_ts
    output["claim_boundary"] = CLAIM_BOUNDARY_UNDERLYING

    open_ = frame["open"].to_numpy(dtype=float)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    size = len(frame)

    for horizon_minutes in config.horizons_minutes:
        horizon_bars = horizon_minutes // config.bar_interval_minutes
        prefix = f"fwd_{horizon_minutes}m"
        status = np.full(size, "UNAVAILABLE", dtype=object)
        entry_price = np.full(size, np.nan)
        terminal_close = np.full(size, np.nan)
        signed_move = np.full(size, np.nan)
        abs_move = np.full(size, np.nan)
        move_bps = np.full(size, np.nan)
        max_up = np.full(size, np.nan)
        max_down = np.full(size, np.nan)
        direction = np.full(size, "UNAVAILABLE", dtype=object)

        for index in range(size):
            entry_index = index + 1
            terminal_index = index + horizon_bars
            if entry_index >= size or terminal_index >= size:
                status[index] = "INSUFFICIENT_FUTURE"
                continue
            if terminal_index > session_ends[index]:
                status[index] = "SESSION_ENDED_BEFORE_HORIZON"
                continue

            entry = open_[entry_index]
            terminal = close[terminal_index]
            if not np.isfinite(entry) or entry <= 0 or not np.isfinite(terminal):
                status[index] = "INVALID_PRICE"
                continue

            path_high = high[entry_index : terminal_index + 1]
            path_low = low[entry_index : terminal_index + 1]
            move = terminal - entry

            status[index] = "MEASURED"
            entry_price[index] = entry
            terminal_close[index] = terminal
            signed_move[index] = move
            abs_move[index] = abs(move)
            move_bps[index] = (move / entry) * 10_000.0
            max_up[index] = float(np.max(path_high) - entry)
            max_down[index] = float(entry - np.min(path_low))
            direction[index] = "UP" if move > 0 else "DOWN" if move < 0 else "FLAT"

        output[f"{prefix}_status"] = status
        output[f"{prefix}_entry_price"] = entry_price
        output[f"{prefix}_terminal_close"] = terminal_close
        output[f"{prefix}_signed_points"] = signed_move
        output[f"{prefix}_abs_points"] = abs_move
        output[f"{prefix}_signed_bps"] = move_bps
        output[f"{prefix}_max_up_points"] = max_up
        output[f"{prefix}_max_down_points"] = max_down
        output[f"{prefix}_direction"] = direction

        for threshold in config.move_thresholds_points:
            label = str(int(threshold)) if float(threshold).is_integer() else str(threshold).replace(".", "p")
            measured = status == "MEASURED"
            output[f"{prefix}_terminal_up_ge_{label}"] = measured & (signed_move >= threshold)
            output[f"{prefix}_terminal_down_ge_{label}"] = measured & (signed_move <= -threshold)
            output[f"{prefix}_excursion_up_ge_{label}"] = measured & (max_up >= threshold)
            output[f"{prefix}_excursion_down_ge_{label}"] = measured & (max_down >= threshold)

    return output
