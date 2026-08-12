"""Governed incremental extended-global research decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExtendedDecision(str, Enum):
    KEEP = "KEEP"
    DISCARD = "DISCARD"
    BLOCKED_DATA = "BLOCKED_DATA"


@dataclass(frozen=True)
class ExtendedHypothesis:
    hypothesis_id: str
    source: str
    rationale: str
    predeclared: bool
    v1_model_sha256: str

    def validate(self) -> None:
        if not self.hypothesis_id or not self.source or not self.rationale:
            raise ValueError("EXTENDED_HYPOTHESIS_INCOMPLETE")
        if not self.predeclared:
            raise ValueError("EXTENDED_HYPOTHESIS_NOT_PREDECLARED")
        if len(self.v1_model_sha256) != 64:
            raise ValueError("V1_MODEL_BINDING_REQUIRED")


def decide(hypothesis: ExtendedHypothesis, *, evidence_available: bool, incremental_support: bool | None) -> ExtendedDecision:
    hypothesis.validate()
    if not evidence_available or incremental_support is None:
        return ExtendedDecision.BLOCKED_DATA
    return ExtendedDecision.KEEP if incremental_support else ExtendedDecision.DISCARD
