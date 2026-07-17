from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from .models import HistoricalCampaignError


def load_canonical_candles(path: str | Path, *, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise HistoricalCampaignError(f"dataset_not_found:{source}")
    frame = pd.read_parquet(source) if source.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(source)
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise HistoricalCampaignError(f"missing_columns:{','.join(missing)}")
    frame = frame[sorted(required)].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    if frame["timestamp"].dt.tz is None:
        frame["timestamp"] = frame["timestamp"].dt.tz_localize(timezone, ambiguous="NaT", nonexistent="shift_forward")
    else:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert(timezone)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | frame[["open", "high", "low", "close"]].le(0).any(axis=1)
    )
    if bool(invalid.any()):
        raise HistoricalCampaignError(f"invalid_ohlc_geometry_rows:{int(invalid.sum())}")
    frame = frame.drop_duplicates(subset=["timestamp", "symbol"], keep="last").sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    if frame.empty:
        raise HistoricalCampaignError("dataset_empty")
    return frame


def prepare_features(frame: pd.DataFrame, *, timezone: str) -> pd.DataFrame:
    work = frame.copy()
    work["session_date"] = work["timestamp"].dt.tz_convert(timezone).dt.date.astype(str)
    outputs: list[pd.DataFrame] = []
    for _, session in work.groupby("session_date", sort=True):
        session = session.sort_values("timestamp").reset_index(drop=True)
        previous_close = session["close"].shift(1)
        true_range = pd.concat([
            session["high"] - session["low"],
            (session["high"] - previous_close).abs(),
            (session["low"] - previous_close).abs(),
        ], axis=1).max(axis=1)
        typical = (session["high"] + session["low"] + session["close"]) / 3.0
        volume = session["volume"].clip(lower=0.0)
        cumulative_volume = volume.cumsum()
        session["vwap"] = (typical * volume).cumsum() / cumulative_volume.replace(0.0, math.nan)
        session["vwap_slope"] = session["vwap"].diff(5) / 5.0
        session["atr"] = true_range.rolling(14, min_periods=14).mean()
        session["atr_short"] = true_range.rolling(5, min_periods=5).mean()
        session["atr_long"] = true_range.rolling(20, min_periods=20).mean()
        session["day_high"] = session["high"].cummax()
        session["day_low"] = session["low"].cummin()
        high20 = session["high"].rolling(20, min_periods=20).max()
        low20 = session["low"].rolling(20, min_periods=20).min()
        session["range_width_pct"] = ((high20 - low20) / session["close"].abs()) * 100.0
        mean30 = volume.rolling(30, min_periods=20).mean()
        std30 = volume.rolling(30, min_periods=20).std(ddof=0)
        session["volume_z"] = (volume - mean30) / std30.replace(0.0, math.nan)
        session["orb_high"] = session["high"].iloc[:15].max() if len(session) >= 15 else math.nan
        session["orb_low"] = session["low"].iloc[:15].min() if len(session) >= 15 else math.nan
        outputs.append(session)
    return pd.concat(outputs, ignore_index=True) if outputs else work.iloc[0:0].copy()


def bar_payload(row: pd.Series, *, timezone: str) -> dict[str, Any]:
    start = pd.Timestamp(row["timestamp"])
    if start.tzinfo is None:
        start = start.tz_localize(timezone)
    end = start + pd.Timedelta(minutes=1)
    return {
        "symbol": str(row["symbol"]), "session_date": str(row["session_date"]), "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(), "bar_end_timestamp": end.isoformat(),
        "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]),
    }
