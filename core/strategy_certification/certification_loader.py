import json
from pathlib import Path
from typing import Any, Dict, Tuple

from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.strategy_certification.certification_errors import (
    CertificationInputMissingError,
    CertificationValidationError,
)
from core.strategy_registry.registry_loader import RegistryLoader
from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.strategy_registry import StrategyRegistry
from core.strategy_truth.truth_models import StrategySourceEvidence, StrategyTruthReport
from core.strategy_truth.truth_types import ImplementationVerdict


class DiskCertificationLoader:
    """Load certification inputs without inventing missing evidence."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)

    def load_certification_inputs(self, strategy_id: str) -> Tuple[Any, ...]:
        manifest = self._load_manifest(strategy_id)
        truth_report = self._load_truth_report(strategy_id)
        evidence_summary = self._load_evidence_summary(strategy_id)
        statistics_report = self._load_statistics_report(strategy_id)
        return manifest, truth_report, evidence_summary, statistics_report

    def _load_manifest(self, strategy_id: str) -> StrategyManifest:
        registry = StrategyRegistry()
        RegistryLoader(registry, strategies_path=str(self.base_dir / "strategies")).load_all()
        manifest = registry.get_strategy(strategy_id)
        if not manifest:
            raise CertificationInputMissingError(
                f"Strategy {strategy_id} not found in Strategy Registry."
            )
        return manifest

    def _load_truth_report(self, strategy_id: str) -> StrategyTruthReport:
        path = self.base_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.json"
        data = self._load_strategy_json(path, strategy_id, "Strategy Truth")
        required = {"strategy_id", "is_registry_complete", "verdict"}
        self._require_fields(data, required, "Strategy Truth")
        try:
            verdict = ImplementationVerdict(data["verdict"])
        except ValueError as exc:
            raise CertificationValidationError(
                f"Invalid Strategy Truth verdict for {strategy_id}: {data['verdict']!r}"
            ) from exc
        return StrategyTruthReport(
            strategy_id=strategy_id,
            is_registry_complete=bool(data["is_registry_complete"]),
            verdict=verdict,
            source_evidence=StrategySourceEvidence(
                strategy_id=strategy_id,
                classes=[],
                functions=[],
                constants=[],
                imported_modules=[],
                indicator_names=[],
                candidate_creation_calls=[],
                ranking_hooks=[],
                execution_hooks=[],
                blocker_gate_references=[],
                parameter_literals=[],
                comments=[],
            ),
            rule_comparisons=[],
            parameter_findings=[],
            heuristic_findings=[],
            indicator_findings=[],
            dependency_findings=[],
        )

    def _load_evidence_summary(self, strategy_id: str) -> OutcomeEvidenceRunSummary:
        path = self.base_dir / "runtime" / "outcome_evidence" / f"{strategy_id}_evidence_summary.json"
        data = self._load_strategy_json(path, strategy_id, "Outcome Evidence")
        required = {
            "run_id", "run_status", "total_candidates", "executable_count",
            "rejected_count", "insufficient_evidence_count", "ambiguous_count",
            "weak_ltp_count", "start_time", "end_time",
        }
        self._require_fields(data, required, "Outcome Evidence")
        if int(data["total_candidates"]) <= 0:
            raise CertificationValidationError("Outcome Evidence contains zero candidates")
        if int(data["executable_count"]) <= 0:
            raise CertificationValidationError("Outcome Evidence contains zero executable records")
        return OutcomeEvidenceRunSummary(
            run_id=data["run_id"],
            run_status=data["run_status"],
            total_candidates=int(data["total_candidates"]),
            executable_count=int(data["executable_count"]),
            rejected_count=int(data["rejected_count"]),
            insufficient_evidence_count=int(data["insufficient_evidence_count"]),
            ambiguous_count=int(data["ambiguous_count"]),
            weak_ltp_count=int(data["weak_ltp_count"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
        )

    def _load_statistics_report(self, strategy_id: str):
        path = self.base_dir / "docs" / "statistical_validation" / f"{strategy_id}_statistics.json"
        data = self._load_strategy_json(path, strategy_id, "Statistical Validation")
        required_sections = {
            "sample_validation", "expectancy", "profit_factor", "drawdown",
            "distribution", "bootstrap", "cost_sensitivity", "regime_analysis",
            "walk_forward", "stability",
        }
        self._require_fields(data, required_sections, "Statistical Validation")
        raise CertificationValidationError(
            "STRICT_STATISTICS_DESERIALIZER_REQUIRED: certification is blocked until all "
            "statistical sections are deserialized from real values; fabricated VALID/STABLE "
            "defaults are forbidden"
        )

    def _load_strategy_json(self, path: Path, strategy_id: str, context: str) -> Dict[str, Any]:
        if not path.exists():
            raise CertificationInputMissingError(f"{context} missing at {path}.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CertificationValidationError(f"Failed to parse {context} at {path}: {exc}") from exc
        if data.get("strategy_id") != strategy_id:
            raise CertificationValidationError(
                f"{context} strategy_id mismatch: expected {strategy_id}, found {data.get('strategy_id')!r}"
            )
        return data

    @staticmethod
    def _require_fields(data: Dict[str, Any], fields: set[str], context: str) -> None:
        missing = sorted(fields.difference(data))
        if missing:
            raise CertificationValidationError(f"{context} missing required fields: {missing}")
