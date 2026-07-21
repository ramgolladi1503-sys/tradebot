from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,79}$")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _canonical(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        _aware(value, "datetime")
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical payload cannot contain NaN or infinity")
        return value
    return value


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON suitable for evidence hashing."""

    return json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SafetyEnvelope:
    """Mandatory fail-closed claims for every discovery artifact."""

    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    append: bool = False

    def validate(self) -> None:
        expected = {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        }
        actual = asdict(self)
        failures = [
            f"{key}={actual[key]!r}, expected {value!r}"
            for key, value in expected.items()
            if actual[key] != value
        ]
        if failures:
            raise ValueError("unsafe discovery envelope: " + "; ".join(failures))


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float
    available_at: datetime
    source: str

    def validate(self, decision_at: datetime) -> None:
        _aware(self.available_at, "feature.available_at")
        _aware(decision_at, "decision_at")
        if (
            not self.name
            or self.name.startswith("target_")
            or self.name.startswith("future_")
        ):
            raise ValueError(f"forbidden or empty feature name: {self.name!r}")
        if not self.source.strip():
            raise ValueError(f"feature {self.name!r} requires a source")
        if not math.isfinite(float(self.value)):
            raise ValueError(f"feature {self.name!r} must be finite")
        if self.available_at > decision_at:
            raise ValueError(
                f"feature {self.name!r} leaks future information: "
                f"available_at={self.available_at.isoformat()} "
                f"decision_at={decision_at.isoformat()}"
            )


@dataclass(frozen=True)
class DiscoveryObservation:
    observation_id: str
    instrument: str
    session_id: str
    decision_at: datetime
    features: Mapping[str, FeatureValue]

    def validate(self) -> None:
        _aware(self.decision_at, "decision_at")
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if not self.instrument.strip():
            raise ValueError("instrument is required")
        if not self.session_id.strip():
            raise ValueError("session_id is required")
        if not self.features:
            raise ValueError("at least one feature is required")
        for key, feature in self.features.items():
            if key != feature.name:
                raise ValueError(
                    f"feature mapping key {key!r} does not match "
                    f"feature name {feature.name!r}"
                )
            feature.validate(self.decision_at)

    @property
    def evidence_hash(self) -> str:
        self.validate()
        return semantic_hash(self)


@dataclass(frozen=True)
class BarrierSpec:
    target_distance: float
    stop_distance: float
    max_holding_bars: int

    def validate(self) -> None:
        if not math.isfinite(self.target_distance) or self.target_distance <= 0:
            raise ValueError("target_distance must be positive and finite")
        if not math.isfinite(self.stop_distance) or self.stop_distance <= 0:
            raise ValueError("stop_distance must be positive and finite")
        if self.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be at least 1")


class CandidateStatus(str, Enum):
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    VALIDATION_READY = "VALIDATION_READY"
    REJECTED = "REJECTED"
    HOLDOUT_CERTIFIED = "HOLDOUT_CERTIFIED"
    SHADOW_ONLY = "SHADOW_ONLY"


@dataclass(frozen=True)
class CandidateStrategySpec:
    candidate_id: str
    family: str
    hypothesis: str
    regime_conditions: tuple[str, ...]
    event_sequence: tuple[str, ...]
    entry_rule: str
    invalidation_rule: str
    exit_rule: str
    maximum_holding_minutes: int
    development_observations: int
    development_sessions: int
    source_dataset_hash: str
    status: CandidateStatus = CandidateStatus.RESEARCH_CANDIDATE
    discovery_metrics: Mapping[str, float] = field(default_factory=dict)
    safety: SafetyEnvelope = field(default_factory=SafetyEnvelope)

    def validate(self) -> None:
        self.safety.validate()
        if not _CANDIDATE_ID.match(self.candidate_id):
            raise ValueError(
                "candidate_id must be 3-80 lowercase letters, digits, "
                "underscores, or hyphens"
            )
        required_text = {
            "family": self.family,
            "hypothesis": self.hypothesis,
            "entry_rule": self.entry_rule,
            "invalidation_rule": self.invalidation_rule,
            "exit_rule": self.exit_rule,
            "source_dataset_hash": self.source_dataset_hash,
        }
        for name, value in required_text.items():
            if not value.strip():
                raise ValueError(f"{name} is required")
        if (
            len(self.source_dataset_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_dataset_hash
            )
        ):
            raise ValueError(
                "source_dataset_hash must be a lowercase SHA-256 hex digest"
            )
        if not self.event_sequence:
            raise ValueError("event_sequence cannot be empty")
        if self.maximum_holding_minutes < 1:
            raise ValueError("maximum_holding_minutes must be at least 1")
        if self.development_observations < 1 or self.development_sessions < 1:
            raise ValueError("development support must be positive")
        for name, value in self.discovery_metrics.items():
            if not name.strip() or not math.isfinite(float(value)):
                raise ValueError(
                    "discovery_metrics must contain named finite values"
                )

    @property
    def evidence_hash(self) -> str:
        self.validate()
        return semantic_hash(self)
