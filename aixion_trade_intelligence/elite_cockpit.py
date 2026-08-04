from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .evidence_guardian import EvidenceGuardianSummary
from .ranking_diagnostics import (
    EmpiricalMetricFinding,
    RankingStabilityReport,
    ScoreSeparationReport,
)


@dataclass(frozen=True)
class AuthorityGate:
    authority: str
    verdict: str
    passed: bool
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "verdict": self.verdict,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class EliteAnalyticsCockpit:
    observation: AuthorityGate
    diagnosis: AuthorityGate
    strategy_change: AuthorityGate
    profitability_claim: AuthorityGate
    ranking: dict[str, object]
    evidence: dict[str, object]
    session: dict[str, object]
    certification: dict[str, object]
    global_blockers: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "authorities": {
                "observation": self.observation.to_record(),
                "diagnosis": self.diagnosis.to_record(),
                "strategy_change": self.strategy_change.to_record(),
                "profitability_claim": self.profitability_claim.to_record(),
            },
            "ranking": dict(self.ranking),
            "evidence": dict(self.evidence),
            "session": dict(self.session),
            "certification": dict(self.certification),
            "global_blockers": list(self.global_blockers),
        }


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"elite_cockpit_{name}_missing")
    return value


def _empirical_findings_summary(findings: Iterable[EmpiricalMetricFinding]) -> dict[str, object]:
    rows = tuple(findings)
    outside = [row.metric for row in rows if row.verdict == "OUTSIDE_EMPIRICAL_BASELINE"]
    insufficient = [row.metric for row in rows if row.verdict == "INSUFFICIENT_REFERENCE_EVIDENCE"]
    return {
        "evaluated_metric_count": len(rows),
        "outside_empirical_baseline": sorted(outside),
        "insufficient_reference_evidence": sorted(insufficient),
        "all_within_empirical_baseline": bool(rows) and not outside and not insufficient,
        "findings": [row.to_record() for row in rows],
    }


def build_elite_analytics_cockpit(
    *,
    canary_readiness: Mapping[str, object],
    evidence_guardian: EvidenceGuardianSummary,
    session_analysis: Mapping[str, object],
    score_report: ScoreSeparationReport | None = None,
    ranking_stability: RankingStabilityReport | None = None,
    empirical_score_findings: Iterable[EmpiricalMetricFinding] = (),
    certification: Mapping[str, object] | None = None,
    evidence_refs: Iterable[str] = (),
) -> EliteAnalyticsCockpit:
    readiness = _mapping(canary_readiness, name="canary_readiness")
    manifest = _mapping(session_analysis.get("manifest"), name="session_manifest")
    outcome_readiness = _mapping(session_analysis.get("outcome_readiness"), name="outcome_readiness")
    certification_record = dict(certification or {})
    refs = tuple(sorted({str(value).strip() for value in evidence_refs if str(value).strip()}))

    observation_reasons: list[str] = []
    if not bool(readiness.get("ready")):
        observation_reasons.append("CANARY_READINESS_FAILED")
    if evidence_guardian.observation_authority != "READ_ONLY_OBSERVATION_ALLOWED":
        observation_reasons.extend(evidence_guardian.blockers)
    observation_passed = not observation_reasons
    observation_gate = AuthorityGate(
        authority="READ_ONLY_OBSERVATION",
        verdict="READ_ONLY_OBSERVATION_ALLOWED" if observation_passed else "READ_ONLY_OBSERVATION_BLOCKED",
        passed=observation_passed,
        reasons=tuple(observation_reasons or ["READINESS_AND_EVIDENCE_CONTINUITY_VALID"]),
        evidence_refs=refs,
    )

    empirical_summary = _empirical_findings_summary(empirical_score_findings)
    diagnosis_reasons: list[str] = []
    if not observation_passed:
        diagnosis_reasons.append("OBSERVATION_AUTHORITY_BLOCKED")
    if not bool(manifest.get("valid")):
        diagnosis_reasons.append("SESSION_EVIDENCE_INVALID")
    if not bool(outcome_readiness.get("ready_for_strategy_diagnosis")):
        diagnosis_reasons.append("CANDIDATE_OUTCOME_COVERAGE_INCOMPLETE")
    if score_report is None:
        diagnosis_reasons.append("RANKING_DIAGNOSTICS_MISSING")
    if empirical_summary["insufficient_reference_evidence"]:
        diagnosis_reasons.append("RANKING_BASELINE_INSUFFICIENT")
    diagnosis_passed = not diagnosis_reasons
    diagnosis_gate = AuthorityGate(
        authority="STRATEGY_DIAGNOSIS",
        verdict="STRATEGY_DIAGNOSIS_ALLOWED" if diagnosis_passed else "STRATEGY_DIAGNOSIS_BLOCKED",
        passed=diagnosis_passed,
        reasons=tuple(diagnosis_reasons or ["SESSION_OUTCOMES_AND_RANKING_EVIDENCE_COMPLETE"]),
        evidence_refs=refs,
    )

    strategy_change_reasons: list[str] = []
    if not diagnosis_passed:
        strategy_change_reasons.append("STRATEGY_DIAGNOSIS_NOT_AUTHORIZED")
    if empirical_summary["outside_empirical_baseline"]:
        strategy_change_reasons.append("RANKING_BEHAVIOR_OUTSIDE_EMPIRICAL_BASELINE")
    if not certification_record:
        strategy_change_reasons.append("CERTIFICATION_NOT_EVALUATED")
    strategy_change_passed = not strategy_change_reasons
    strategy_change_gate = AuthorityGate(
        authority="STRATEGY_CHANGE",
        verdict="HUMAN_STRATEGY_CHANGE_REVIEW_ALLOWED" if strategy_change_passed else "STRATEGY_CHANGE_BLOCKED",
        passed=strategy_change_passed,
        reasons=tuple(strategy_change_reasons or ["HUMAN_REVIEW_REQUIRED_NO_AUTOMATIC_MUTATION"]),
        evidence_refs=refs,
    )

    profitability_reasons: list[str] = []
    if not bool(outcome_readiness.get("ready_for_profitability_claim")):
        profitability_reasons.append("SESSION_NOT_READY_FOR_PROFITABILITY_CLAIM")
    certification_verdict = str(certification_record.get("verdict") or "NOT_EVALUATED")
    if certification_verdict != "READY_FOR_HUMAN_PROMOTION_REVIEW":
        profitability_reasons.append(f"CERTIFICATION_VERDICT={certification_verdict}")
    profitability_passed = not profitability_reasons
    profitability_gate = AuthorityGate(
        authority="PROFITABILITY_CLAIM",
        verdict="PROFITABILITY_CLAIM_REVIEW_ALLOWED" if profitability_passed else "PROFITABILITY_CLAIM_BLOCKED",
        passed=profitability_passed,
        reasons=tuple(profitability_reasons or ["HUMAN_PROMOTION_REVIEW_STILL_REQUIRED"]),
        evidence_refs=refs,
    )

    ranking_record: dict[str, object] = {
        "score_separation": score_report.to_record() if score_report else None,
        "ranking_stability": ranking_stability.to_record() if ranking_stability else None,
        "empirical_policy": empirical_summary,
    }
    session_record = {
        "session_id": manifest.get("session_id"),
        "run_id": manifest.get("run_id"),
        "verdict": manifest.get("verdict"),
        "valid": manifest.get("valid"),
        "ready_for_strategy_diagnosis": outcome_readiness.get("ready_for_strategy_diagnosis"),
        "ready_for_profitability_claim": outcome_readiness.get("ready_for_profitability_claim"),
        "outcome_readiness_reason": outcome_readiness.get("reason"),
    }
    global_blockers = tuple(
        dict.fromkeys(
            observation_reasons
            + diagnosis_reasons
            + strategy_change_reasons
            + profitability_reasons
        )
    )
    return EliteAnalyticsCockpit(
        observation=observation_gate,
        diagnosis=diagnosis_gate,
        strategy_change=strategy_change_gate,
        profitability_claim=profitability_gate,
        ranking=ranking_record,
        evidence=evidence_guardian.to_record(),
        session=session_record,
        certification=certification_record or {"verdict": "NOT_EVALUATED"},
        global_blockers=global_blockers,
    )
