from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA_VERSION = "ml_strategy_discovery_v2_certified_repair_v1"
DEVELOPMENT = "DEVELOPMENT_V1"
VALIDATION_CONSUMED = "VALIDATION_V1_CONSUMED"
HOLDOUT_LOCKED = "HOLDOUT_V1_LOCKED"
FRESH_CONSUMED = "FRESH_CONFIRMATION_V2_CONSUMED_INVALID"
FRESH_LOCKED = "FRESH_CONFIRMATION_V2_LOCKED"

SAFETY_FIELDS: dict[str, bool] = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": False,
}

FORBIDDEN_EXACT = {
    "instrument",
    "session_date",
    "bar_start_timestamp",
    "bar_end_timestamp",
    "decision_timestamp",
    "feature_cutoff_timestamp",
    "source_data_max_timestamp",
    "timestamp",
    "timestamp_semantics",
    "bar_interval_minutes",
    "source_timezone",
    "source_kind",
    "source_logical_path",
    "source_sha256",
    "source_manifest_record_id",
    "feature_schema_version",
    "label_schema_version",
    "data_quality_status",
    "option_data_availability",
    "option_data_reason",
    "label_entry_semantics",
    "label_entry_price",
    "label_entry_timestamp",
    "label_terminal_timestamp",
    "barrier_outcome",
    "bars_to_event",
    "mfe_atr",
    "mae_atr",
    "label_return_r",
    "future_close_return_atr",
    "label_status",
    "label_side",
    "split",
    "v2_dataset",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "symbol",
}
FORBIDDEN_PREFIXES = (
    "label_",
    "future_",
    "target_",
    "outcome_",
    "source_",
    "option_",
    "terminal_",
)
FORBIDDEN_SUBSTRINGS = ("timestamp", "hash", "record_id")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def is_forbidden_feature(name: str) -> bool:
    lowered = name.lower().strip()
    return (
        lowered in FORBIDDEN_EXACT
        or lowered.startswith(FORBIDDEN_PREFIXES)
        or any(part in lowered for part in FORBIDDEN_SUBSTRINGS)
    )


def require_causal_features(columns: Iterable[str]) -> tuple[str, ...]:
    features = tuple(str(column) for column in columns)
    if not features:
        raise ValueError("at least one causal feature is required")
    forbidden = sorted({name for name in features if is_forbidden_feature(name)})
    if forbidden:
        raise ValueError(f"forbidden model features: {forbidden}")
    return features


@dataclass(frozen=True)
class StabilityConfig:
    outer_folds: int = 5
    inner_folds: int = 4
    embargo_sessions: int = 1
    min_rows: int = 100
    min_sessions: int = 30
    min_trade_bearing_fold_fraction: float = 0.70
    max_fold_positive_contribution: float = 0.40
    max_top5_positive_contribution: float = 0.50
    max_year_positive_contribution: float = 0.60
    max_regime_positive_contribution: float = 0.60
    max_imputed_selection_fraction: float = 0.30
    bootstrap_iterations: int = 1000
    permutation_iterations: int = 1000
    seed: int = 42

    def __post_init__(self) -> None:
        if self.outer_folds < 3 or self.inner_folds < 2:
            raise ValueError("nested folds require at least 3 outer and 2 inner folds")
        if self.embargo_sessions < 0:
            raise ValueError("embargo_sessions cannot be negative")
        if self.min_rows < 1 or self.min_sessions < 2:
            raise ValueError("support thresholds must be positive")
        for value in (
            self.min_trade_bearing_fold_fraction,
            self.max_fold_positive_contribution,
            self.max_top5_positive_contribution,
            self.max_year_positive_contribution,
            self.max_regime_positive_contribution,
            self.max_imputed_selection_fraction,
        ):
            if not 0 < value <= 1:
                raise ValueError("fraction thresholds must be in (0, 1]")
        if self.bootstrap_iterations < 100 or self.permutation_iterations < 100:
            raise ValueError("statistical iterations must be at least 100")
