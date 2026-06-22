"""Explicit outcome contract for candidate probability and semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CandidateOutcomeContract:
    """Explicit outcome contract for candidate probability."""

    candidate_id: str
    strategy_name: str
    created_at: str
    entry_price: float
    candidate_status: str
    execution_ok: bool
    is_fallback: bool
    is_advisory: bool
    is_stale: bool
    is_recovered: bool
    confidence_score: float
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    prediction_event: Optional[str] = None
    prediction_horizon_minutes: Optional[int] = None
    valid_until: Optional[str] = None
    time_stop: Optional[str] = None
    cost_model: Optional[str] = None
    probability_target_before_stop: Optional[float] = None
    calibration_source: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_name": self.strategy_name,
            "created_at": self.created_at,
            "entry_price": self.entry_price,
            "candidate_status": self.candidate_status,
            "execution_ok": self.execution_ok,
            "is_fallback": self.is_fallback,
            "is_advisory": self.is_advisory,
            "is_stale": self.is_stale,
            "is_recovered": self.is_recovered,
            "confidence_score": self.confidence_score,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
            "prediction_event": self.prediction_event,
            "prediction_horizon_minutes": self.prediction_horizon_minutes,
            "valid_until": self.valid_until,
            "time_stop": self.time_stop,
            "cost_model": self.cost_model,
            "probability_target_before_stop": self.probability_target_before_stop,
            "calibration_source": self.calibration_source,
        }
