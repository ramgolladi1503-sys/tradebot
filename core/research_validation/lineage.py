from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from core.research_registry.experiment_validator import ExperimentValidator
from core.research_registry.research_models import ResearchExperiment

from .policy import CertificationInput, CertificationVerdict, certify_research


@dataclass(frozen=True)
class LineageAudit:
    passed: bool
    registered_experiments: int
    reasons: tuple[str, ...]


def audit_experiment_lineage(
    experiments: Iterable[ResearchExperiment],
    *,
    hypothesis_id: str,
) -> LineageAudit:
    """Audit immutable experiment lineage before statistical certification."""
    rows = list(experiments)
    reasons: list[str] = []
    if not hypothesis_id.strip():
        reasons.append("MISSING_HYPOTHESIS_ID")
    if not rows:
        reasons.append("MISSING_EXPERIMENT_HISTORY")

    experiment_ids: set[str] = set()
    for experiment in rows:
        if not experiment.experiment_id.strip():
            reasons.append("MISSING_EXPERIMENT_ID")
        elif experiment.experiment_id in experiment_ids:
            reasons.append("DUPLICATE_EXPERIMENT_ID")
        experiment_ids.add(experiment.experiment_id)

        if experiment.parent_hypothesis_id != hypothesis_id:
            reasons.append("PARENT_HYPOTHESIS_MISMATCH")
        if not experiment.versions:
            reasons.append("EXPERIMENT_WITHOUT_VERSION")
            continue

        previous_timestamp = None
        previous_version = None
        local_version_ids: set[str] = set()
        for version in experiment.versions:
            if not version.version_id.strip():
                reasons.append("MISSING_VERSION_ID")
            elif version.version_id in local_version_ids:
                reasons.append("DUPLICATE_VERSION_ID")
            local_version_ids.add(version.version_id)

            if previous_timestamp is not None and version.created_timestamp < previous_timestamp:
                reasons.append("NON_MONOTONIC_VERSION_HISTORY")
            previous_timestamp = version.created_timestamp

            for error in ExperimentValidator.validate_version(version, previous_version):
                reasons.append(f"INVALID_VERSION:{error}")
            previous_version = version

            if not version.reason.strip():
                reasons.append("MISSING_EXPERIMENT_REASON")
            universe = version.market_universe
            if not universe.dataset.strip() or not universe.market.strip() or not universe.timeframe.strip():
                reasons.append("MISSING_MARKET_UNIVERSE")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return LineageAudit(
        passed=not unique_reasons,
        registered_experiments=len(rows),
        reasons=unique_reasons,
    )


def certify_research_from_registry(
    evidence: CertificationInput,
    experiments: Iterable[ResearchExperiment],
    **policy_kwargs: object,
) -> CertificationVerdict:
    """Certify using registry-derived experiment count instead of trusting caller count."""
    audit = audit_experiment_lineage(experiments, hypothesis_id=evidence.hypothesis_id)
    if not audit.passed:
        # Preserve the policy's immutable safety fields and expose the actual lineage failure.
        verdict = certify_research(
            replace(
                evidence,
                registered_experiments=max(audit.registered_experiments, 0),
                search_history_complete=False,
            ),
            **policy_kwargs,
        )
        return replace(verdict, reasons=tuple(dict.fromkeys((*audit.reasons, *verdict.reasons))))

    return certify_research(
        replace(evidence, registered_experiments=audit.registered_experiments),
        **policy_kwargs,
    )
