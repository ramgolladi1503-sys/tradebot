from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .analytics import AnalyticsContractError, SessionAnalytics, build_session_analytics
from .contracts import CanonicalEvent, parse_timestamp
from .lineage import CandidateLineage, LineageError, build_candidate_lineage
from .outcomes import HorizonOutcome, OutcomeContractError, calculate_outcomes
from .quality import VALID, SessionManifest, validate_session
from .replay import ReplayConflictError, ReplayResult, assert_replay_deterministic


PIPELINE_CERTIFIED = "PIPELINE_OFFLINE_CERTIFIED"
PIPELINE_REJECTED = "PIPELINE_OFFLINE_REJECTED"


@dataclass(frozen=True, slots=True)
class CertificationCheck:
    check_id: str
    passed: bool
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SessionAnalysis:
    manifest: SessionManifest
    replay: ReplayResult | None
    lineage: tuple[CandidateLineage, ...]
    outcomes: tuple[HorizonOutcome, ...]
    analytics: SessionAnalytics
    errors: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CertificationResult:
    verdict: str
    pipeline_certified: bool
    strategy_edge_certified: bool
    strategy_edge_reason: str
    replay_hash: str
    manifest: SessionManifest
    lineage_count: int
    outcome_count: int
    checks: tuple[CertificationCheck, ...]
    analysis_errors: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "pipeline_certified": self.pipeline_certified,
            "strategy_edge_certified": self.strategy_edge_certified,
            "strategy_edge_reason": self.strategy_edge_reason,
            "replay_hash": self.replay_hash,
            "manifest": self.manifest.to_dict(),
            "lineage_count": self.lineage_count,
            "outcome_count": self.outcome_count,
            "checks": [check.to_dict() for check in self.checks],
            "analysis_errors": dict(self.analysis_errors),
        }


def analyze_session(events: Iterable[CanonicalEvent]) -> SessionAnalysis:
    """Run replay, lineage, and outcome analysis without allowing one bad stage to crash finalization."""

    materialized = tuple(events)
    manifest = validate_session(materialized)
    errors: dict[str, str] = {}
    replay_result: ReplayResult | None = None
    lineage: tuple[CandidateLineage, ...] = ()
    outcomes: tuple[HorizonOutcome, ...] = ()
    analytics = SessionAnalytics(metrics=(), required_metrics=(), missing_required_metrics=(), contract={})

    try:
        replay_result = assert_replay_deterministic(materialized)
    except (ReplayConflictError, AssertionError, ValueError) as exc:
        errors["replay"] = f"{type(exc).__name__}:{exc}"

    if replay_result is not None:
        try:
            lineage = build_candidate_lineage(replay_result.ordered_events)
        except (LineageError, ValueError) as exc:
            errors["lineage"] = f"{type(exc).__name__}:{exc}"

    if replay_result is not None and "lineage" not in errors:
        try:
            outcomes = calculate_outcomes(replay_result.ordered_events, lineage)
        except (OutcomeContractError, ValueError) as exc:
            errors["outcomes"] = f"{type(exc).__name__}:{exc}"

    if replay_result is not None and "lineage" not in errors and "outcomes" not in errors:
        try:
            analytics = build_session_analytics(replay_result.ordered_events, lineage, outcomes)
        except (AnalyticsContractError, ValueError) as exc:
            errors["analytics"] = f"{type(exc).__name__}:{exc}"

    return SessionAnalysis(
        manifest=manifest,
        replay=replay_result,
        lineage=lineage,
        outcomes=outcomes,
        analytics=analytics,
        errors=dict(sorted(errors.items())),
    )


def _outcome_time_integrity(outcomes: Iterable[HorizonOutcome]) -> tuple[bool, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    for outcome in outcomes:
        decision = parse_timestamp(outcome.decision_time, field_name="decision_time")
        label = parse_timestamp(outcome.label_available_time, field_name="label_available_time")
        elapsed = (label - decision).total_seconds()
        if elapsed < outcome.horizon_seconds:
            violations.append(
                {
                    "candidate_id": outcome.candidate_id,
                    "horizon_seconds": outcome.horizon_seconds,
                    "elapsed_seconds": elapsed,
                }
            )
    return not violations, violations


def certify_analysis(analysis: SessionAnalysis) -> CertificationResult:
    manifest = analysis.manifest
    lineage = analysis.lineage
    outcomes = analysis.outcomes
    outcome_time_ok, outcome_time_violations = _outcome_time_integrity(outcomes)

    candidates_with_contract = sum(1 for row in lineage if row.outcome_contract)
    candidates_with_outcomes = len({row.candidate_id for row in outcomes})
    candidate_contract_coverage_ok = (
        "lineage" not in analysis.errors
        and ((not lineage) or candidates_with_contract == len(lineage))
    )
    outcome_coverage_ok = (
        "outcomes" not in analysis.errors
        and candidates_with_contract == candidates_with_outcomes
    )
    incomplete_outcomes = [
        {
            "candidate_id": row.candidate_id,
            "horizon_seconds": row.horizon_seconds,
            "unavailable_reasons": list(row.unavailable_reasons),
        }
        for row in outcomes
        if row.unavailable_reasons
    ]
    outcome_evidence_complete = "outcomes" not in analysis.errors and not incomplete_outcomes
    replay_valid = analysis.replay is not None and "replay" not in analysis.errors
    lineage_valid = "lineage" not in analysis.errors
    outcome_calculation_valid = "outcomes" not in analysis.errors
    analytics_valid = "analytics" not in analysis.errors
    required_analytics_complete = analytics_valid and not analysis.analytics.missing_required_metrics

    checks = (
        CertificationCheck(
            check_id="SESSION_MANIFEST_VALID",
            passed=manifest.verdict == VALID,
            evidence={"verdict": manifest.verdict, "reason_codes": list(manifest.reason_codes)},
        ),
        CertificationCheck(
            check_id="DETERMINISTIC_REPLAY",
            passed=replay_valid,
            evidence={
                "event_count": analysis.replay.event_count if analysis.replay else 0,
                "hash": analysis.replay.deterministic_hash if analysis.replay else "",
                "error": analysis.errors.get("replay", ""),
            },
        ),
        CertificationCheck(
            check_id="LINEAGE_CALCULATION_VALID",
            passed=lineage_valid,
            evidence={"lineage_count": len(lineage), "error": analysis.errors.get("lineage", "")},
        ),
        CertificationCheck(
            check_id="OUTCOME_CALCULATION_VALID",
            passed=outcome_calculation_valid,
            evidence={"outcome_count": len(outcomes), "error": analysis.errors.get("outcomes", "")},
        ),
        CertificationCheck(
            check_id="ANALYTICS_CALCULATION_VALID",
            passed=analytics_valid,
            evidence={
                "metric_count": len(analysis.analytics.metrics),
                "error": analysis.errors.get("analytics", ""),
            },
        ),
        CertificationCheck(
            check_id="DECLARED_ANALYTICS_COMPLETE",
            passed=required_analytics_complete,
            evidence={
                "required_metrics": list(analysis.analytics.required_metrics),
                "missing_required_metrics": list(analysis.analytics.missing_required_metrics),
            },
        ),
        CertificationCheck(
            check_id="NO_LOOKAHEAD",
            passed=manifest.lookahead_violations == 0,
            evidence={"violations": manifest.lookahead_violations},
        ),
        CertificationCheck(
            check_id="OUTCOME_LABEL_TIME_INTEGRITY",
            passed=outcome_calculation_valid and outcome_time_ok,
            evidence={"violations": outcome_time_violations},
        ),
        CertificationCheck(
            check_id="CANDIDATE_OUTCOME_CONTRACT_COVERAGE",
            passed=candidate_contract_coverage_ok,
            evidence={
                "lineage_count": len(lineage),
                "candidates_with_contract": candidates_with_contract,
            },
        ),
        CertificationCheck(
            check_id="OUTCOME_CONTRACT_COVERAGE",
            passed=outcome_coverage_ok,
            evidence={
                "candidates_with_contract": candidates_with_contract,
                "candidates_with_outcomes": candidates_with_outcomes,
            },
        ),
        CertificationCheck(
            check_id="OUTCOME_EVIDENCE_COMPLETE",
            passed=outcome_evidence_complete,
            evidence={"incomplete_outcomes": incomplete_outcomes},
        ),
    )
    passed = all(check.passed for check in checks)
    return CertificationResult(
        verdict=PIPELINE_CERTIFIED if passed else PIPELINE_REJECTED,
        pipeline_certified=passed,
        strategy_edge_certified=False,
        strategy_edge_reason=(
            "Offline certification proves evidence, replay, lineage, and causal outcome integrity only. "
            "It does not prove profitability, fill calibration, capacity, holdout performance, or live edge."
        ),
        replay_hash=analysis.replay.deterministic_hash if analysis.replay else "",
        manifest=manifest,
        lineage_count=len(lineage),
        outcome_count=len(outcomes),
        checks=checks,
        analysis_errors=analysis.errors,
    )


def certify_session(events: Iterable[CanonicalEvent]) -> CertificationResult:
    return certify_analysis(analyze_session(events))
