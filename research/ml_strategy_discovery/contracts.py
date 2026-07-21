from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_SCHEMA_VERSION = "ml_strategy_discovery_features_v1"
LABEL_SCHEMA_VERSION = "ml_strategy_discovery_labels_v1"
CANDIDATE_SCHEMA_VERSION = "ml_strategy_candidate_v1"


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


@dataclass(frozen=True)
class DiscoveryConfig:
    instrument: str = "UNKNOWN"
    timestamp_column: str = "timestamp"
    opening_range_bars: int = 15
    minimum_history_bars: int = 63
    barrier_horizon_bars: int = 30
    target_atr: float = 1.2
    stop_atr: float = 0.6
    validation_fraction: float = 0.2
    holdout_fraction: float = 0.2
    random_seed: int = 42

    def __post_init__(self) -> None:
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
            raise ValueError("development partition must retain at least 40% of rows")


@dataclass(frozen=True)
class RuleCondition:
    feature: str
    operator: str
    threshold: float

    def __post_init__(self) -> None:
        if self.operator not in {"<=", ">"}:
            raise ValueError(f"unsupported operator: {self.operator}")


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
    status: str = "RESEARCH_CANDIDATE"
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.conditions:
            raise ValueError("candidate must contain at least one condition")
        if self.status != "RESEARCH_CANDIDATE":
            raise ValueError("discovery candidates must remain research-only")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["conditions"] = [asdict(condition) for condition in self.conditions]
        return payload


def feature_names_from_frame(columns: Iterable[str]) -> tuple[str, ...]:
    excluded = {
        "instrument",
        "session_date",
        "decision_timestamp",
        "feature_cutoff_timestamp",
        "source_data_max_timestamp",
        "feature_schema_version",
        "label_schema_version",
        "data_quality_status",
        "option_data_availability",
        "barrier_outcome",
        "bars_to_event",
        "mfe_atr",
        "mae_atr",
        "label_return_r",
        "future_close_return_atr",
        "split",
    }
    return tuple(column for column in columns if column not in excluded)


def require_columns(mapping: Mapping[str, Any], required: Iterable[str]) -> None:
    missing = [column for column in required if column not in mapping]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
