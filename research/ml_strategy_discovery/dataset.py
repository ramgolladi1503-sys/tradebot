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
    TimestampSemantics,
    feature_names_from_frame,
)
from .features import compute_causal_features
from .labels import attach_option_outcome_availability, compute_triple_barrier_labels
from .regimes import classify_deterministic_regimes

_REQUIRED_BAR_COLUMNS = {"open", "high", "low", "close", "volume"}
_SOURCE_PROVENANCE_COLUMNS = (
    "source_logical_path",
    "source_sha256",
    "source_manifest_record_id",
)


def _source_timestamps_local(
    values: pd.Series,
    *,
    source_timezone: str,
) -> pd.Series:
    parsed = pd.to_datetime(values, errors="raise")
    timezone = getattr(parsed.dt, "tz", None)
    if timezone is None:
        return parsed.dt.tz_localize(
            source_timezone,
            ambiguous="raise",
            nonexistent="raise",
        )
    return parsed.dt.tz_convert(source_timezone)


def normalize_bars(bars: pd.DataFrame, config: DiscoveryConfig) -> pd.DataFrame:
    missing = _REQUIRED_BAR_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    if config.timestamp_column not in bars.columns:
        raise ValueError(f"missing timestamp column: {config.timestamp_column}")

    frame = bars.copy()
    source_local = _source_timestamps_local(
        frame[config.timestamp_column],
        source_timezone=config.source_timezone,
    )
    interval = pd.Timedelta(minutes=config.bar_interval_minutes)
    if config.normalized_timestamp_semantics is TimestampSemantics.START:
        bar_start_local = source_local
        bar_end_local = source_local + interval
    else:
        bar_end_local = source_local
        bar_start_local = source_local - interval

    frame["bar_start_timestamp"] = bar_start_local.dt.tz_convert("UTC")
    frame["bar_end_timestamp"] = bar_end_local.dt.tz_convert("UTC")
    frame["timestamp"] = frame["bar_end_timestamp"]
    frame["session_date"] = bar_start_local.dt.date.astype(str)

    if frame["bar_start_timestamp"].duplicated().any():
        duplicates = frame.loc[
            frame["bar_start_timestamp"].duplicated(), "bar_start_timestamp"
        ].astype(str).tolist()
        raise ValueError(f"duplicate timestamps fail closed: {duplicates[:5]}")
    frame = frame.sort_values("bar_start_timestamp", kind="mergesort").reset_index(
        drop=True
    )

    for column in _REQUIRED_BAR_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    numeric = frame[list(_REQUIRED_BAR_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("OHLCV values must be finite")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (frame["volume"] < 0).any():
        raise ValueError("volume cannot be negative")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high violates OHLC ordering")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low violates OHLC ordering")

    if config.strict_bar_cadence:
        expected = pd.Timedelta(minutes=config.bar_interval_minutes)
        deltas = frame.groupby("session_date")["bar_start_timestamp"].diff().dropna()
        if not (deltas == expected).all():
            sample = deltas.loc[deltas != expected].astype(str).head(5).tolist()
            raise ValueError(
                "strict bar cadence violated: "
                f"expected={expected} observed_samples={sample}"
            )
    return frame


def _quality_status(frame: pd.DataFrame, config: DiscoveryConfig) -> pd.Series:
    deltas = frame.groupby("session_date")["bar_start_timestamp"].diff()
    expected = pd.Timedelta(minutes=config.bar_interval_minutes)
    status = pd.Series("OK", index=frame.index)
    status.loc[deltas.notna() & (deltas != expected)] = (
        "MISSING_OR_IRREGULAR_INTERVAL_BEFORE_DECISION"
    )
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
        side=config.label_side,
    )

    metadata = pd.DataFrame(index=frame.index)
    metadata["instrument"] = config.instrument
    metadata["session_date"] = frame["session_date"]
    metadata["bar_start_timestamp"] = frame["bar_start_timestamp"]
    metadata["bar_end_timestamp"] = frame["bar_end_timestamp"]
    metadata["decision_timestamp"] = frame["bar_end_timestamp"]
    metadata["feature_cutoff_timestamp"] = frame["bar_end_timestamp"]
    metadata["source_data_max_timestamp"] = frame["bar_end_timestamp"]
    metadata["timestamp_semantics"] = config.normalized_timestamp_semantics.value
    metadata["bar_interval_minutes"] = config.bar_interval_minutes
    metadata["source_timezone"] = config.source_timezone
    metadata["source_kind"] = config.source_kind
    for column in _SOURCE_PROVENANCE_COLUMNS:
        metadata[column] = frame[column] if column in frame.columns else ""
    metadata["feature_schema_version"] = FEATURE_SCHEMA_VERSION
    metadata["label_schema_version"] = LABEL_SCHEMA_VERSION
    metadata["data_quality_status"] = _quality_status(frame, config)

    dataset = pd.concat([metadata, features, regimes, labels], axis=1)
    dataset = attach_option_outcome_availability(dataset, option_quotes)

    if not (
        dataset["source_data_max_timestamp"] <= dataset["decision_timestamp"]
    ).all():
        raise AssertionError("causal timestamp invariant violated")
    if not (
        dataset["bar_start_timestamp"] < dataset["bar_end_timestamp"]
    ).all():
        raise AssertionError("bar interval ordering invariant violated")

    minimum_index = config.minimum_history_bars - 1
    if len(dataset) <= minimum_index:
        raise ValueError("insufficient rows for configured history")
    dataset = dataset.iloc[minimum_index:].copy()
    dataset = dataset.loc[dataset["label_status"] == "MEASURED"].copy()
    if dataset.empty:
        raise ValueError("no rows have a complete same-session label horizon")
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
    sessions = (
        ordered.groupby("session_date", sort=False)["decision_timestamp"]
        .min()
        .sort_values(kind="mergesort")
        .index.tolist()
    )
    if len(sessions) < 5:
        raise ValueError("at least five complete sessions are required")
    development_end = int(
        len(sessions) * (1.0 - validation_fraction - holdout_fraction)
    )
    validation_end = int(len(sessions) * (1.0 - holdout_fraction))
    if not 0 < development_end < validation_end < len(sessions):
        raise ValueError("invalid chronological session partition")
    split_by_session = {
        session: "DEVELOPMENT" for session in sessions[:development_end]
    }
    split_by_session.update(
        {
            session: "VALIDATION"
            for session in sessions[development_end:validation_end]
        }
    )
    split_by_session.update(
        {session: "HOLDOUT_LOCKED" for session in sessions[validation_end:]}
    )
    ordered["split"] = ordered["session_date"].map(split_by_session)
    ordered.reset_index(drop=True, inplace=True)
    return ordered


def model_feature_names(dataset: pd.DataFrame) -> tuple[str, ...]:
    candidates = feature_names_from_frame(dataset.columns)
    return tuple(
        name
        for name in candidates
        if name in dataset.columns and pd.api.types.is_numeric_dtype(dataset[name])
    )


def semantic_dataset_hash(dataset: pd.DataFrame) -> str:
    canonical = dataset.copy()
    canonical = canonical.sort_values("decision_timestamp", kind="mergesort")
    for column in canonical.columns:
        if pd.api.types.is_datetime64_any_dtype(canonical[column]):
            canonical[column] = canonical[column].dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
    records = canonical.where(pd.notna(canonical), None).to_dict(orient="records")
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provenance_payload(config: DiscoveryConfig, dataset: pd.DataFrame) -> dict[str, object]:
    config_payload = asdict(config)
    config_payload["timestamp_semantics"] = (
        config.normalized_timestamp_semantics.value
    )
    return {
        "config": config_payload,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "rows": int(len(dataset)),
        "sessions": int(dataset["session_date"].nunique()),
        "start": str(dataset["decision_timestamp"].min()),
        "end": str(dataset["decision_timestamp"].max()),
        "source_kind": config.source_kind,
        "source_record_count": int(
            dataset["source_manifest_record_id"].replace("", np.nan).nunique()
        ),
        "semantic_hash": semantic_dataset_hash(dataset),
    }
