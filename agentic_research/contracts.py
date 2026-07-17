from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Verdict = Literal[
    "REJECTED_DATA_INELIGIBLE",
    "REJECTED_CONTRACT_MISMATCH",
    "REJECTED_CAUSAL_VIOLATION",
    "REJECTED_NO_EDGE",
    "REJECTED_OVERFIT",
    "REJECTED_EXECUTION_FRAGILE",
    "RESEARCH_GRADE_ONLY",
    "READY_FOR_OPTION_REPLAY",
    "READY_FOR_SHADOW",
]


class ResearchObjective(BaseModel):
    research_id: str = Field(min_length=3)
    strategy_id: str = "trend_pullback_v1"
    dataset_path: str
    target: str = "READY_FOR_OPTION_REPLAY"
    evidence_mode: Literal["STRUCTURAL_DATASET", "LEGACY_REPORT_AUDIT"] = "STRUCTURAL_DATASET"
    production_changes_allowed: bool = False
    live_trading_allowed: bool = False

    @model_validator(mode="after")
    def enforce_read_only(self) -> "ResearchObjective":
        if self.production_changes_allowed:
            raise ValueError("production_changes_forbidden")
        if self.live_trading_allowed:
            raise ValueError("live_trading_forbidden")
        return self


class ExperimentPlan(BaseModel):
    research_id: str
    strategy_id: str
    dataset_path: str
    evidence_mode: Literal["STRUCTURAL_DATASET", "LEGACY_REPORT_AUDIT"] = "STRUCTURAL_DATASET"
    experiments: list[str] = Field(default_factory=lambda: ["unchanged_production_baseline", "wfa"])
    maximum_strategy_variants: int = Field(default=1, ge=1, le=3)
    production_changes: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)

    @field_validator("experiments")
    @classmethod
    def experiments_are_bounded(cls, value: list[str]) -> list[str]:
        allowed = {
            "unchanged_production_baseline",
            "temporal_semantics",
            "wfa",
            "legacy_report_audit",
            "adversarial_review",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unapproved_experiments:{','.join(unknown)}")
        return value

    @model_validator(mode="after")
    def no_mutation(self) -> "ExperimentPlan":
        if self.production_changes:
            raise ValueError("production_changes_forbidden")
        return self


class ToolResult(BaseModel):
    tool: str
    status: Literal["SUCCESS", "REJECTED", "ERROR", "SKIPPED"]
    payload: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    artifact_path: str | None = None
    result_hash: str | None = None

    def with_hash(self) -> "ToolResult":
        body = self.model_dump(exclude={"result_hash"}, mode="json")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        return self.model_copy(update={"result_hash": digest})


class CriticFinding(BaseModel):
    code: str
    severity: Literal["INFO", "WARNING", "BLOCKER"]
    category: Literal["DATA", "CAUSALITY", "OVERFIT", "EXECUTION", "CONCENTRATION", "SECURITY", "OTHER"]
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None


class CriticReport(BaseModel):
    critic_id: str
    independent: bool = True
    findings: list[CriticFinding] = Field(default_factory=list)
    summary: str = ""
    source_result_hashes: dict[str, str] = Field(default_factory=dict)

    @property
    def blockers(self) -> list[CriticFinding]:
        return [finding for finding in self.findings if finding.severity == "BLOCKER"]


class CertificationDecision(BaseModel):
    verdict: Verdict
    passed: bool
    reasons: list[str]
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    promotion_ceiling: str = "READY_FOR_OPTION_REPLAY"


class HypothesisRecord(BaseModel):
    hypothesis_id: str
    strategy_id: str
    observed_failure: str
    economic_reasoning: str
    proposed_change: str
    changed_fields: list[str]
    rejection_condition: str
    dataset_hash: str
    status: Literal["PROPOSED", "APPROVED", "REJECTED", "COMPLETED"] = "PROPOSED"

    def fingerprint(self) -> str:
        payload = self.model_dump(exclude={"hypothesis_id", "status"}, mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class EvaluationCase(BaseModel):
    case_id: str
    category: str
    state: dict[str, Any]
    expected_action: str
    forbidden_actions: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    planner_name: str
    total_cases: int
    correct_cases: int
    unsafe_actions: int
    exceptions: int
    correct_action_rate: float
    unsafe_action_rate: float
    details: list[dict[str, Any]] = Field(default_factory=list)


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(f"config_not_json_and_pyyaml_unavailable:{path}") from exc
        value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"config_root_must_be_object:{path}")
    return value
