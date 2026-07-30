from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
HORIZONS = (5, 10, 15, 20)
FRICTIONS = {"base": 0.005, "stress": 0.010, "severe": 0.015}
VARIANTS = (
    "high_dispersion_high_participation_low_expression",
    "rising_dispersion_rising_participation_low_expression",
    "high_dispersion_broad_not_concentrated_low_expression",
)


class DataContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Metrics:
    trades: int
    sessions: int
    mean_return: float | None
    median_return: float | None
    profit_factor: float | None
    bootstrap_ci_low: float | None
    remove_top_five_mean: float | None
    remove_top_five_profit_factor: float | None
    largest_winner_share: float | None
    largest_session_share: float | None
    positive_folds: int
    total_folds: int


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def normalize_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise DataContractError(f"invalid timestamps: {int(parsed.isna().sum())}")
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize(IST, ambiguous="raise", nonexistent="raise")
    return parsed.dt.tz_convert(IST)


def split_sessions(sessions: Iterable[str]) -> dict[str, list[str]]:
    ordered = sorted(set(map(str, sessions)))
    if len(ordered) < 80:
        raise DataContractError(f"insufficient overlap sessions: {len(ordered)}")
    r = int(len(ordered) * 0.70)
    v = int(len(ordered) * 0.85)
    return {"research": ordered[:r], "validation": ordered[r:v], "holdout": ordered[v:]}


def time_bucket(series: pd.Series) -> pd.Series:
    return (series // 30).astype(int)


def _flat_thresholds(frame: pd.DataFrame) -> dict[str, float]:
    clean = frame.replace([np.inf, -np.inf], np.nan)
    return {
        "dispersion_high": float(clean["dispersion_mad"].quantile(0.75)),
        "participation_high": float(clean["absolute_participation"].quantile(0.75)),
        "expression_low": float(clean["index_expression_ratio"].quantile(0.35)),
        "dispersion_change_high": float(clean["dispersion_mad_change"].quantile(0.65)),
        "participation_change_high": float(clean["absolute_participation_change"].quantile(0.65)),
        "top5_broad": float(clean["top5_abs_share"].quantile(0.50)),
    }


def training_thresholds(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise DataContractError("empty threshold training frame")
    working = frame.copy()
    if "minute_of_day" not in working:
        working["minute_of_day"] = 0
    working["time_bucket"] = time_bucket(working["minute_of_day"])
    global_values = _flat_thresholds(working)
    by_bucket: dict[str, dict[str, float]] = {}
    for bucket, group in working.groupby("time_bucket", sort=True):
        by_bucket[str(int(bucket))] = _flat_thresholds(group) if len(group) >= 100 else global_values
    return {"global": global_values, "by_time_bucket": by_bucket}


def _threshold_series(frame: pd.DataFrame, thresholds: dict[str, Any], key: str) -> pd.Series:
    if "global" not in thresholds:
        return pd.Series(float(thresholds[key]), index=frame.index)
    minute = frame["minute_of_day"] if "minute_of_day" in frame else pd.Series(0, index=frame.index)
    buckets = time_bucket(minute)
    return buckets.map(
        lambda b: float(thresholds["by_time_bucket"].get(str(int(b)), thresholds["global"])[key])
    )


def variant_mask(frame: pd.DataFrame, thresholds: dict[str, Any], variant: str) -> pd.Series:
    low_expression = frame["index_expression_ratio"] <= _threshold_series(frame, thresholds, "expression_low")
    if variant == VARIANTS[0]:
        return low_expression & (frame["dispersion_mad"] >= _threshold_series(frame, thresholds, "dispersion_high")) & (
            frame["absolute_participation"] >= _threshold_series(frame, thresholds, "participation_high")
        )
    if variant == VARIANTS[1]:
        return low_expression & (
            frame["dispersion_mad_change"] >= _threshold_series(frame, thresholds, "dispersion_change_high")
        ) & (
            frame["absolute_participation_change"]
            >= _threshold_series(frame, thresholds, "participation_change_high")
        )
    if variant == VARIANTS[2]:
        return low_expression & (frame["dispersion_mad"] >= _threshold_series(frame, thresholds, "dispersion_high")) & (
            frame["top5_abs_share"] <= _threshold_series(frame, thresholds, "top5_broad")
        )
    raise ValueError(variant)


def calculate_metrics(ledger: pd.DataFrame, column: str = "stress_return", seed: int = 7619) -> Metrics:
    if ledger.empty or column not in ledger:
        return Metrics(0, 0, None, None, None, None, None, None, None, None, 0, 0)
    values = pd.to_numeric(ledger[column], errors="coerce").dropna().to_numpy(float)
    if not len(values):
        return Metrics(0, 0, None, None, None, None, None, None, None, None, 0, 0)
    gains, losses = values[values > 0].sum(), -values[values < 0].sum()
    pf = gains / losses if losses > 0 else (math.inf if gains > 0 else None)
    trimmed = np.sort(values)[:-5] if len(values) > 5 else np.array([])
    tg, tl = trimmed[trimmed > 0].sum(), -trimmed[trimmed < 0].sum()
    tpf = tg / tl if tl > 0 else (math.inf if tg > 0 else None)
    samples = np.random.default_rng(seed).choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
    positive = values[values > 0]
    winner_share = float(positive.max() / positive.sum()) if len(positive) and positive.sum() > 0 else None
    session_returns = ledger.assign(_r=pd.to_numeric(ledger[column], errors="coerce")).groupby("session")["_r"].sum()
    profitable = session_returns[session_returns > 0]
    session_share = float(profitable.max() / profitable.sum()) if len(profitable) and profitable.sum() > 0 else None
    folds = ledger.assign(_r=pd.to_numeric(ledger[column], errors="coerce")).groupby("fold")["_r"].mean()
    return Metrics(
        len(values), int(ledger["session"].nunique()), float(values.mean()), float(np.median(values)),
        float(pf) if pf is not None and np.isfinite(pf) else pf, float(np.quantile(samples, 0.025)),
        float(trimmed.mean()) if len(trimmed) else None,
        float(tpf) if tpf is not None and np.isfinite(tpf) else tpf,
        winner_share, session_share, int((folds > 0).sum()), int(len(folds)),
    )


def oof_gate(metrics: Metrics, range_lift: float | None, delayed_mean: float | None) -> bool:
    return bool(
        metrics.trades >= 80 and metrics.sessions >= 50 and (metrics.mean_return or 0) > 0
        and (metrics.bootstrap_ci_low or -1) > 0 and (metrics.remove_top_five_mean or -1) > 0
        and (metrics.profit_factor or 0) > 1.10 and metrics.positive_folds >= 4 and metrics.total_folds >= 5
        and (metrics.largest_winner_share is None or metrics.largest_winner_share < 0.18)
        and (metrics.largest_session_share is None or metrics.largest_session_share < 0.20)
        and range_lift is not None and range_lift > 0 and delayed_mean is not None
        and metrics.mean_return is not None and metrics.mean_return > delayed_mean
    )


def forward_gate(metrics: Metrics, min_trades: int = 20, min_sessions: int = 15) -> bool:
    return bool(
        metrics.trades >= min_trades and metrics.sessions >= min_sessions and (metrics.mean_return or 0) > 0
        and (metrics.bootstrap_ci_low or -1) > 0 and (metrics.remove_top_five_mean or -1) > 0
        and (metrics.profit_factor or 0) > 1.05
        and (metrics.largest_winner_share is None or metrics.largest_winner_share < 0.24)
        and (metrics.largest_session_share is None or metrics.largest_session_share < 0.25)
    )
