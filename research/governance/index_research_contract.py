"""Fail-closed offline research contracts for BANKNIFTY and SENSEX."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class ResearchOutcome(str, Enum):
    BLOCKED_DATA = "BLOCKED_DATA"
    NO_STRUCTURAL_EDGE_FOUND = "NO_STRUCTURAL_EDGE_FOUND"
    QUALIFIED = "QUALIFIED"


@dataclass(frozen=True)
class ResearchSpec:
    index: str
    target: str
    cutoff_ist: str
    dev_split: str
    oos_split: str
    candidate_families: tuple[str, ...]
    negative_controls: tuple[str, ...]
    multiple_testing: str

    def validate(self) -> None:
        if self.index not in {"BANKNIFTY", "SENSEX"}:
            raise ValueError("UNSUPPORTED_INDEX")
        if not self.target or not self.cutoff_ist or not self.dev_split or not self.oos_split:
            raise ValueError("RESEARCH_SPEC_INCOMPLETE")
        if not self.candidate_families or not self.negative_controls:
            raise ValueError("RESEARCH_CONTROLS_REQUIRED")
        if self.multiple_testing != "required":
            raise ValueError("MULTIPLE_TESTING_CONTROL_REQUIRED")


@dataclass(frozen=True)
class DiscoveryResult:
    index: str
    outcome: ResearchOutcome
    dataset_sha256: str | None = None
    candidate_sha: str | None = None
    evidence_sha256: str | None = None

    def validate(self) -> None:
        if self.index not in {"BANKNIFTY", "SENSEX"}:
            raise ValueError("UNSUPPORTED_INDEX")
        if self.outcome == ResearchOutcome.QUALIFIED:
            if not all((self.dataset_sha256, self.candidate_sha, self.evidence_sha256)):
                raise ValueError("QUALIFIED_RESULT_REQUIRES_PROVENANCE")
        elif self.outcome == ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND:
            if not self.evidence_sha256:
                raise ValueError("NO_EDGE_RESULT_REQUIRES_EVIDENCE")


def run_offline_discovery(spec: ResearchSpec, *, dataset: Sequence[Mapping[str, object]] | None) -> DiscoveryResult:
    """Return an honest blocked result when required source data is absent."""

    spec.validate()
    if not dataset:
        result = DiscoveryResult(spec.index, ResearchOutcome.BLOCKED_DATA)
        result.validate()
        return result
    raise ValueError("DISCOVERY_EXECUTION_REQUIRES_FROZEN_DATA_AND_PREDECLARED_RUN")
