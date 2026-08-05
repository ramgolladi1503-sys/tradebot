from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping

import pandas as pd


class PSILORError(ValueError):
    """Raised when PSILOR research evidence violates a frozen contract."""


@dataclass(frozen=True)
class ReconciledTrade:
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    exit_price: float
    gross_return: float
    round_trip_cost_fraction: float
    net_return: float
    elapsed_seconds: float
    entry_row_index: int
    exit_row_index: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite_positive(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PSILORError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise PSILORError(f"{field} must be positive and finite")
    return result


def reconcile_long_return(
    *,
    entry_price: Any,
    exit_price: Any,
    round_trip_cost_fraction: Any = 0.0,
) -> tuple[float, float]:
    entry = _finite_positive(entry_price, field="entry_price")
    exit_value = _finite_positive(exit_price, field="exit_price")
    cost = float(round_trip_cost_fraction)
    if not math.isfinite(cost) or cost < 0:
        raise PSILORError("round_trip_cost_fraction must be finite and non-negative")
    gross = exit_value / entry - 1.0
    return float(gross), float(gross - cost)


def _timestamps(frame: pd.DataFrame, timestamp_col: str) -> pd.Series:
    if timestamp_col not in frame:
        raise PSILORError(f"missing timestamp column: {timestamp_col}")
    values = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True)
    if values.isna().any():
        raise PSILORError("timestamps must be parseable")
    if not values.is_monotonic_increasing:
        raise PSILORError("timestamps must be monotonic increasing")
    if values.duplicated().any():
        raise PSILORError("timestamps must be unique")
    return values


def _first_index_at_or_after(values: pd.Series, target: pd.Timestamp) -> int:
    matches = values[values >= target]
    if matches.empty:
        raise PSILORError(f"no causal row at or after {target.isoformat()}")
    return int(matches.index[0])


def build_elapsed_time_trade(
    frame: pd.DataFrame,
    *,
    signal_timestamp: Any,
    entry_delay_seconds: int,
    hold_seconds: int,
    timestamp_col: str = "timestamp",
    entry_price_col: str = "close",
    exit_price_col: str = "close",
    round_trip_cost_fraction: float = 0.0,
) -> ReconciledTrade:
    if entry_delay_seconds < 0 or hold_seconds <= 0:
        raise PSILORError("entry delay must be non-negative and hold must be positive")
    if entry_price_col not in frame or exit_price_col not in frame:
        raise PSILORError("price column missing")
    values = _timestamps(frame, timestamp_col)
    signal_ts = pd.Timestamp(signal_timestamp)
    signal_ts = (
        signal_ts.tz_localize("UTC")
        if signal_ts.tzinfo is None
        else signal_ts.tz_convert("UTC")
    )
    entry_target = signal_ts + pd.Timedelta(seconds=entry_delay_seconds)
    entry_index = _first_index_at_or_after(values, entry_target)
    entry_ts = values.loc[entry_index]
    exit_target = entry_ts + pd.Timedelta(seconds=hold_seconds)
    exit_index = _first_index_at_or_after(values, exit_target)
    exit_ts = values.loc[exit_index]
    if entry_ts.date() != exit_ts.date():
        raise PSILORError("entry and exit must remain in one session")
    entry_price = _finite_positive(
        frame.loc[entry_index, entry_price_col], field="entry_price"
    )
    exit_price = _finite_positive(
        frame.loc[exit_index, exit_price_col], field="exit_price"
    )
    gross, net = reconcile_long_return(
        entry_price=entry_price,
        exit_price=exit_price,
        round_trip_cost_fraction=round_trip_cost_fraction,
    )
    return ReconciledTrade(
        entry_timestamp=entry_ts.isoformat(),
        exit_timestamp=exit_ts.isoformat(),
        entry_price=entry_price,
        exit_price=exit_price,
        gross_return=gross,
        round_trip_cost_fraction=float(round_trip_cost_fraction),
        net_return=net,
        elapsed_seconds=float((exit_ts - entry_ts).total_seconds()),
        entry_row_index=entry_index,
        exit_row_index=exit_index,
    )


def audit_bar_horizon(
    frame: pd.DataFrame,
    *,
    horizon_bars: int,
    timestamp_col: str = "timestamp",
) -> dict[str, Any]:
    if horizon_bars <= 0:
        raise PSILORError("horizon_bars must be positive")
    values = _timestamps(frame, timestamp_col)
    elapsed = (values.shift(-horizon_bars) - values).dt.total_seconds().dropna()
    if elapsed.empty:
        raise PSILORError("insufficient rows for bar-horizon audit")
    unique_seconds = sorted(float(value) for value in elapsed.unique())
    return {
        "horizon_bars": int(horizon_bars),
        "observations": int(len(elapsed)),
        "minimum_elapsed_seconds": float(elapsed.min()),
        "median_elapsed_seconds": float(elapsed.median()),
        "maximum_elapsed_seconds": float(elapsed.max()),
        "unique_elapsed_seconds": unique_seconds,
        "mixed_elapsed_horizon": len(unique_seconds) > 1,
    }


def assert_precomputed_outcome_reconciles(
    precomputed_return: Any,
    trade: ReconciledTrade,
    *,
    tolerance: float = 1e-12,
) -> None:
    value = float(precomputed_return)
    if not math.isfinite(value):
        raise PSILORError("precomputed return must be finite")
    if not math.isclose(
        value, trade.gross_return, rel_tol=0.0, abs_tol=tolerance
    ):
        raise PSILORError(
            "precomputed outcome does not reconcile to recorded entry and exit prices"
        )


def resolve_long_barrier_exit(
    *,
    bar_open: Any,
    bar_high: Any,
    bar_low: Any,
    stop_price: Any,
    target_price: Any,
) -> dict[str, Any]:
    open_value = _finite_positive(bar_open, field="bar_open")
    high = _finite_positive(bar_high, field="bar_high")
    low = _finite_positive(bar_low, field="bar_low")
    stop = _finite_positive(stop_price, field="stop_price")
    target = _finite_positive(target_price, field="target_price")
    if low > high:
        raise PSILORError("bar_low cannot exceed bar_high")
    stop_hit = low <= stop
    target_hit = high >= target
    if stop_hit and target_hit:
        return {"exit_price": stop, "reason": "AMBIGUOUS_STOP_FIRST"}
    if stop_hit:
        return {"exit_price": stop, "reason": "STOP"}
    if target_hit:
        return {"exit_price": target, "reason": "TARGET"}
    return {"exit_price": open_value, "reason": "NO_BARRIER"}


def ensure_no_future_fields(
    row: Mapping[str, Any],
    *,
    forbidden_tokens: tuple[str, ...] = (
        "future",
        "outcome",
        "realized",
        "exit_",
    ),
) -> None:
    offending = sorted(
        key
        for key in row
        if any(token in str(key).lower() for token in forbidden_tokens)
    )
    if offending:
        raise PSILORError(
            f"future/outcome fields present in signal row: {offending}"
        )
