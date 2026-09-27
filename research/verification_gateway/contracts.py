"""Strict, research-only source-fidelity contract.

Does not execute strategies, read historical outcomes, write ledgers, select
candidates, grant certification, or interact with broker/runtime code.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    rule_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1, description="Page/section/video timestamp")
    exact_source_text_or_equation: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    is_author_rule: bool
    assumption_rationale: str | None = None

    @model_validator(mode="after")
    def explain_assumptions(self):
        if not self.is_author_rule and not self.assumption_rationale:
            raise ValueError("An inferred rule requires an explicit rationale")
        return self


class TimestampPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timezone: str = Field(min_length=1)
    signal_requires_complete_bar: bool
    earliest_entry_policy: Literal["NEXT_AVAILABLE_QUOTE", "NEXT_BAR_OPEN"]
    data_available_at: str = Field(min_length=1)


class ResearchStrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    research_id: str = Field(min_length=1)
    existing_registry_strategy_id: str | None = None
    source_uri_or_artifact_id: str = Field(min_length=1)
    source_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules: tuple[SourceRule, ...] = Field(min_length=1)
    indicator_equations: tuple[str, ...] = Field(min_length=1)
    instrument_and_contract_rule: str = Field(min_length=1)
    entry_rule: str = Field(min_length=1)
    exit_rule: str = Field(min_length=1)
    costs_and_fill_convention: str = Field(min_length=1)
    required_input_fields: tuple[str, ...] = Field(min_length=1)
    timing: TimestampPolicy
    source_review_status: Literal["REVIEW_REQUIRED", "INDEPENDENTLY_REVIEWED"]
    independent_reviewer_evidence: str | None = None

    @model_validator(mode="after")
    def require_review_evidence(self):
        if self.source_review_status == "INDEPENDENTLY_REVIEWED" and not self.independent_reviewer_evidence:
            raise ValueError("Independent review requires evidence")
        ids = [r.rule_id for r in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate source rule IDs")
        return self

    def content_digest(self) -> str:
        stable = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(stable.encode("utf-8")).hexdigest()


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    spec_sha256: str
    source_reviewed: bool
    reference_comparison_passed: bool
    causal_checks_passed: bool
    data_checks_passed: bool
    issues: tuple[str, ...] = ()

    @property
    def translation_verified(self) -> bool:
        return (self.source_reviewed and self.reference_comparison_passed
                and self.causal_checks_passed and self.data_checks_passed
                and not self.issues)


def check_causality(*, data_available: datetime, signal_decision: datetime,
                    first_permitted_entry: datetime) -> tuple[str, ...]:
    """Fail closed on naive timestamps and decisions/entries made too early."""
    stamps = (data_available, signal_decision, first_permitted_entry)
    if any(t.tzinfo is None or t.utcoffset() is None for t in stamps):
        return ("NAIVE_TIMESTAMP",)
    issues = []
    if signal_decision < data_available:
        issues.append("FUTURE_DATA_USED")
    if first_permitted_entry < signal_decision:
        issues.append("ENTRY_BEFORE_DECISION")
    return tuple(issues)


def verify_strategy_spec(
    spec: ResearchStrategySpec, *, reference_comparison_passed: bool,
    causal_checks_passed: bool, data_checks_passed: bool,
    issues: tuple[str, ...] = (),
) -> VerificationReport:
    """Aggregation only: explicit caller evidence required for each check.

    A positive result is engineering translation verification, never evidence
    of profitability, untouched OOS status, or authorization to backtest.
    """
    source_reviewed = bool(spec.source_review_status == "INDEPENDENTLY_REVIEWED"
                           and spec.independent_reviewer_evidence)
    if not source_reviewed:
        issues = (*issues, "SOURCE_REVIEW_NOT_VERIFIED")
    return VerificationReport(
        spec_sha256=spec.content_digest(), source_reviewed=source_reviewed,
        reference_comparison_passed=reference_comparison_passed,
        causal_checks_passed=causal_checks_passed,
        data_checks_passed=data_checks_passed, issues=issues,
    )
