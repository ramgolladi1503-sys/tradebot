from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_SCHEMA_VERSION = "ml_strategy_discovery_features_v2"
LABEL_SCHEMA_VERSION = "ml_strategy_discovery_labels_v2"
CANDIDATE_SCHEMA_VERSION = "ml_strategy_candidate_v2"


class BarrierOutcome(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"
    NEITHER = "NEITHER"
    AMBIGUOUS_SAME_BAR = "AMBIGUOUS_SAME_BAR"
    UNAVAILABLE = "UNAVAILABLE"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"


class TimestampSemantics(str, Enum):
    START = "START"
    END = "END"


@dataclass(frozen=True)
class DiscoveryConfig:
    instrument: str = "UNKNOWN"
    timestamp_column: str = "timestamp"
    timestamp_semantics: TimestampSemantics | str = TimestampSemantics.END
    source_timezone: str = "Asia/Kolkata"
    bar_interval_minutes: int = 1
    strict_bar_cadence: bool = False
    source_kind: str = "GENERIC_COMPLETED_BARS"
    opening_range_bars: int = 15
    minimum_history_bars: int = 63
    barrier_horizon_bars: int = 30
    target_atr: float = 1.2
    stop_atr: float = 0.6
    validation_fraction: float = 0.2
    holdout_fraction: float = 0.2
    random_seed: int = 42
    label_side: str = "LONG"

    def __post_init__(self) -> None:
        if not self.instrument.strip():
            raise ValueError("instrument is required")
        if not self.timestamp_column.strip():
            raise ValueError("timestamp_column is required")
        if not self.source_timezone.strip():
            raise ValueError("source_timezone is required")
        if self.normalized_timestamp_semantics not in TimestampSemantics:
            raise ValueError("timestamp_semantics must be START or END")
        if self.bar_interval_minutes < 1:
            raise ValueError("bar_interval_minutes must be positive")
        if self.opening_range_bars < 2:
            raise ValueError("opening_range_bars must be at least 2")
        if self.minimum_history_bars < 20:
            raise ValueError("minimum_history_bars must be at least 20")
        if self.barrier_horizon_bars < 1:
            raise ValueError("barrier_horizon_bars must be positive")
        if self.target_atr <= 0 or self.stop_atr <= 0:
            raise ValueError("barrier sizes must be positive")
        if not 0 < self.validation_fraction < 0.5:
            raise ValueError("validation_fraction must be in (0, 0.5)")
        if not 0 < self.holdout_fraction < 0.5:
            raise ValueError("holdout_fraction must be in (0, 0.5)")
        if self.validation_fraction + self.holdout_fraction >= 0.6:
            raise ValueError("development partition must retain at least 40% of sessions")
        if self.label_side.upper() not in {"LONG", "SHORT"}:
            raise ValueError("label_side must be LONG or SHORT")

    @property
    def normalized_timestamp_semantics(self) -> TimestampSemantics:
        value = (
            self.timestamp_semantics.value
            if isinstance(self.timestamp_semantics, TimestampSemantics)
            else str(self.timestamp_semantics).upper().strip()
        )
        return TimestampSemantics(value)


@dataclass(frozen=True)
class RuleCondition:
    feature: str
    operator: str
    threshold: float

    def __post_init__(self) -> None:
        if not self.feature.strip():
            raise ValueError("condition feature is required")
        if self.operator not in {"<=", ">"}:
            raise ValueError(f"unsupported operator: {self.operator}")


@dataclass(frozen=True)
class FeatureImputation:
    feature: str
    value: float


@dataclass(frozen=True)
class StrategyCandidate:
    candidate_id: str
    conditions: tuple[RuleCondition, ...]
    target_atr: float
    stop_atr: float
    maximum_holding_bars: int
    feature_schema_version: str
    label_schema_version: str
    discovery_start: str
    discovery_end: str
    discovery_rows: int
    discovery_sessions: int
    leaf_probability: float
    leaf_node_id: int = -1
    label_side: str = "LONG"
    source_dataset_hash: str = ""
    imputation_values: tuple[FeatureImputation, ...] = ()
    label_entry_semantics: str = "CURRENT_COMPLETED_BAR_CLOSE_FOR_RESEARCH_LABEL_ONLY"
    status: str = "RESEARCH_CANDIDATE"
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.conditions:
            raise ValueError("candidate must contain at least one condition")
        if self.status != "RESEARCH_CANDIDATE":
            raise ValueError("discovery candidates must remain research-only")
        if self.label_side.upper() not in {"LONG", "SHORT"}:
            raise ValueError("candidate label_side must be LONG or SHORT")
        if self.source_dataset_hash and (
            len(self.source_dataset_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.source_dataset_hash)
        ):
            raise ValueError("source_dataset_hash must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["conditions"] = [asdict(condition) for condition in self.conditions]
        payload["imputation_values"] = [
            asdict(imputation) for imputation in self.imputation_values
        ]
        return payload

    def imputation_map(self) -> dict[str, float]:
        return {item.feature: float(item.value) for item in self.imputation_values}


_METADATA_COLUMNS = {
    "instrument",
    "session_date",
    "bar_start_timestamp",
    "bar_end_timestamp",
    "decision_timestamp",
    "feature_cutoff_timestamp",
    "source_data_max_timestamp",
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
    "barrier_outcome",
    "bars_to_event",
    "mfe_atr",
    "mae_atr",
    "label_return_r",
    "future_close_return_atr",
    "label_status",
    "label_side",
    "split",
}


def feature_names_from_frame(columns: Iterable[str]) -> tuple[str, ...]:
    return tuple(column for column in columns if column not in _METADATA_COLUMNS)


def require_columns(mapping: Mapping[str, Any], required: Iterable[str]) -> None:
    missing = [column for column in required if column not in mapping]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
