from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


CANONICAL_SYMBOL_ALIASES: dict[str, str] = {
    "NIFTY": "NIFTY",
    "NSE_INDEX|Nifty 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "NSE_INDEX|Nifty Bank": "BANKNIFTY",
    "BSE_INDEX|SENSEX": "SENSEX",
    "SENSEX": "SENSEX",
}


@dataclass(frozen=True)
class PatternAtlasContract:
    bar_minutes: int = 5
    volatility_window_bars: int = 60
    volatility_min_periods: int = 30
    residual_threshold: float = 2.0
    contraction_ratio: float = 0.50
    max_extension_fraction: float = 0.25
    horizons_minutes: tuple[int, ...] = (5, 15, 30, 60)
    permutation_count: int = 500
    random_seed: int = 42

    def validate(self) -> None:
        if self.bar_minutes <= 0:
            raise ValueError("bar_minutes must be positive")
        if self.volatility_window_bars <= 1:
            raise ValueError("volatility_window_bars must be greater than one")
        if not 2 <= self.volatility_min_periods <= self.volatility_window_bars:
            raise ValueError("volatility_min_periods must be within the rolling window")
        if self.residual_threshold <= 0:
            raise ValueError("residual_threshold must be positive")
        if not 0 < self.contraction_ratio < 1:
            raise ValueError("contraction_ratio must be between zero and one")
        if self.max_extension_fraction < 0:
            raise ValueError("max_extension_fraction must be nonnegative")
        if not self.horizons_minutes:
            raise ValueError("at least one horizon is required")
        if any(h <= 0 or h % self.bar_minutes for h in self.horizons_minutes):
            raise ValueError("horizons must be positive multiples of bar_minutes")
        if self.permutation_count <= 0:
            raise ValueError("permutation_count must be positive")


def canonicalize_symbol(symbol: str) -> str:
    normalized = str(symbol).strip()
    if normalized not in CANONICAL_SYMBOL_ALIASES:
        raise ValueError(f"unsupported atlas symbol: {normalized}")
    return CANONICAL_SYMBOL_ALIASES[normalized]


def _validate_ohlc(frame: pd.DataFrame, *, source: str = "<memory>") -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{source} missing OHLC columns {missing}")
    if frame.empty:
        raise ValueError(f"{source} is empty")

    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="raise")
    if normalized["timestamp"].isna().any():
        raise ValueError(f"{source} contains null timestamps")
    if normalized["timestamp"].duplicated().any():
        raise ValueError(f"{source} contains duplicate timestamps")

    for column in ("open", "high", "low", "close"):
        values = pd.to_numeric(normalized[column], errors="raise").astype(float)
        if not np.isfinite(values.to_numpy()).all():
            raise ValueError(f"{source} contains non-finite {column}")
        normalized[column] = values

    if "volume" in normalized.columns:
        volume = pd.to_numeric(normalized["volume"], errors="coerce").fillna(0.0).astype(float)
        if (volume < 0).any() or not np.isfinite(volume.to_numpy()).all():
            raise ValueError(f"{source} contains invalid volume")
        normalized["volume"] = volume
    else:
        normalized["volume"] = 0.0

    return normalized.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def resample_completed_bars(
    frame: pd.DataFrame,
    *,
    bar_minutes: int = 5,
    source: str = "<memory>",
) -> pd.DataFrame:
    """Aggregate start-labelled candles into deterministic completed bars.

    The returned timestamp labels the bucket start. A row is usable only after the
    complete bucket has ended; the atlas records that separately as ``known_at``.
    """
    if bar_minutes <= 0:
        raise ValueError("bar_minutes must be positive")
    normalized = _validate_ohlc(frame, source=source)
    normalized = normalized.set_index("timestamp")
    frequency = f"{bar_minutes}min"
    grouped = normalized.groupby(normalized.index.floor(frequency), sort=True)
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_rows=("close", "size"),
    )
    bars.index.name = "timestamp"
    bars = bars.reset_index()
    bars["known_at"] = bars["timestamp"] + pd.Timedelta(minutes=bar_minutes)
    return bars


def _session_keys(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(index.normalize(), index=index)


def _safe_log_return(close: pd.Series) -> pd.Series:
    if (close <= 0).any():
        raise ValueError("close prices must be positive")
    returns = np.log(close).diff()
    sessions = _session_keys(close.index)
    returns = returns.mask(sessions.ne(sessions.shift(1)))
    return returns


def _causal_volatility(
    returns: pd.Series,
    *,
    window: int,
    min_periods: int,
) -> pd.Series:
    return returns.rolling(window, min_periods=min_periods).std(ddof=1).shift(1)


def build_residual_panel(
    frames_by_symbol: Mapping[str, pd.DataFrame],
    *,
    contract: PatternAtlasContract = PatternAtlasContract(),
) -> pd.DataFrame:
    """Build a causal cross-index standardized residual panel.

    Each target return is divided by its own trailing volatility and compared
    with the mean standardized return of the other available indices. Rolling
    volatility is shifted by one completed bar, so the event bar cannot affect
    its own normalizer.
    """
    contract.validate()
    canonical_frames: dict[str, pd.DataFrame] = {}
    for raw_symbol, raw_frame in frames_by_symbol.items():
        symbol = canonicalize_symbol(raw_symbol)
        if symbol in canonical_frames:
            raise ValueError(f"duplicate canonical symbol supplied: {symbol}")
        bars = resample_completed_bars(
            raw_frame,
            bar_minutes=contract.bar_minutes,
            source=str(raw_symbol),
        ).set_index("timestamp")
        canonical_frames[symbol] = bars

    if len(canonical_frames) < 2:
        raise ValueError("at least two canonical indices are required")

    panel_parts: list[pd.DataFrame] = []
    for symbol, frame in sorted(canonical_frames.items()):
        renamed = frame[["open", "high", "low", "close", "volume", "known_at"]].rename(
            columns=lambda column: f"{symbol}__{column}"
        )
        panel_parts.append(renamed)
    panel = pd.concat(panel_parts, axis=1, join="outer").sort_index()
    panel.index.name = "timestamp"

    symbols = sorted(canonical_frames)
    z_columns: dict[str, pd.Series] = {}
    for symbol in symbols:
        close = panel[f"{symbol}__close"]
        returns = _safe_log_return(close)
        volatility = _causal_volatility(
            returns,
            window=contract.volatility_window_bars,
            min_periods=contract.volatility_min_periods,
        )
        z_score = returns / volatility.replace(0.0, np.nan)
        z_columns[symbol] = z_score
        panel[f"{symbol}__log_return"] = returns
        panel[f"{symbol}__causal_vol"] = volatility
        panel[f"{symbol}__return_z"] = z_score

    z_frame = pd.DataFrame(z_columns, index=panel.index)
    for target in symbols:
        peers = [symbol for symbol in symbols if symbol != target]
        peer_z = z_frame[peers]
        peer_count = peer_z.notna().sum(axis=1)
        peer_mean = peer_z.mean(axis=1, skipna=True).where(peer_count >= 1)
        panel[f"{target}__peer_count"] = peer_count.astype(int)
        panel[f"{target}__peer_z_mean"] = peer_mean
        panel[f"{target}__residual_z"] = z_frame[target] - peer_mean

    return panel


def _time_bucket(timestamp: pd.Timestamp) -> str:
    minute = timestamp.hour * 60 + timestamp.minute
    if minute < 10 * 60:
        return "OPEN_0915_1000"
    if minute < 12 * 60:
        return "MORNING_1000_1200"
    if minute < 14 * 60:
        return "MIDDAY_1200_1400"
    if minute < 15 * 60:
        return "AFTERNOON_1400_1500"
    return "CLOSE_1500_ONWARD"


def _magnitude_bucket(value: float) -> str:
    magnitude = abs(float(value))
    if magnitude < 2.5:
        return "RZ_2_2P5"
    if magnitude < 3.0:
        return "RZ_2P5_3"
    return "RZ_3_PLUS"


def _volatility_bucket(vol_bps: float) -> str:
    if not np.isfinite(vol_bps):
        return "VOL_UNKNOWN"
    if vol_bps < 5:
        return "VOL_LT_5BPS"
    if vol_bps < 10:
        return "VOL_5_10BPS"
    if vol_bps < 20:
        return "VOL_10_20BPS"
    return "VOL_20BPS_PLUS"


def _calendar_period(timestamp: pd.Timestamp) -> str:
    half = 1 if timestamp.month <= 6 else 2
    return f"{timestamp.year}H{half}"


def extract_residual_events(
    panel: pd.DataFrame,
    *,
    contract: PatternAtlasContract = PatternAtlasContract(),
) -> pd.DataFrame:
    contract.validate()
    symbols = sorted(
        column.removesuffix("__residual_z")
        for column in panel.columns
        if column.endswith("__residual_z")
    )
    if not symbols:
        raise ValueError("panel contains no residual columns")

    horizon_bars = {
        horizon: horizon // contract.bar_minutes for horizon in contract.horizons_minutes
    }
    max_horizon_bars = max(horizon_bars.values())
    records: list[dict[str, object]] = []

    for target in symbols:
        residual = panel[f"{target}__residual_z"]
        target_close = panel[f"{target}__close"]
        target_high = panel[f"{target}__high"]
        target_low = panel[f"{target}__low"]
        target_return = panel[f"{target}__log_return"]
        target_vol = panel[f"{target}__causal_vol"]
        peer_count = panel[f"{target}__peer_count"]
        known_at = panel[f"{target}__known_at"]

        event_mask = residual.abs().ge(contract.residual_threshold)
        candidate_positions = np.flatnonzero(event_mask.fillna(False).to_numpy())
        for position in candidate_positions:
            if position + 1 + max_horizon_bars >= len(panel):
                continue
            event_time = panel.index[position]
            confirmation_time = panel.index[position + 1]
            final_outcome_time = panel.index[position + 1 + max_horizon_bars]
            if (
                event_time.normalize() != confirmation_time.normalize()
                or event_time.normalize() != final_outcome_time.normalize()
            ):
                continue

            event_residual = float(residual.iloc[position])
            shock_sign = 1 if event_residual > 0 else -1
            mean_reversion_side = "SELL" if shock_sign > 0 else "BUY"
            entry_close = float(target_close.iloc[position])
            next_close = float(target_close.iloc[position + 1])
            required_prices = [
                entry_close,
                next_close,
                float(target_high.iloc[position]),
                float(target_low.iloc[position]),
                float(target_high.iloc[position + 1]),
                float(target_low.iloc[position + 1]),
            ]
            if not np.isfinite(required_prices).all():
                continue

            outcome_prices = []
            for bars in horizon_bars.values():
                outcome_prices.extend(
                    [
                        float(target_close.iloc[position + bars]),
                        float(target_close.iloc[position + 1 + bars]),
                    ]
                )
            if not np.isfinite(outcome_prices).all():
                continue

            event_range_bps = (
                (float(target_high.iloc[position]) - float(target_low.iloc[position]))
                / entry_close
                * 10000.0
            )
            if shock_sign > 0:
                extension_bps = max(
                    0.0,
                    (float(target_high.iloc[position + 1]) - entry_close)
                    / entry_close
                    * 10000.0,
                )
            else:
                extension_bps = max(
                    0.0,
                    (entry_close - float(target_low.iloc[position + 1]))
                    / entry_close
                    * 10000.0,
                )
            extension_fraction = extension_bps / max(event_range_bps, 1e-12)
            next_residual = float(residual.iloc[position + 1])
            residual_contracted = bool(
                np.isfinite(next_residual)
                and abs(next_residual) <= contract.contraction_ratio * abs(event_residual)
            )
            continuation_failed = bool(
                extension_fraction <= contract.max_extension_fraction
            )
            exhaustion_confirmed = bool(residual_contracted and continuation_failed)

            row: dict[str, object] = {
                "target_symbol": target,
                "event_time": event_time.isoformat(),
                "event_known_at": pd.Timestamp(known_at.iloc[position]).isoformat(),
                "confirmation_time": confirmation_time.isoformat(),
                "event_side": "UP_SHOCK" if shock_sign > 0 else "DOWN_SHOCK",
                "mean_reversion_side": mean_reversion_side,
                "shock_sign": shock_sign,
                "residual_z": event_residual,
                "next_residual_z": next_residual,
                "peer_count": int(peer_count.iloc[position]),
                "event_return_bps": abs(float(target_return.iloc[position])) * 10000.0,
                "causal_volatility_bps": float(target_vol.iloc[position]) * 10000.0,
                "event_range_bps": event_range_bps,
                "confirmation_extension_bps": extension_bps,
                "confirmation_extension_fraction": extension_fraction,
                "residual_contracted": residual_contracted,
                "continuation_failed": continuation_failed,
                "exhaustion_confirmed": exhaustion_confirmed,
                "time_bucket": _time_bucket(event_time),
                "magnitude_bucket": _magnitude_bucket(event_residual),
                "volatility_bucket": _volatility_bucket(
                    float(target_vol.iloc[position]) * 10000.0
                ),
                "calendar_period": _calendar_period(event_time),
            }

            for horizon, bars in horizon_bars.items():
                raw_future_close = float(target_close.iloc[position + bars])
                confirmed_future_close = float(target_close.iloc[position + 1 + bars])
                row[f"raw_reversion_bps_{horizon}m"] = (
                    -shock_sign * (raw_future_close / entry_close - 1.0) * 10000.0
                )
                row[f"confirmed_reversion_bps_{horizon}m"] = (
                    -shock_sign * (confirmed_future_close / next_close - 1.0) * 10000.0
                )

            future_slice = slice(position + 1, position + 1 + max_horizon_bars)
            future_high = float(target_high.iloc[future_slice].max())
            future_low = float(target_low.iloc[future_slice].min())
            if shock_sign > 0:
                raw_mfe = (entry_close - future_low) / entry_close * 10000.0
                raw_mae = (future_high - entry_close) / entry_close * 10000.0
            else:
                raw_mfe = (future_high - entry_close) / entry_close * 10000.0
                raw_mae = (entry_close - future_low) / entry_close * 10000.0
            row["raw_mfe_bps_60m"] = raw_mfe
            row["raw_mae_bps_60m"] = raw_mae
            records.append(row)

    events = pd.DataFrame.from_records(records)
    if events.empty:
        return events
    return events.sort_values(["event_time", "target_symbol"], kind="mergesort").reset_index(
        drop=True
    )


def _metric_summary(frame: pd.DataFrame, *, horizons: Iterable[int]) -> dict[str, object]:
    result: dict[str, object] = {"event_count": int(len(frame))}
    if frame.empty:
        return result
    result.update(
        {
            "confirmed_count": int(frame["exhaustion_confirmed"].sum()),
            "confirmed_rate": float(frame["exhaustion_confirmed"].mean()),
            "mean_abs_residual_z": float(frame["residual_z"].abs().mean()),
            "mean_raw_mfe_bps_60m": float(frame["raw_mfe_bps_60m"].mean()),
            "mean_raw_mae_bps_60m": float(frame["raw_mae_bps_60m"].mean()),
        }
    )
    for horizon in horizons:
        raw = frame[f"raw_reversion_bps_{horizon}m"]
        confirmed = frame.loc[
            frame["exhaustion_confirmed"], f"confirmed_reversion_bps_{horizon}m"
        ]
        result[f"raw_mean_reversion_bps_{horizon}m"] = float(raw.mean())
        result[f"raw_median_reversion_bps_{horizon}m"] = float(raw.median())
        result[f"raw_positive_rate_{horizon}m"] = float((raw > 0).mean())
        result[f"confirmed_mean_reversion_bps_{horizon}m"] = (
            float(confirmed.mean()) if not confirmed.empty else None
        )
        result[f"confirmed_positive_rate_{horizon}m"] = (
            float((confirmed > 0).mean()) if not confirmed.empty else None
        )
    return result


def build_segment_metrics(
    events: pd.DataFrame,
    *,
    contract: PatternAtlasContract = PatternAtlasContract(),
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    dimensions = [
        ("overall", []),
        ("symbol", ["target_symbol"]),
        ("symbol_side", ["target_symbol", "event_side"]),
        ("symbol_time", ["target_symbol", "time_bucket"]),
        ("symbol_magnitude", ["target_symbol", "magnitude_bucket"]),
        ("symbol_volatility", ["target_symbol", "volatility_bucket"]),
        ("calendar_period", ["calendar_period"]),
        ("confirmation", ["exhaustion_confirmed"]),
    ]
    rows: list[dict[str, object]] = []
    for dimension_name, columns in dimensions:
        if not columns:
            groups = [((), events)]
        else:
            groups = events.groupby(columns, dropna=False, sort=True)
        for key, frame in groups:
            key_values = key if isinstance(key, tuple) else (key,)
            row: dict[str, object] = {"dimension": dimension_name}
            for column, value in zip(columns, key_values):
                row[column] = value
            row.update(_metric_summary(frame, horizons=contract.horizons_minutes))
            rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["dimension", "event_count"], ascending=[True, False], kind="mergesort"
    )


def permutation_control(
    events: pd.DataFrame,
    *,
    horizon_minutes: int = 15,
    contract: PatternAtlasContract = PatternAtlasContract(),
) -> dict[str, object]:
    """Direction-permutation control for the raw target move.

    The event timestamps and absolute forward moves stay fixed. Shock directions
    are shuffled within symbol and time-of-day buckets, destroying the proposed
    residual direction while retaining the event distribution.
    """
    if events.empty:
        return {
            "classification": "NO_EVENTS",
            "horizon_minutes": horizon_minutes,
            "event_count": 0,
        }
    metric = f"raw_reversion_bps_{horizon_minutes}m"
    if metric not in events.columns:
        raise ValueError(f"unsupported control horizon: {horizon_minutes}")

    observed = float(events[metric].mean())
    implied_forward_return = -events["shock_sign"].astype(float) * events[metric].astype(float)
    rng = np.random.default_rng(contract.random_seed)
    permutation_means: list[float] = []
    group_indices = [
        group.index.to_numpy()
        for _, group in events.groupby(["target_symbol", "time_bucket"], sort=True)
    ]
    base_signs = events["shock_sign"].astype(float).to_numpy()
    forward = implied_forward_return.to_numpy()

    for _ in range(contract.permutation_count):
        shuffled = base_signs.copy()
        for indices in group_indices:
            shuffled[indices] = rng.permutation(shuffled[indices])
        permutation_means.append(float(np.mean(-shuffled * forward)))

    null = np.asarray(permutation_means, dtype=float)
    p_value = float((1 + np.sum(null >= observed)) / (1 + len(null)))
    return {
        "classification": "DIRECTION_PERMUTATION_CONTROL",
        "horizon_minutes": horizon_minutes,
        "event_count": int(len(events)),
        "permutation_count": int(contract.permutation_count),
        "observed_mean_reversion_bps": observed,
        "null_mean_reversion_bps": float(null.mean()),
        "null_std_reversion_bps": float(null.std(ddof=1)),
        "one_sided_p_value": p_value,
        "random_seed": int(contract.random_seed),
    }
