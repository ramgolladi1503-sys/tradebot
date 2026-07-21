from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import BarrierOutcome


def _session_end_positions(bars: pd.DataFrame) -> np.ndarray:
    size = len(bars)
    if "session_date" not in bars.columns:
        return np.full(size, size - 1, dtype=int)
    sessions = bars["session_date"].astype(str).to_numpy()
    ends = np.empty(size, dtype=int)
    end = size - 1
    for index in range(size - 1, -1, -1):
        if index == size - 1 or sessions[index] != sessions[index + 1]:
            end = index
        ends[index] = end
    return ends


def compute_triple_barrier_labels(
    bars: pd.DataFrame,
    atr: pd.Series,
    *,
    horizon_bars: int,
    target_atr: float,
    stop_atr: float,
    side: str = "LONG",
) -> pd.DataFrame:
    """Create same-session path labels from future completed bars.

    The full configured horizon must exist inside the same session. Rows too near
    session end are explicitly unavailable, preventing next-session gap leakage.
    Same-bar target/stop collisions are explicit and valued conservatively as a stop.
    """

    normalized_side = side.upper()
    if normalized_side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")

    close = bars["close"].to_numpy(dtype=float)
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    atr_values = atr.to_numpy(dtype=float)
    session_ends = _session_end_positions(bars)
    size = len(bars)

    outcomes: list[str] = [BarrierOutcome.UNAVAILABLE.value] * size
    statuses: list[str] = ["INSUFFICIENT_HISTORY_OR_FUTURE"] * size
    bars_to_event = np.full(size, np.nan)
    mfe_atr = np.full(size, np.nan)
    mae_atr = np.full(size, np.nan)
    future_close_return_atr = np.full(size, np.nan)
    label_return_r = np.full(size, np.nan)

    for index in range(size):
        scale = atr_values[index]
        required_last = index + horizon_bars
        if not np.isfinite(scale) or scale <= 0:
            statuses[index] = "ATR_UNAVAILABLE"
            continue
        if required_last >= size or required_last > session_ends[index]:
            statuses[index] = "SESSION_ENDED_BEFORE_HORIZON"
            continue

        last = required_last
        entry = close[index]
        if normalized_side == "LONG":
            target = entry + target_atr * scale
            stop = entry - stop_atr * scale
        else:
            target = entry - target_atr * scale
            stop = entry + stop_atr * scale

        future_high = high[index + 1 : last + 1]
        future_low = low[index + 1 : last + 1]
        future_close = close[last]

        if normalized_side == "LONG":
            mfe_atr[index] = float((np.nanmax(future_high) - entry) / scale)
            mae_atr[index] = float((np.nanmin(future_low) - entry) / scale)
            future_close_return_atr[index] = float((future_close - entry) / scale)
        else:
            mfe_atr[index] = float((entry - np.nanmin(future_low)) / scale)
            mae_atr[index] = float((entry - np.nanmax(future_high)) / scale)
            future_close_return_atr[index] = float((entry - future_close) / scale)

        outcome = BarrierOutcome.NEITHER
        event_bar: int | None = None
        for offset, (bar_high, bar_low) in enumerate(zip(future_high, future_low), start=1):
            if normalized_side == "LONG":
                hit_target = bar_high >= target
                hit_stop = bar_low <= stop
            else:
                hit_target = bar_low <= target
                hit_stop = bar_high >= stop
            if hit_target and hit_stop:
                outcome = BarrierOutcome.AMBIGUOUS_SAME_BAR
                event_bar = offset
                break
            if hit_target:
                outcome = BarrierOutcome.TARGET_FIRST
                event_bar = offset
                break
            if hit_stop:
                outcome = BarrierOutcome.STOP_FIRST
                event_bar = offset
                break

        outcomes[index] = outcome.value
        statuses[index] = "MEASURED"
        if event_bar is not None:
            bars_to_event[index] = float(event_bar)

        if outcome is BarrierOutcome.TARGET_FIRST:
            label_return_r[index] = target_atr
        elif outcome in {BarrierOutcome.STOP_FIRST, BarrierOutcome.AMBIGUOUS_SAME_BAR}:
            label_return_r[index] = -stop_atr
        else:
            label_return_r[index] = float(
                np.clip(future_close_return_atr[index], -stop_atr, target_atr)
            )

    return pd.DataFrame(
        {
            "label_side": normalized_side,
            "label_status": statuses,
            "barrier_outcome": outcomes,
            "bars_to_event": bars_to_event,
            "mfe_atr": mfe_atr,
            "mae_atr": mae_atr,
            "future_close_return_atr": future_close_return_atr,
            "label_return_r": label_return_r,
        },
        index=bars.index,
    )


def attach_option_outcome_availability(
    dataset: pd.DataFrame,
    option_quotes: pd.DataFrame | None,
) -> pd.DataFrame:
    """Declare option evidence availability without fabricating missing fields."""

    output = dataset.copy()
    required = {"timestamp", "bid", "ask", "instrument"}
    if option_quotes is None or not required.issubset(option_quotes.columns):
        output["option_data_availability"] = "UNAVAILABLE"
        output["option_data_reason"] = "historical_bid_ask_path_not_supplied"
        return output

    quotes = option_quotes.copy()
    quotes["timestamp"] = pd.to_datetime(quotes["timestamp"], utc=True, errors="raise")
    quotes = quotes.sort_values("timestamp")
    timestamps = set(quotes["timestamp"].tolist())
    present = output["decision_timestamp"].isin(timestamps)
    output["option_data_availability"] = np.where(present, "PARTIAL", "UNAVAILABLE")
    output["option_data_reason"] = np.where(
        present,
        "decision_quote_present_but_full_selection_and_future_path_not_evaluated",
        "decision_quote_missing",
    )
    return output
