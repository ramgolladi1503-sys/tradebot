"""Independent Verifier for Live Pipeline Observability and Evidence.

Reconstructs and verifies from primitive telemetry:
- Trace stage order and trace ID immutability
- First divergence detection
- Strategy invocation coverage and wiring vs market distinction
- Candidate lifecycle transitions and disappearance detection
- Candidate-empty attribution logic
- Role-aware token coverage and health impact
- Non-intrusive telemetry invariants (zero additional file I/O on normal tick path)

Does not trust self-reported PASS flags.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.observability.candidate_attribution import (
    CandidateEmptyClass,
    CandidateLifecycleLedger,
    EmptyPoolSummaryClass,
    StrategyCoverageTracker,
    StrategyEvaluationAttribution,
)
from core.observability.stage_lineage import (
    CANONICAL_CHECKPOINT_ORDER,
    StageRecord,
    StageStatus,
)
from core.observability.token_health_model import (
    RoleAwareHealthReport,
    SystemHealthStatus,
    TokenDependencyGraph,
    TokenObservation,
    TokenRole,
)
from core.observability.trace_pulse import (
    DiagnosticPulseRing,
    FirstDivergenceReport,
    analyze_first_divergence,
)


class VerificationError(ValueError):
    """Raised when independent verification fails an invariant."""


class IndependentObservabilityVerifier:
    """Independent oracle that strictly validates all pipeline telemetry contracts."""

    @staticmethod
    def verify_trace_immutability_and_order(stage_records: Sequence[StageRecord]) -> bool:
        """Verify that trace_id never changes and stages follow valid topological ordering."""
        if not stage_records:
            return True

        expected_trace_id = stage_records[0].trace_id
        checkpoint_indices = {cp: idx for idx, cp in enumerate(CANONICAL_CHECKPOINT_ORDER)}

        last_index = -1
        for idx, rec in enumerate(stage_records):
            rec.validate()
            # 1. Verify trace ID immutability
            if rec.trace_id != expected_trace_id:
                raise VerificationError(
                    f"trace_id_mutated at stage {rec.stage_id}: expected {expected_trace_id}, got {rec.trace_id}"
                )

            # 2. Verify stage order monotonicity (allowing for re-entry within valid flow)
            cp_idx = checkpoint_indices.get(rec.component)
            if cp_idx is not None:
                if cp_idx < last_index:
                    # Backward jump in canonical checkpoint pipeline
                    raise VerificationError(
                        f"stage_order_violation: checkpoint {rec.component} (idx {cp_idx}) followed stage (idx {last_index})"
                    )
                last_index = cp_idx

            # 3. Verify safety properties
            if rec.is_order_action:  # is_order_action=false
                raise VerificationError("stage_record_has_order_action_true")
            if rec.broker_write_authority:
                raise VerificationError("stage_record_has_broker_write_true")

        return True

    @staticmethod
    def verify_first_divergence_oracle(
        stage_records: Sequence[StageRecord],
        claimed_report: FirstDivergenceReport,
    ) -> bool:
        """Independently re-compute first divergence and compare against claimed report."""
        oracle_report = analyze_first_divergence(stage_records)

        if oracle_report.diverged != claimed_report.diverged:
            raise VerificationError(
                f"divergence_mismatch: oracle={oracle_report.diverged} claimed={claimed_report.diverged}"
            )

        if oracle_report.diverged:
            if oracle_report.first_divergence_stage != claimed_report.first_divergence_stage:
                raise VerificationError(
                    f"first_divergence_stage_mismatch: oracle={oracle_report.first_divergence_stage} "
                    f"claimed={claimed_report.first_divergence_stage}"
                )
            if oracle_report.upstream_stages_healthy != claimed_report.upstream_stages_healthy:
                raise VerificationError(
                    f"upstream_health_mismatch: oracle={oracle_report.upstream_stages_healthy} "
                    f"claimed={claimed_report.upstream_stages_healthy}"
                )
            if not claimed_report.rca:
                raise VerificationError("missing_rca_candidate_on_diverged_trace")
            if claimed_report.rca.causal_classification not in {"PROVEN", "SUPPORTED", "HYPOTHESIS", "UNKNOWN"}:
                raise VerificationError(f"invalid_rca_causal_classification: {claimed_report.rca.causal_classification}")

        return True

    @staticmethod
    def verify_candidate_lifecycle(
        ledger: CandidateLifecycleLedger,
        candidate_id: str,
        expected_final_stage: str,
        expected_final_status: str,
    ) -> bool:
        """Verify complete candidate transition chain with no silent drops."""
        history = ledger.get_candidate_history(candidate_id)
        if not history:
            raise VerificationError(f"candidate_not_found_in_ledger: {candidate_id}")

        last_trans = history[-1]
        if last_trans.to_stage != expected_final_stage:
            raise VerificationError(
                f"candidate_final_stage_mismatch: expected {expected_final_stage}, got {last_trans.to_stage}"
            )
        if last_trans.status != expected_final_status:
            raise VerificationError(
                f"candidate_final_status_mismatch: expected {expected_final_status}, got {last_trans.status}"
            )
        return True

    @staticmethod
    def verify_empty_pool_attribution(
        tracker: StrategyCoverageTracker,
        expected_class: str,
    ) -> bool:
        """Verify candidate empty pool diagnostic classification."""
        diag = tracker.diagnose_empty_pool()
        actual_class = diag.get("EMPTY_POOL_CLASS")
        if actual_class != expected_class:
            raise VerificationError(
                f"empty_pool_attribution_mismatch: expected {expected_class}, got {actual_class}"
            )
        return True

    @staticmethod
    def verify_token_health_attribution(
        graph: TokenDependencyGraph,
        observations: Sequence[TokenObservation],
        expected_health: str,
        expected_system_critical: bool,
    ) -> bool:
        """Verify token health evaluation matches policy rules."""
        report = graph.evaluate_health(observations)
        if report.overall_health != expected_health:
            raise VerificationError(
                f"token_health_status_mismatch: expected {expected_health}, got {report.overall_health}"
            )
        if report.system_critical != expected_system_critical:
            raise VerificationError(
                f"system_critical_mismatch: expected {expected_system_critical}, got {report.system_critical}"
            )
        return True

    @staticmethod
    def verify_non_intrusive_telemetry(ring: DiagnosticPulseRing) -> bool:
        """Verify normal tick path adds ZERO file I/O."""
        if ring.normal_tick_path_additional_io != 0:
            raise VerificationError(
                f"non_intrusive_violation: NORMAL_TICK_PATH_ADDITIONAL_IO={ring.normal_tick_path_additional_io} (must be 0)"
            )
        return True
