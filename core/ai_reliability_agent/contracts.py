from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = 1


class AgentMode(str, Enum):
    LIVE_OBSERVE = "LIVE_OBSERVE"
    POST_MARKET_ANALYZE = "POST_MARKET_ANALYZE"
    REPAIR_PROPOSE = "REPAIR_PROPOSE"
    VERIFY = "VERIFY"


class Decision(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    NOT_EVALUATED = "NOT_EVALUATED"
    ERROR = "ERROR"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ClaimKind(str, Enum):
    DETERMINISTIC_FACT = "DETERMINISTIC_FACT"
    STATISTICAL_ASSOCIATION = "STATISTICAL_ASSOCIATION"
    LIKELY_CONTRIBUTOR = "LIKELY_CONTRIBUTOR"
    UNVERIFIED_HYPOTHESIS = "UNVERIFIED_HYPOTHESIS"


class FindingStatus(str, Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AgentActionType(str, Enum):
    TOOL = "TOOL"
    PROPOSE_FINDING = "PROPOSE_FINDING"
    STOP = "STOP"


class SessionVerdict(str, Enum):
    PIPELINE_TRUTHFUL_AND_OPERATIONAL = "PIPELINE_TRUTHFUL_AND_OPERATIONAL"
    PIPELINE_OPERATIONAL_BUT_OBSERVABILITY_INCOMPLETE = "PIPELINE_OPERATIONAL_BUT_OBSERVABILITY_INCOMPLETE"
    PIPELINE_SUPPRESSED_VALID_CANDIDATES = "PIPELINE_SUPPRESSED_VALID_CANDIDATES"
    PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES = "PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES"
    LIVE_SESSION_INVALID = "LIVE_SESSION_INVALID"


class CertificationLevel(str, Enum):
    NOT_CERTIFIED = "NOT_CERTIFIED"
    COMPONENT_CERTIFIED = "COMPONENT_CERTIFIED"
    SIMULATION_CERTIFIED = "SIMULATION_CERTIFIED"
    LIVE_CERTIFICATION_PENDING = "LIVE_CERTIFICATION_PENDING"
    LIVE_CERTIFIED = "LIVE_CERTIFIED"


class RejectionVerdict(str, Enum):
    CORRECT_REJECTION = "CORRECT_REJECTION"
    MISSED_OPPORTUNITY = "MISSED_OPPORTUNITY"
    NEUTRAL_REJECTION = "NEUTRAL_REJECTION"
    INVALID_REJECTION = "INVALID_REJECTION"
    UNVERIFIABLE = "UNVERIFIABLE"


class DecisionOutcomeClass(str, Enum):
    GOOD_DECISION_GOOD_OUTCOME = "GOOD_DECISION_GOOD_OUTCOME"
    GOOD_DECISION_BAD_OUTCOME = "GOOD_DECISION_BAD_OUTCOME"
    BAD_DECISION_GOOD_OUTCOME = "BAD_DECISION_GOOD_OUTCOME"
    BAD_DECISION_BAD_OUTCOME = "BAD_DECISION_BAD_OUTCOME"
    UNVERIFIABLE = "UNVERIFIABLE"


class OutcomeKind(str, Enum):
    TARGET = "TARGET"
    STOP = "STOP"
    TIME_EXIT = "TIME_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"
    NO_HIT = "NO_HIT"
    NOT_EXECUTED = "NOT_EXECUTED"
    UNKNOWN = "UNKNOWN"


class OutcomeScope(str, Enum):
    ACTUAL = "ACTUAL"
    HYPOTHETICAL = "HYPOTHETICAL"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    UNRESOLVED = "UNRESOLVED"


class FailureFactor(str, Enum):
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    LATE_ENTRY = "LATE_ENTRY"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    REGIME_TRANSITION = "REGIME_TRANSITION"
    PARTICIPATION_COLLAPSE = "PARTICIPATION_COLLAPSE"
    LEADERSHIP_REVERSAL = "LEADERSHIP_REVERSAL"
    OPTION_UNDERRESPONSE = "OPTION_UNDERRESPONSE"
    IV_CONTRACTION = "IV_CONTRACTION"
    THETA_DECAY = "THETA_DECAY"
    LIQUIDITY_DETERIORATION = "LIQUIDITY_DETERIORATION"
    EXCESSIVE_SLIPPAGE = "EXCESSIVE_SLIPPAGE"
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    TARGET_TOO_AMBITIOUS = "TARGET_TOO_AMBITIOUS"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    EXTERNAL_EVENT_SHOCK = "EXTERNAL_EVENT_SHOCK"
    NORMAL_VARIANCE = "NORMAL_VARIANCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    event_type: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Assertion:
    evidence_id: str
    path: str
    operator: str
    expected: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolRequest:
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "arguments": dict(self.arguments), "rationale": self.rationale}


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    success: bool
    payload: Mapping[str, Any]
    evidence_ref: EvidenceRef | None = None
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "payload": dict(self.payload),
            "evidence_ref": self.evidence_ref.to_dict() if self.evidence_ref else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class FindingProposal:
    title: str
    stage: str
    severity: Severity
    claim_kind: ClaimKind
    narrative: str
    assertions: tuple[Assertion, ...]
    evidence_ids: tuple[str, ...]
    business_effect: str = ""
    recommended_action: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "stage": self.stage,
            "severity": self.severity.value,
            "claim_kind": self.claim_kind.value,
            "narrative": self.narrative,
            "assertions": [item.to_dict() for item in self.assertions],
            "evidence_ids": list(self.evidence_ids),
            "business_effect": self.business_effect,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class VerificationResult:
    status: FindingStatus
    reasons: tuple[str, ...]
    evaluated_assertions: int
    passed_assertions: int
    contradictory_evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reasons": list(self.reasons),
            "evaluated_assertions": self.evaluated_assertions,
            "passed_assertions": self.passed_assertions,
            "contradictory_evidence_ids": list(self.contradictory_evidence_ids),
        }


@dataclass(frozen=True)
class Finding:
    finding_id: str
    session_id: str
    proposal: FindingProposal
    verification: VerificationResult
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "session_id": self.session_id,
            "proposal": self.proposal.to_dict(),
            "verification": self.verification.to_dict(),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class AgentAction:
    action_type: AgentActionType
    tool_request: ToolRequest | None = None
    finding: FindingProposal | None = None
    stop_reason: str = ""


@dataclass(frozen=True)
class Contributor:
    factor: FailureFactor
    claim_kind: ClaimKind
    confidence: float
    evidence: Mapping[str, Any]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor.value,
            "claim_kind": self.claim_kind.value,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class CandidateAutopsy:
    candidate_id: str
    strategy_name: str
    approved: bool
    executed: bool
    outcome: OutcomeKind
    outcome_scope: OutcomeScope
    decision_outcome_class: DecisionOutcomeClass
    rejection_verdict: RejectionVerdict | None
    observed_contributors: tuple[Contributor, ...]
    facts: Mapping[str, Any]
    evidence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_name": self.strategy_name,
            "approved": self.approved,
            "executed": self.executed,
            "outcome": self.outcome.value,
            "outcome_scope": self.outcome_scope.value,
            "decision_outcome_class": self.decision_outcome_class.value,
            "rejection_verdict": self.rejection_verdict.value if self.rejection_verdict else None,
            "observed_contributors": [item.to_dict() for item in self.observed_contributors],
            "facts": dict(self.facts),
            "evidence_ids": list(self.evidence_ids),
        }
