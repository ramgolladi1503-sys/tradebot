from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from .contracts import (
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    DiscoveryConfig,
    feature_names_from_frame,
)
from .features import compute_causal_features
from .labels import attach_option_outcome_availability, compute_triple_barrier_labels
from .regimes import classify_deterministic_regimes

_REQUIRED_BAR_COLUMNS = {"open", "high", "low", "close", "volume"}


def normalize_bars(bars: pd.DataFrame, config: DiscoveryConfig) -> pd.DataFrame:
    missing = _REQUIRED_BAR_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    if config.timestamp_column not in bars.columns:
        raise ValueError(f"missing timestamp column: {config.timestamp_column}")

    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(
        frame[config.timestamp_column], utc=True, errors="raise"
    )
    if frame["timestamp"].duplicated().any():
        duplicates = frame.loc[frame["timestamp"].duplicated(), "timestamp"].astype(str).tolist()
        raise ValueError(f"duplicate timestamps fail closed: {duplicates[:5]}")
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    for column in _REQUIRED_BAR_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (frame["volume"] < 0).any():
        raise ValueError("volume cannot be negative")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high violates OHLC ordering")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low violates OHLC ordering")

    frame["session_date"] = frame["timestamp"].dt.date.astype(str)
    return frame


def _quality_status(frame: pd.DataFrame) -> pd.Series:
    deltas = frame.groupby("session_date")["timestamp"].diff().dt.total_seconds()
    expected = deltas.dropna().median()
    if not np.isfinite(expected) or expected <= 0:
        return pd.Series("INSUFFICIENT_INTERVAL_EVIDENCE", index=frame.index)
    gaps = deltas > expected * 1.5
    status = pd.Series("OK", index=frame.index)
    status.loc[gaps] = "MISSING_INTERVAL_BEFORE_DECISION"
    return status


def build_discovery_dataset(
    bars: pd.DataFrame,
    *,
    config: DiscoveryConfig | None = None,
    option_quotes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    config = config or DiscoveryConfig()
    frame = normalize_bars(bars, config)
    features = compute_causal_features(
        frame, opening_range_bars=config.opening_range_bars
    )
    regimes = classify_deterministic_regimes(features)
    labels = compute_triple_barrier_labels(
        frame,
        features["atr_14"],
        horizon_bars=config.barrier_horizon_bars,
        target_atr=config.target_atr,
        stop_atr=config.stop_atr,
    )

    metadata = pd.DataFrame(index=frame.index)
    metadata["instrument"] = config.instrument
    metadata["session_date"] = frame["session_date"]
    metadata["decision_timestamp"] = frame["timestamp"]
    metadata["feature_cutoff_timestamp"] = frame["timestamp"]
    metadata["source_data_max_timestamp"] = frame["timestamp"]
    metadata["feature_schema_version"] = FEATURE_SCHEMA_VERSION
    metadata["label_schema_version"] = LABEL_SCHEMA_VERSION
    metadata["data_quality_status"] = _quality_status(frame)

    dataset = pd.concat([metadata, features, regimes, labels], axis=1)
    dataset = attach_option_outcome_availability(dataset, option_quotes)

    if not (
        dataset["source_data_max_timestamp"] <= dataset["decision_timestamp"]
    ).all():
        raise AssertionError("causal timestamp invariant violated")

    # Rows without the declared history or future horizon are retained in raw
    # construction but excluded from the model-ready output.
    minimum_index = config.minimum_history_bars - 1
    maximum_index = len(dataset) - config.barrier_horizon_bars - 1
    if maximum_index < minimum_index:
        raise ValueError("insufficient rows for configured history and label horizon")
    dataset = dataset.iloc[minimum_index : maximum_index + 1].copy()
    dataset.reset_index(drop=True, inplace=True)
    return dataset


def chronological_split(
    dataset: pd.DataFrame,
    *,
    validation_fraction: float = 0.2,
    holdout_fraction: float = 0.2,
) -> pd.DataFrame:
    if len(dataset) < 30:
        raise ValueError("at least 30 model-ready rows are required")
    ordered = dataset.sort_values("decision_timestamp", kind="mergesort").copy()
    n_rows = len(ordered)
    development_end = int(n_rows * (1.0 - validation_fraction - holdout_fraction))
    validation_end = int(n_rows * (1.0 - holdout_fraction))
    if not 0 < development_end < validation_end < n_rows:
        raise ValueError("invalid chronological partition")
    ordered["split"] = "HOLDOUT_LOCKED"
    ordered.iloc[:development_end, ordered.columns.get_loc("split")] = "DEVELOPMENT"
    ordered.iloc[
        development_end:validation_end, ordered.columns.get_loc("split")
    ] = "VALIDATION"
    ordered.reset_index(drop=True, inplace=True)
    return ordered


def model_feature_names(dataset: pd.DataFrame) -> tuple[str, ...]:
    candidates = feature_names_from_frame(dataset.columns)
    names: list[str] = []
    for name in candidates:
        if name in {"option_data_reason"}:
            continue
        if pd.api.types.is_numeric_dtype(dataset[name]):
            names.append(name)
    return tuple(names)


def semantic_dataset_hash(dataset: pd.DataFrame) -> str:
    canonical = dataset.copy()
    canonical = canonical.sort_values("decision_timestamp", kind="mergesort")
    for column in canonical.columns:
        if pd.api.types.is_datetime64_any_dtype(canonical[column]):
            canonical[column] = canonical[column].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    records = canonical.where(pd.notna(canonical), None).to_dict(orient="records")
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provenance_payload(config: DiscoveryConfig, dataset: pd.DataFrame) -> dict[str, object]:
    return {
        "config": asdict(config),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "rows": int(len(dataset)),
        "sessions": int(dataset["session_date"].nunique()),
        "start": str(dataset["decision_timestamp"].min()),
        "end": str(dataset["decision_timestamp"].max()),
        "semantic_hash": semantic_dataset_hash(dataset),
    }
