from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Iterable


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class CASSessionObservation:
    trade_date: date
    session_id: str
    expiry_session: bool
    continuous_index: float
    final_index: float
    weighted_breadth: float | None
    top3_concentration: float | None
    futures_gap_to_final: float | None
    option_response_lag_seconds: float | None
    data_quality_state: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.session_id.strip() or not self.evidence_ref.strip():
            raise ValueError("cas_identity_missing")
        continuous = _finite(self.continuous_index, name="continuous_index")
        final = _finite(self.final_index, name="final_index")
        if continuous <= 0 or final <= 0:
            raise ValueError("cas_index_prices_must_be_positive")
        quality = self.data_quality_state.strip().upper()
        if not quality:
            raise ValueError("cas_data_quality_missing")
        for name in ("weighted_breadth", "top3_concentration", "futures_gap_to_final", "option_response_lag_seconds"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(value, name=name))
        if self.top3_concentration is not None and not 0 <= self.top3_concentration <= 1:
            raise ValueError("cas_top3_concentration_out_of_range")
        object.__setattr__(self, "continuous_index", continuous)
        object.__setattr__(self, "final_index", final)
        object.__setattr__(self, "data_quality_state", quality)

    @property
    def finalization_move(self) -> float:
        return self.final_index - self.continuous_index

    @property
    def finalization_return(self) -> float:
        return self.final_index / self.continuous_index - 1.0


@dataclass(frozen=True)
class CASCampaignSummary:
    valid_sessions: int
    invalid_sessions: int
    expiry_sessions: int
    non_expiry_sessions: int
    median_move: float | None
    median_absolute_move: float | None
    median_return: float | None
    positive_sessions: int
    negative_sessions: int
    zero_sessions: int
    ready_for_directional_testing: bool
    readiness_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {"valid_sessions": self.valid_sessions, "invalid_sessions": self.invalid_sessions, "expiry_sessions": self.expiry_sessions, "non_expiry_sessions": self.non_expiry_sessions, "median_move": self.median_move, "median_absolute_move": self.median_absolute_move, "median_return": self.median_return, "positive_sessions": self.positive_sessions, "negative_sessions": self.negative_sessions, "zero_sessions": self.zero_sessions, "ready_for_directional_testing": self.ready_for_directional_testing, "readiness_reasons": list(self.readiness_reasons), "evidence_refs": list(self.evidence_refs)}


def summarize_cas_campaign(observations: Iterable[CASSessionObservation], *, accepted_quality_states: set[str], minimum_expiry_sessions: int, minimum_non_expiry_sessions: int) -> CASCampaignSummary:
    rows = list(observations)
    if minimum_expiry_sessions < 0 or minimum_non_expiry_sessions < 0:
        raise ValueError("cas_minimum_sessions_negative")
    if not accepted_quality_states:
        raise ValueError("cas_accepted_quality_states_empty")
    normalized_states = {value.strip().upper() for value in accepted_quality_states}
    valid = [row for row in rows if row.data_quality_state in normalized_states]
    invalid = [row for row in rows if row.data_quality_state not in normalized_states]
    ids = [row.session_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_cas_session_id")
    expiry = [row for row in valid if row.expiry_session]
    non_expiry = [row for row in valid if not row.expiry_session]
    reasons: list[str] = []
    if len(expiry) < minimum_expiry_sessions: reasons.append("INSUFFICIENT_EXPIRY_SESSIONS")
    if len(non_expiry) < minimum_non_expiry_sessions: reasons.append("INSUFFICIENT_NON_EXPIRY_SESSIONS")
    moves = [row.finalization_move for row in valid]
    returns = [row.finalization_return for row in valid]
    return CASCampaignSummary(len(valid), len(invalid), len(expiry), len(non_expiry), median(moves) if moves else None, median(abs(value) for value in moves) if moves else None, median(returns) if returns else None, sum(value > 0 for value in moves), sum(value < 0 for value in moves), sum(value == 0 for value in moves), not reasons, tuple(reasons), tuple(sorted(row.evidence_ref for row in valid)))
