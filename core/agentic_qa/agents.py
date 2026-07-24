from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import AuditReport
from .security import redact_secrets


class AdvisoryAgent(Protocol):
    def review(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AgentReviewOutcome:
    accepted: bool
    reason_code: str
    review: dict[str, Any]


_ALLOWED_KEYS = {
    "summary",
    "risk_categories",
    "recommended_next_tests",
    "evidence_citations",
    "uncertainties",
    "deterministic_verdict",
}


def validate_advisory_review(report: AuditReport, review: dict[str, Any]) -> AgentReviewOutcome:
    redacted = redact_secrets(review)
    unexpected = sorted(set(redacted) - _ALLOWED_KEYS)
    if unexpected:
        return AgentReviewOutcome(False, "UNEXPECTED_AGENT_FIELDS", {"unexpected": unexpected})
    proposed = str(redacted.get("deterministic_verdict") or "")
    if proposed != report.verdict.value:
        return AgentReviewOutcome(
            False,
            "AGENT_VERDICT_OVERRIDE_ATTEMPT",
            {"expected": report.verdict.value, "observed": proposed},
        )
    citations = redacted.get("evidence_citations")
    if not isinstance(citations, list) or not citations:
        return AgentReviewOutcome(False, "AGENT_CITATIONS_MISSING", {})
    valid_artifacts = {ref.artifact for control in report.controls for ref in control.evidence_refs}
    unresolved = [item for item in citations if not isinstance(item, str) or item not in valid_artifacts]
    if unresolved:
        return AgentReviewOutcome(False, "AGENT_CITATIONS_UNRESOLVED", {"unresolved": unresolved})
    if not isinstance(redacted.get("uncertainties"), list):
        return AgentReviewOutcome(False, "AGENT_UNCERTAINTY_MISSING", {})
    return AgentReviewOutcome(True, "AGENT_REVIEW_ACCEPTED", redacted)


class DeterministicCritic:
    """A non-LLM baseline used for regression and safe fallback."""

    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        hard_failures = list(payload.get("hard_failures") or [])
        warnings = list(payload.get("warnings") or [])
        citations = []
        for control in payload.get("controls") or []:
            for ref in control.get("evidence_refs") or []:
                artifact = ref.get("artifact")
                if artifact and artifact not in citations:
                    citations.append(artifact)
        return {
            "summary": "Deterministic audit review generated from supplied control results only.",
            "risk_categories": sorted({item.split(":", 1)[0] for item in hard_failures}),
            "recommended_next_tests": ["Resolve hard failures", "Rerun the frozen evidence audit"],
            "evidence_citations": citations[:10] or ["run_manifest.json"],
            "uncertainties": warnings,
            "deterministic_verdict": str(payload.get("verdict") or ""),
        }
