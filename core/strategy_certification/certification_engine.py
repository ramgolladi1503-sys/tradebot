from datetime import datetime
from typing import Optional

from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_truth.truth_models import StrategyTruthReport
from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.statistical_validation.statistics_models import StatisticalValidationReport

from core.strategy_certification.certification_models import GateResult, StrategyCertificationReport
from core.strategy_certification.certification_types import CertificationState, GateStatus

from core.strategy_certification.eligibility import RegistryGate
from core.strategy_certification.truth_gate import TruthGate
from core.strategy_certification.evidence_gate import EvidenceGate
from core.strategy_certification.statistics_gate import StatisticsGate
from core.strategy_certification.risk_gate import RiskGate


class CertificationEngine:
    """
    Orchestrates the governance gates to produce a final CertificationState.
    """

    @staticmethod
    def run_certification(
        manifest: Optional[StrategyManifest],
        truth_report: Optional[StrategyTruthReport],
        evidence_summary: Optional[OutcomeEvidenceRunSummary],
        statistics_report: Optional[StatisticalValidationReport],
        initial_state: CertificationState = CertificationState.RESEARCH_ONLY
    ) -> StrategyCertificationReport:
        
        # If the strategy is explicitly suspended, revoked, or rejected, 
        # it cannot proceed to higher environments without manual override.
        if initial_state in (CertificationState.REJECTED, CertificationState.SUSPENDED, CertificationState.REVOKED):
            return CertificationEngine._build_report(
                manifest=manifest,
                initial_state=initial_state,
                final_state=initial_state,
                gate_results={"pre_check": GateResult(status=GateStatus.FAIL, reason=f"Strategy is currently {initial_state.name}", blockers=[f"Cannot certify a {initial_state.name} strategy."])}
            )

        gate_results = {}
        
        # Gate 1: Registry
        registry_result = RegistryGate.evaluate(manifest)
        gate_results["registry"] = registry_result
        if registry_result.status == GateStatus.FAIL:
            return CertificationEngine._build_report(manifest, initial_state, CertificationState.RESEARCH_ONLY, gate_results)

        # Gate 2: Truth
        truth_result = TruthGate.evaluate(truth_report)
        gate_results["truth"] = truth_result
        if truth_result.status == GateStatus.FAIL:
            return CertificationEngine._build_report(manifest, initial_state, CertificationState.RESEARCH_ONLY, gate_results)

        # Gate 3: Evidence
        evidence_result = EvidenceGate.evaluate(evidence_summary)
        gate_results["evidence"] = evidence_result
        if evidence_result.status == GateStatus.FAIL:
            return CertificationEngine._build_report(manifest, initial_state, CertificationState.INSUFFICIENT_EVIDENCE, gate_results)

        # Gate 4: Statistics
        statistics_result = StatisticsGate.evaluate(statistics_report)
        gate_results["statistics"] = statistics_result
        if statistics_result.status == GateStatus.FAIL:
            return CertificationEngine._build_report(manifest, initial_state, CertificationState.INSUFFICIENT_EVIDENCE, gate_results)

        # Gate 5: Risk (Governance only)
        risk_result = RiskGate.evaluate(statistics_report, evidence_summary)
        gate_results["risk"] = risk_result
        
        # If we passed all structural gates (Registry, Truth, Evidence, Statistics),
        # the strategy satisfies the policy to be considered a PRODUCTION_CANDIDATE.
        # This does NOT assert edge, only that all governance gates are passed.
        
        return CertificationEngine._build_report(manifest, initial_state, CertificationState.PRODUCTION_CANDIDATE, gate_results)

    @staticmethod
    def _build_report(
        manifest: Optional[StrategyManifest], 
        initial_state: CertificationState,
        final_state: CertificationState,
        gate_results: dict[str, GateResult]
    ) -> StrategyCertificationReport:
        
        strategy_id = manifest.contract.strategy_id if manifest and manifest.contract else "UNKNOWN"
        strategy_version = manifest.contract.version if manifest and manifest.contract else "UNKNOWN"
        
        aggregated_blockers = []
        aggregated_limitations = []
        
        for name, result in gate_results.items():
            for blocker in result.blockers:
                aggregated_blockers.append(f"[{name}] {blocker}")
            for limitation in result.limitations:
                aggregated_limitations.append(f"[{name}] {limitation}")
            for warning in result.warnings:
                aggregated_limitations.append(f"[{name} WARNING] {warning}")

        return StrategyCertificationReport(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            timestamp=datetime.utcnow(),
            initial_state=initial_state,
            final_state=final_state,
            gate_results=gate_results,
            aggregated_blockers=aggregated_blockers,
            aggregated_limitations=aggregated_limitations
        )
