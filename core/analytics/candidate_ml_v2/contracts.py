from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = "candidate_ml_v2"
SAFETY_CONTRACT = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": False,
}

FORBIDDEN_FEATURE_TOKENS = (
    "future",
    "target",
    "outcome",
    "mfe",
    "mae",
    "pnl",
    "profit",
    "loss",
    "exit",
    "resolution",
    "hit_target",
    "hit_sl",
    "label",
)

DEFAULT_REQUIRED_FEATURES = (
    "spread_pct",
    "quote_age_sec",
    "relative_volume",
    "distance_from_vwap_atr",
    "breadth_up_1",
    "breadth_down_1",
    "index_breadth_divergence",
    "option_return_1",
    "option_return_3",
    "minutes_to_expiry",
)


class PredictionStatus(str, Enum):
    VALID = "PREDICTION_VALID"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    FEATURES_INCOMPLETE = "FEATURES_INCOMPLETE"
    OUT_OF_DISTRIBUTION = "PREDICTION_OUT_OF_DISTRIBUTION"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    BELOW_VALUE_THRESHOLD = "BELOW_VALUE_THRESHOLD"


@dataclass(frozen=True)
class CandidateMLConfig:
    min_train_rows: int = 250
    min_validation_rows: int = 80
    min_strategy_rows: int = 250
    min_positive_rows: int = 30
    max_missing_ratio: float = 0.20
    ood_z_threshold: float = 5.0
    ensemble_disagreement_threshold: float = 0.25
    probability_floor: float = 0.50
    default_win_r: float = 1.5
    default_loss_r: float = 1.0
    cost_r: float = 0.10
    purge_rows: int = 5
    validation_fraction: float = 0.20
    calibration_fraction: float = 0.50
    random_state: int = 68742
    required_features: tuple[str, ...] = DEFAULT_REQUIRED_FEATURES

    def __post_init__(self) -> None:
        if self.min_train_rows < 20:
            raise ValueError("min_train_rows_too_small")
        if self.min_validation_rows < 20:
            raise ValueError("min_validation_rows_too_small")
        if not 0 < self.validation_fraction < 0.5:
            raise ValueError("validation_fraction_out_of_range")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction_out_of_range")
        if not 0 <= self.max_missing_ratio < 1:
            raise ValueError("max_missing_ratio_out_of_range")
        if self.purge_rows < 0:
            raise ValueError("purge_rows_negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidatePrediction:
    status: PredictionStatus
    probability: float | None
    raw_logistic_probability: float | None
    raw_tree_probability: float | None
    expected_value_r: float | None
    threshold_probability: float | None
    strategy_id: str
    model_scope: str
    reason_codes: tuple[str, ...] = ()
    top_positive_features: tuple[tuple[str, float], ...] = ()
    top_negative_features: tuple[tuple[str, float], ...] = ()
    missing_features: tuple[str, ...] = ()
    ood_features: tuple[str, ...] = ()
    safety: Mapping[str, bool] = field(default_factory=lambda: dict(SAFETY_CONTRACT))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["reason_codes"] = list(self.reason_codes)
        payload["top_positive_features"] = [list(item) for item in self.top_positive_features]
        payload["top_negative_features"] = [list(item) for item in self.top_negative_features]
        payload["missing_features"] = list(self.missing_features)
        payload["ood_features"] = list(self.ood_features)
        payload["safety"] = dict(self.safety)
        return payload
