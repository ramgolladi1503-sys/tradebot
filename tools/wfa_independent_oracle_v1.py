"""Small, calculation-bearing WFA oracle independent of TradeBot producers.

The oracle consumes primitive event rows.  It deliberately does not import any
TradeBot WFA, backtest, signal, or aggregation implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Iterable, Mapping

import pandas as pd


@dataclass(frozen=True)
class OracleFold:
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_rows: int
    test_rows: int
    raw_overlap_rows: int
    overlap_rows: int
    purged_train_rows: int
    required_gap: pd.Timedelta
    actual_gap: pd.Timedelta


def _ts(value: Any) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        return result.tz_localize("Asia/Kolkata")
    return result.tz_convert("Asia/Kolkata")


def primitive_frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows)).copy()
    if "timestamp" not in frame:
        raise ValueError("timestamp_required")
    frame["timestamp"] = frame["timestamp"].map(_ts)
    if frame["timestamp"].duplicated().any():
        raise ValueError("duplicate_timestamp")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("non_monotonic_timestamp")
    return frame


def classify_data_quality(
    frame: pd.DataFrame, *, required_columns: Iterable[str]
) -> dict[str, Any]:
    """Classify primitive input defects without coercing unknown values."""
    required = list(required_columns)
    missing_columns = sorted(set(required).difference(frame.columns))
    nan_columns = sorted(
        column for column in required if column in frame and frame[column].isna().any()
    )
    off_session_rows = 0
    if "timestamp" in frame:
        timestamps = frame["timestamp"].map(_ts)
        off_session_rows = int(
            ((timestamps.dt.time < pd.Timestamp("09:15").time()) |
             (timestamps.dt.time > pd.Timestamp("15:30").time())).sum()
        )
    return {
        "missing_columns": missing_columns,
        "nan_columns": nan_columns,
        "off_session_rows": off_session_rows,
        "status": "BLOCK" if missing_columns or nan_columns else "CLASSIFIED",
    }


def build_folds(
    frame: pd.DataFrame,
    *,
    train_size: int,
    test_size: int,
    label_horizon: pd.Timedelta = pd.Timedelta(0),
    mode: str = "rolling",
) -> list[OracleFold]:
    if train_size <= 0 or test_size <= 0:
        raise ValueError("fold_sizes_must_be_positive")
    if mode not in {"rolling", "anchored"}:
        raise ValueError("unsupported_fold_mode")
    timestamps = frame["timestamp"]
    folds: list[OracleFold] = []
    start = 0
    fold_id = 1
    while start + train_size + test_size <= len(frame):
        train = frame.iloc[start : start + train_size]
        test = frame.iloc[start + train_size : start + train_size + test_size]
        train_end = train["timestamp"].iloc[-1]
        test_start = test["timestamp"].iloc[0]
        actual_gap = test_start - train_end
        overlap_mask = train["timestamp"] + label_horizon >= test_start
        raw_overlap = int(overlap_mask.sum())
        folds.append(
            OracleFold(
                fold_id=fold_id,
                train_start=timestamps.iloc[start],
                train_end=train_end,
                test_start=test_start,
                test_end=test["timestamp"].iloc[-1],
                train_rows=len(train),
                test_rows=len(test),
                raw_overlap_rows=raw_overlap,
                overlap_rows=0,
                purged_train_rows=len(train) - raw_overlap,
                required_gap=label_horizon,
                actual_gap=actual_gap,
            )
        )
        if mode == "rolling":
            start += test_size
        else:
            # Keep the training origin fixed while expanding its endpoint.
            train_size += test_size
        fold_id += 1
    return folds


def purged_training_indices(
    frame: pd.DataFrame, fold: OracleFold, *, label_horizon: pd.Timedelta
) -> list[int]:
    """Return training positions whose label window ends before test starts."""
    train_mask = (frame["timestamp"] >= fold.train_start) & (
        frame["timestamp"] <= fold.train_end
    )
    label_end = frame["timestamp"] + label_horizon
    return [
        int(position)
        for position in frame.index[train_mask & (label_end < fold.test_start)]
    ]


def assert_causal_feature(
    frame: pd.DataFrame, *, feature: str, cutoff: str = "timestamp"
) -> None:
    if feature not in frame or cutoff not in frame:
        raise ValueError("feature_and_cutoff_required")
    if frame[feature].isna().any():
        raise ValueError("feature_nan")
    if "feature_source_timestamp" in frame:
        source = frame["feature_source_timestamp"].map(_ts)
        allowed = frame[cutoff].map(_ts)
        if (source > allowed).any():
            raise ValueError("future_feature_leakage")


def assert_train_only_scaler(*, fit_end: Any, test_start: Any) -> None:
    if _ts(fit_end) >= _ts(test_start):
        raise ValueError("test_fitted_scaler")


def assert_parameter_freeze(
    *, selection_end: Any, freeze_time: Any, test_start: Any
) -> None:
    selection = _ts(selection_end)
    freeze = _ts(freeze_time)
    test = _ts(test_start)
    if selection >= test:
        raise ValueError("test_selected_parameter")
    if freeze > test:
        raise ValueError("parameter_freeze_after_test_start")


def deterministic_effect_fixture(
    *, n: int = 20, effect: float = 1.0, decay_at: int | None = None
) -> pd.DataFrame:
    """Primitive causal next-row outcome fixture with an analytic answer."""
    if n < 4:
        raise ValueError("fixture_too_small")
    values = [effect if decay_at is None or i < decay_at else 0.0 for i in range(n)]
    return pd.DataFrame({"signal": [1.0] * n, "future_return": values})


def session_isolated_events(
    events: Iterable[Mapping[str, Any]], *, session_col: str = "session"
) -> pd.DataFrame:
    frame = pd.DataFrame(list(events)).copy()
    required = {"entry_timestamp", "exit_timestamp", session_col, "gross_bps"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing_event_fields:{','.join(sorted(missing))}")
    frame["entry_timestamp"] = frame["entry_timestamp"].map(_ts)
    frame["exit_timestamp"] = frame["exit_timestamp"].map(_ts)
    if (frame["exit_timestamp"] < frame["entry_timestamp"]).any():
        raise ValueError("exit_before_entry")
    entry_session = frame["entry_timestamp"].dt.date
    exit_session = frame["exit_timestamp"].dt.date
    if (entry_session != exit_session).any():
        raise ValueError("cross_session_event")
    return frame


def net_bps(gross_bps: float, *, entry_cost_bps: float, exit_cost_bps: float) -> float:
    return float(gross_bps) - float(entry_cost_bps) - float(exit_cost_bps)


def simulate_same_session_path(
    candles: pd.DataFrame,
    *,
    signal_index: int,
    side: str,
    entry_price: float,
    target: float,
    stop_loss: float,
    horizon: int,
    slippage_bps: float,
    spread_bps: float,
    quantity: int = 1,
    lot_size: int = 1,
) -> dict[str, Any]:
    """Independent fixed-target/stop path and round-trip cost calculation."""
    if signal_index < 0 or signal_index >= len(candles) or horizon <= 0:
        raise ValueError("invalid_path_inputs")
    if not isinstance(candles.index, pd.DatetimeIndex):
        raise ValueError("path_requires_datetime_index")
    day = candles.index[signal_index].date()
    future = candles.iloc[signal_index + 1 : signal_index + 1 + horizon]
    future = future[future.index.date == day]
    if future.empty:
        raise ValueError("no_same_session_future_bars")
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("unsupported_side")
    cost_bps = float(slippage_bps) + float(spread_bps)
    entry_fill = float(entry_price) * (1 + cost_bps / 10000.0 if side == "BUY" else 1 - cost_bps / 10000.0)
    exit_price = float(future.iloc[-1]["close"])
    outcome = "TIMEOUT"
    ambiguous = False
    for _, bar in future.iterrows():
        high, low = float(bar["high"]), float(bar["low"])
        if side == "BUY":
            target_hit, stop_hit = high >= target, low <= stop_loss
        else:
            target_hit, stop_hit = low <= target, high >= stop_loss
        if target_hit and stop_hit:
            outcome, exit_price, ambiguous = "STOP", float(stop_loss), True
            break
        if stop_hit:
            outcome, exit_price = "STOP", float(stop_loss)
            break
        if target_hit:
            outcome, exit_price = "TARGET", float(target)
            break
    exit_fill = exit_price * (1 - cost_bps / 10000.0 if side == "BUY" else 1 + cost_bps / 10000.0)
    pnl = (exit_fill - entry_fill if side == "BUY" else entry_fill - exit_fill) * quantity * lot_size
    return {"outcome": outcome, "entry_price": entry_fill, "exit_price": exit_fill, "pl": float(pnl), "ambiguous": ambiguous}


def assert_cost_accounting(
    *, gross_bps: float, observed_net_bps: float, entry_cost_bps: float, exit_cost_bps: float
) -> None:
    expected = net_bps(
        gross_bps, entry_cost_bps=entry_cost_bps, exit_cost_bps=exit_cost_bps
    )
    if float(observed_net_bps) != expected:
        raise ValueError("cost_accounting_mismatch")


def aggregate(values: Iterable[float], sessions: Iterable[str]) -> dict[str, float]:
    value_list = [float(v) for v in values]
    session_list = list(sessions)
    if len(value_list) != len(session_list):
        raise ValueError("aggregation_length_mismatch")
    if not value_list:
        raise ValueError("empty_aggregation")
    by_session: dict[str, list[float]] = {}
    for session, value in zip(session_list, value_list):
        by_session.setdefault(str(session), []).append(value)
    session_means = [sum(v) / len(v) for v in by_session.values()]
    return {
        "event_mean": sum(value_list) / len(value_list),
        "session_equal_mean": sum(session_means) / len(session_means),
        "positive_fraction": sum(v > 0 for v in value_list) / len(value_list),
    }


def session_cluster_bootstrap(
    values: Iterable[float],
    sessions: Iterable[str],
    *,
    repetitions: int = 1000,
    seed: int = 0,
) -> list[float]:
    """Bootstrap session means, preserving within-session dependence."""
    if repetitions <= 0:
        raise ValueError("repetitions_must_be_positive")
    grouped: dict[str, list[float]] = {}
    for session, value in zip(sessions, values):
        grouped.setdefault(str(session), []).append(float(value))
    if not grouped:
        raise ValueError("empty_bootstrap")
    rng = random.Random(seed)
    keys = sorted(grouped)
    result = []
    for _ in range(repetitions):
        sample = [rng.choice(keys) for _ in keys]
        result.append(sum(sum(grouped[key]) / len(grouped[key]) for key in sample) / len(sample))
    return result
