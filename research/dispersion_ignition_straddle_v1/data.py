from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .common import DataContractError, HORIZONS, normalize_timestamp


@dataclass(frozen=True)
class SourcePaths:
    constituent_bars: Path
    contract_inventory: Path
    option_root: Path


def _priority(paths: Iterable[Path], tokens: tuple[str, ...]) -> Path:
    candidates = sorted(set(Path(p).resolve() for p in paths))
    if not candidates:
        raise DataContractError(f"no source candidates for {tokens}")
    return sorted(candidates, key=lambda p: (-sum(t in str(p) for t in tokens), len(str(p)), str(p)))[0]


def resolve_sources(repo_root: Path) -> SourcePaths:
    root = repo_root / "research" / "local_evidence_consolidation_v1"
    if not root.exists():
        raise DataContractError(f"missing evidence root: {root}")
    constituent = _priority(
        root.rglob("constituent_index_5m.parquet"),
        ("constituent-lead-lag-data-v1", "proxy_campaign_2024_2025_v2", "normalized"),
    )
    inventory = _priority(root.rglob("contract_inventory.parquet"), ("upstox-expired-options-v1", "manifests"))
    return SourcePaths(constituent, inventory, inventory.parent.parent)


def detect_index_symbol(bars: pd.DataFrame) -> str:
    symbols = set(bars["symbol"].astype(str).str.upper().str.strip())
    for candidate in ("NIFTY", "NIFTY50", "NIFTY 50", "NSE_INDEX|NIFTY 50"):
        if candidate in symbols:
            return candidate
    matches = sorted(s for s in symbols if "NIFTY" in s)
    if len(matches) == 1:
        return matches[0]
    raise DataContractError(f"cannot identify NIFTY index symbol: {matches[:10]}")


def load_constituent_bars(path: Path) -> tuple[pd.DataFrame, str]:
    bars = pd.read_parquet(path).copy()
    required = {"timestamp", "symbol", "open", "high", "low", "close"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise DataContractError(f"constituent bars missing: {missing}")
    bars["timestamp"] = normalize_timestamp(bars["timestamp"])
    bars["symbol"] = bars["symbol"].astype(str).str.upper().str.strip()
    for column in ("open", "high", "low", "close"):
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    invalid = (
        bars[["open", "high", "low", "close"]].isna().any(axis=1)
        | (bars[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (bars["high"] < bars[["open", "close"]].max(axis=1))
        | (bars["low"] > bars[["open", "close"]].min(axis=1))
        | (bars["high"] < bars["low"])
    )
    if invalid.any():
        raise DataContractError(f"invalid constituent OHLC rows: {int(invalid.sum())}")
    bars["session"] = bars.get("session", bars["timestamp"].dt.date.astype(str)).astype(str)
    duplicates = bars.duplicated(["symbol", "timestamp"], keep=False)
    if duplicates.any():
        raise DataContractError(f"duplicate constituent keys: {int(duplicates.sum())}")
    index_symbol = detect_index_symbol(bars)
    return bars.sort_values(["session", "symbol", "timestamp"], kind="mergesort"), index_symbol


def _future_range(day: pd.DataFrame, count: int) -> np.ndarray:
    highs, lows, closes = (day[c].to_numpy(float) for c in ("high", "low", "close"))
    out = np.full(len(day), np.nan)
    for pos in range(len(day)):
        start, stop = pos + 1, pos + 1 + count
        if stop <= len(day):
            out[pos] = (highs[start:stop].max() - lows[start:stop].min()) / closes[pos]
    return out


def build_features(bars: pd.DataFrame, index_symbol: str, minimum_constituents: int = 40) -> pd.DataFrame:
    bars = bars.copy()
    bars["ret_1"] = bars.groupby(["session", "symbol"], sort=False)["close"].pct_change()
    constituents = bars[(bars["symbol"] != index_symbol) & bars["ret_1"].notna()]
    rows: list[dict[str, Any]] = []
    for (session, timestamp), group in constituents.groupby(["session", "timestamp"], sort=True):
        values = group["ret_1"].to_numpy(float)
        values = values[np.isfinite(values)]
        if len(values) < minimum_constituents:
            continue
        median = float(np.median(values))
        absolute = np.abs(values)
        ordered = np.sort(absolute)[::-1]
        total = absolute.sum()
        rows.append({
            "session": str(session), "bar_timestamp": timestamp,
            "signal_timestamp": timestamp + pd.Timedelta(minutes=5),
            "constituent_count": len(values), "mean_return": float(values.mean()),
            "median_return": median, "median_abs_return": float(np.median(absolute)),
            "dispersion_mad": float(np.median(np.abs(values - median))),
            "dispersion_iqr": float(np.quantile(values, .75) - np.quantile(values, .25)),
            "up_share": float(np.mean(values > 0)), "down_share": float(np.mean(values < 0)),
            "absolute_participation": float(max(np.mean(values > 0), np.mean(values < 0))),
            "top1_abs_share": float(ordered[:1].sum() / total) if total else 0.0,
            "top3_abs_share": float(ordered[:3].sum() / total) if total else 0.0,
            "top5_abs_share": float(ordered[:5].sum() / total) if total else 0.0,
        })
    features = pd.DataFrame(rows)
    if features.empty:
        raise DataContractError("no feature rows passed constituent coverage")

    index = bars[bars["symbol"] == index_symbol].copy()
    index["index_ret_1"] = index.groupby("session", sort=False)["close"].pct_change()
    parts = []
    for _, day in index.groupby("session", sort=True):
        day = day.sort_values("timestamp", kind="mergesort").copy()
        for horizon in HORIZONS:
            day[f"future_range_{horizon}"] = _future_range(day, horizon // 5)
        parts.append(day)
    index = pd.concat(parts, ignore_index=True).rename(columns={"timestamp": "bar_timestamp", "close": "index_close"})
    keep = ["session", "bar_timestamp", "index_close", "index_ret_1", *[f"future_range_{h}" for h in HORIZONS]]
    features = features.merge(index[keep], on=["session", "bar_timestamp"], how="inner", validate="one_to_one")
    features["index_expression_ratio"] = features["index_ret_1"].abs() / features["median_abs_return"].clip(lower=1e-8)
    features = features.sort_values(["session", "bar_timestamp"], kind="mergesort").reset_index(drop=True)
    for column in ("dispersion_mad", "absolute_participation"):
        features[f"{column}_change"] = features.groupby("session", sort=False)[column].diff()
    features["minute_of_day"] = features["signal_timestamp"].dt.hour * 60 + features["signal_timestamp"].dt.minute
    return features
