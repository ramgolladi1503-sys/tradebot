from __future__ import annotations

import hashlib
import json
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
    digest_sha256: str


def _canonical_payload(rows: list[ResearchExperiment]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for experiment in sorted(rows, key=lambda e: e.experiment_id):
        versions = []
        for version in experiment.versions:
            versions.append({
                "version_id": version.version_id,
                "created_timestamp": version.created_timestamp.isoformat(),
                "author": version.author,
                "branch": version.branch,
                "commit": version.commit,
                "market_universe": {
                    "dataset": version.market_universe.dataset,
                    "market": version.market_universe.market,
                    "timeframe": version.market_universe.timeframe,
                },
                "parameters": sorted((str(k), str(v)) for k, v in version.parameters.parameters.items()),
                "reason": version.reason,
                "result": {
                    "expected_behavior": version.result.expected_behavior,
                    "actual_behavior": version.result.actual_behavior,
                    "limitations": list(version.result.limitations),
                    "conclusion": version.result.conclusion,
                },
                "stage": version.stage.name,
            })
        payload.append({
            "experiment_id": experiment.experiment_id,
            "parent_hypothesis_id": experiment.parent_hypothesis_id,
            "versions": versions,
            "evidence": {
                "strategy_registry_id": experiment.evidence.strategy_registry_id,
                "truth_engine_report_id": experiment.evidence.truth_engine_report_id,
                "outcome_evidence_id": experiment.evidence.outcome_evidence_id,
                "statistical_validation_id": experiment.evidence.statistical_validation_id,
                "certification_id": experiment.evidence.certification_id,
            },
        })
    return payload


def lineage_digest(experiments: Iterable[ResearchExperiment]) -> str:
    rows = list(experiments)
    encoded = json.dumps(_canonical_payload(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def audit_experiment_lineage(experiments: Iterable[ResearchExperiment], *, hypothesis_id: str) -> LineageAudit:
    rows = list(experiments)
    reasons: list[str] = []
    if not isinstance(hypothesis_id, str) or not hypothesis_id.strip(): reasons.append("MISSING_HYPOTHESIS_ID")
    if not rows: reasons.append("MISSING_EXPERIMENT_HISTORY")
    experiment_ids: set[str] = set()
    for experiment in rows:
        if not isinstance(experiment.experiment_id, str) or not experiment.experiment_id.strip(): reasons.append("MISSING_EXPERIMENT_ID")
        elif experiment.experiment_id in experiment_ids: reasons.append("DUPLICATE_EXPERIMENT_ID")
        experiment_ids.add(experiment.experiment_id)
        if experiment.parent_hypothesis_id != hypothesis_id: reasons.append("PARENT_HYPOTHESIS_MISMATCH")
        if not experiment.versions:
            reasons.append("EXPERIMENT_WITHOUT_VERSION")
            continue
        previous_timestamp = None
        previous_version = None
        local_version_ids: set[str] = set()
        for version in experiment.versions:
            if not isinstance(version.version_id, str) or not version.version_id.strip(): reasons.append("MISSING_VERSION_ID")
            elif version.version_id in local_version_ids: reasons.append("DUPLICATE_VERSION_ID")
            local_version_ids.add(version.version_id)
            if previous_timestamp is not None and version.created_timestamp < previous_timestamp: reasons.append("NON_MONOTONIC_VERSION_HISTORY")
            previous_timestamp = version.created_timestamp
            for error in ExperimentValidator.validate_version(version, previous_version): reasons.append(f"INVALID_VERSION:{error}")
            previous_version = version
            if not isinstance(version.reason, str) or not version.reason.strip(): reasons.append("MISSING_EXPERIMENT_REASON")
            universe = version.market_universe
            if not universe.dataset.strip() or not universe.market.strip() or not universe.timeframe.strip(): reasons.append("MISSING_MARKET_UNIVERSE")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return LineageAudit(passed=not unique_reasons, registered_experiments=len(rows), reasons=unique_reasons, digest_sha256=lineage_digest(rows))


def certify_research_from_registry(
    evidence: CertificationInput,
    experiments: Iterable[ResearchExperiment],
    *,
    expected_lineage_digest: str | None,
    require_prospective: bool = False,
) -> CertificationVerdict:
    rows = list(experiments)
    audit = audit_experiment_lineage(rows, hypothesis_id=evidence.hypothesis_id)
    lineage_reasons = list(audit.reasons)
    if expected_lineage_digest is None:
        lineage_reasons.append("LINEAGE_DIGEST_REQUIRED")
    elif not isinstance(expected_lineage_digest, str) or len(expected_lineage_digest) != 64:
        lineage_reasons.append("INVALID_LINEAGE_DIGEST")
    elif audit.digest_sha256 != expected_lineage_digest:
        lineage_reasons.append("LINEAGE_DIGEST_MISMATCH")
    if lineage_reasons:
        verdict = certify_research(
            replace(evidence, registered_experiments=max(audit.registered_experiments, 0), search_history_complete=False),
            require_prospective=require_prospective,
        )
        return replace(verdict, reasons=tuple(dict.fromkeys((*lineage_reasons, *verdict.reasons))))
    return certify_research(
        replace(evidence, registered_experiments=audit.registered_experiments),
        require_prospective=require_prospective,
    )
