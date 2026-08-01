from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .contracts import FORBIDDEN_FEATURE_TOKENS, SAFETY_CONTRACT, SCHEMA_VERSION, CandidateMLConfig


def text(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if not math.isfinite(out):
            return None
        return out
    except Exception:
        return None


def coerce_epoch_ms(value: Any) -> int | None:
    try:
        if value is None:
            return None
        raw = float(value)
        if not math.isfinite(raw) or raw <= 0:
            return None
        if raw < 10_000_000_000:
            raw *= 1000
        return int(raw)
    except Exception:
        return None


def _find_forbidden_metric_keys(prefix: str, value: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(value, Mapping):
        return out
    for key, nested in value.items():
        name = f"{prefix}_{key}" if prefix else str(key)
        normalized = name.strip("_").lower()
        if any(token in normalized for token in FORBIDDEN_FEATURE_TOKENS):
            out.append(normalized)
        if isinstance(nested, Mapping):
            out.extend(_find_forbidden_metric_keys(name, nested))
    return sorted(set(out))


def _flatten_numeric(prefix: str, value: Any, out: dict[str, float]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            name = f"{prefix}_{key}" if prefix else str(key)
            _flatten_numeric(name, nested, out)
        return
    numeric = safe_float(value)
    if numeric is None:
        return
    normalized = prefix.strip("_").lower()
    if not normalized or any(token in normalized for token in FORBIDDEN_FEATURE_TOKENS):
        return
    out[normalized] = numeric


def build_candidate_row(
    event: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    friction_r: float = 0.10,
) -> dict[str, Any]:
    event_ts = coerce_epoch_ms(event.get("ts_epoch_ms") or event.get("timestamp_epoch_ms") or event.get("ts_epoch"))
    trade_outcome = outcome.get("trade_outcome") if isinstance(outcome.get("trade_outcome"), Mapping) else outcome
    outcome_ts = coerce_epoch_ms(
        outcome.get("resolution_ts_epoch_ms")
        or outcome.get("ts_epoch_ms")
        or trade_outcome.get("ts_epoch_ms")
    )
    if event_ts is None:
        raise ValueError("candidate_event_timestamp_missing")
    if outcome_ts is None:
        raise ValueError("candidate_outcome_timestamp_missing")
    if outcome_ts < event_ts:
        raise ValueError("candidate_outcome_precedes_event")

    metrics_snapshot = event.get("metrics_snapshot") or {}
    forbidden_metric_keys = _find_forbidden_metric_keys("", metrics_snapshot)
    if forbidden_metric_keys:
        raise ValueError(f"forbidden_future_feature:{','.join(forbidden_metric_keys)}")

    metrics: dict[str, float] = {}
    _flatten_numeric("", metrics_snapshot, metrics)
    for key in ("strike", "quote_age_sec", "spread_pct", "entry_price"):
        value = safe_float(event.get(key))
        if value is not None:
            metrics[key] = value

    outcome_label = text(trade_outcome.get("outcome") or outcome.get("outcome")).lower()
    exec_feasible = bool(trade_outcome.get("exec_feasible", outcome.get("exec_feasible", False)))
    target_hit = int(outcome_label == "hit_target" and exec_feasible)
    stop_hit = int(outcome_label == "hit_sl" and exec_feasible)
    mfe = safe_float(trade_outcome.get("mfe_points") or outcome.get("mfe_points"))
    mae = safe_float(trade_outcome.get("mae_points") or outcome.get("mae_points"))

    entry = safe_float(event.get("entry_price"))
    target = safe_float(event.get("target_price"))
    stop = safe_float(event.get("stop_price"))
    reward_points = abs(target - entry) if entry is not None and target is not None else None
    risk_points = abs(entry - stop) if entry is not None and stop is not None else None
    reward_r = reward_points / risk_points if reward_points is not None and risk_points not in (None, 0) else 1.5
    outcome_r = reward_r - friction_r if target_hit else (-1.0 - friction_r if stop_hit else -friction_r)

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": text(event.get("event_id")),
        "trade_key": text(event.get("trade_key")),
        "strategy_id": text(event.get("strategy_id") or event.get("strategy") or "UNKNOWN").upper(),
        "symbol": text(event.get("symbol")).upper(),
        "option_type": text(event.get("option_type")).upper(),
        "decision_ts_epoch_ms": event_ts,
        "feature_cutoff_ts_epoch_ms": event_ts,
        "outcome_ts_epoch_ms": outcome_ts,
        "session_date": datetime.fromtimestamp(event_ts / 1000.0, tz=timezone.utc).date().isoformat(),
        "target": target_hit,
        "stop_hit": stop_hit,
        "exec_feasible": int(exec_feasible),
        "future_mfe_points": mfe,
        "future_mae_points": mae,
        "future_net_r": float(outcome_r),
        "friction_r": float(friction_r),
        **metrics,
        **SAFETY_CONTRACT,
    }


def build_candidate_dataset(
    events: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    *,
    friction_r: float = 0.10,
) -> pd.DataFrame:
    by_event: dict[str, Mapping[str, Any]] = {}
    by_trade: dict[str, Mapping[str, Any]] = {}
    for outcome in outcomes:
        event_ref = text(outcome.get("event_ref_id") or outcome.get("event_id"))
        trade_key = text(outcome.get("trade_key") or (outcome.get("trade_outcome") or {}).get("trade_key"))
        if event_ref:
            by_event[event_ref] = outcome
        if trade_key:
            by_trade[trade_key] = outcome

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for event in events:
        event_id = text(event.get("event_id"))
        trade_key = text(event.get("trade_key"))
        outcome = by_event.get(event_id) or by_trade.get(trade_key)
        if outcome is None:
            continue
        row = build_candidate_row(event, outcome, friction_r=friction_r)
        key = (row["event_id"] or row["trade_key"], int(row["decision_ts_epoch_ms"]))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["decision_ts_epoch_ms", "event_id"], kind="stable").reset_index(drop=True)
    validate_candidate_dataset(df)
    return df


def validate_candidate_dataset(df: pd.DataFrame) -> None:
    required = {
        "decision_ts_epoch_ms",
        "feature_cutoff_ts_epoch_ms",
        "outcome_ts_epoch_ms",
        "target",
        "strategy_id",
        "session_date",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"candidate_dataset_missing_columns:{','.join(missing)}")
    if df.empty:
        raise ValueError("candidate_dataset_empty")
    if not df["decision_ts_epoch_ms"].is_monotonic_increasing:
        raise ValueError("candidate_dataset_not_chronological")
    if (df["feature_cutoff_ts_epoch_ms"] > df["decision_ts_epoch_ms"]).any():
        raise ValueError("candidate_feature_cutoff_after_decision")
    if (df["outcome_ts_epoch_ms"] < df["decision_ts_epoch_ms"]).any():
        raise ValueError("candidate_outcome_before_decision")
    allowed_future_columns = {"future_mfe_points", "future_mae_points", "future_net_r", "outcome_ts_epoch_ms", "target"}
    forbidden = [
        column
        for column in df.columns
        if column not in allowed_future_columns and any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    if forbidden:
        raise ValueError(f"candidate_dataset_forbidden_columns:{','.join(sorted(forbidden))}")


def feature_columns(df: pd.DataFrame) -> list[str]:
    excluded = {
        "schema_version", "event_id", "trade_key", "strategy_id", "symbol", "option_type", "session_date",
        "decision_ts_epoch_ms", "feature_cutoff_ts_epoch_ms", "outcome_ts_epoch_ms", "target", "stop_hit",
        "exec_feasible", "future_mfe_points", "future_mae_points", "future_net_r", "friction_r",
        *SAFETY_CONTRACT.keys(),
    }
    return sorted(
        column
        for column in df.columns
        if column not in excluded
        and not any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)
        and pd.api.types.is_numeric_dtype(df[column])
    )


def chronological_split(df: pd.DataFrame, config: CandidateMLConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_candidate_dataset(df)
    sessions = list(dict.fromkeys(df["session_date"].astype(str).tolist()))
    if len(sessions) < 5:
        raise ValueError("candidate_dataset_too_few_sessions")
    validation_sessions = max(1, int(math.ceil(len(sessions) * config.validation_fraction)))
    train = df[df["session_date"].astype(str).isin(set(sessions[:-validation_sessions]))].copy()
    validation = df[df["session_date"].astype(str).isin(set(sessions[-validation_sessions:]))].copy()
    if config.purge_rows:
        train = train.iloc[: max(0, len(train) - config.purge_rows)].copy()
    if len(train) < config.min_train_rows:
        raise ValueError("candidate_training_support_below_minimum")
    if len(validation) < config.min_validation_rows:
        raise ValueError("candidate_validation_support_below_minimum")
    return train, validation


def purged_walk_forward_splits(
    df: pd.DataFrame,
    *,
    n_splits: int = 5,
    purge_rows: int = 5,
    min_train_sessions: int = 3,
) -> list[tuple[np.ndarray, np.ndarray]]:
    validate_candidate_dataset(df)
    sessions = list(dict.fromkeys(df["session_date"].astype(str).tolist()))
    if len(sessions) < min_train_sessions + n_splits:
        raise ValueError("insufficient_sessions_for_walk_forward")
    blocks = np.array_split(np.asarray(sessions[min_train_sessions:], dtype=object), n_splits)
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for block in blocks:
        if len(block) == 0:
            continue
        first_test = sessions.index(str(block[0]))
        train_idx = np.flatnonzero(df["session_date"].astype(str).isin(set(sessions[:first_test])).to_numpy())
        test_idx = np.flatnonzero(df["session_date"].astype(str).isin(set(str(item) for item in block)).to_numpy())
        if purge_rows and len(train_idx):
            train_idx = train_idx[: max(0, len(train_idx) - purge_rows)]
        if len(train_idx) and len(test_idx):
            splits.append((train_idx, test_idx))
    if not splits:
        raise ValueError("no_valid_walk_forward_splits")
    return splits


def semantic_dataset_hash(df: pd.DataFrame) -> str:
    ordered = df.sort_values(["decision_ts_epoch_ms", "event_id"], kind="stable")
    payload = ordered.to_json(orient="records", date_format="iso", double_precision=12)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
