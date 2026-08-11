from core.strategy_certification.certification_models import StrategyCertificationReport
from core.strategy_certification.certification_types import CertificationState, GateStatus


class CertificationPolicyValidator:
    """Fail-closed validation of certification-policy outputs.

    PRODUCTION_CANDIDATE is governance eligibility only. It is not proof of
    profitability, structural edge, execution viability, paper authority, or
    live authority.
    """

    @staticmethod
    def validate_report(report: StrategyCertificationReport) -> bool:
        """Raise on contradictory or authority-inflating certification output."""
        if report.final_state == CertificationState.PRODUCTION_CANDIDATE:
            required = ("registry", "truth", "evidence", "statistics")
            for gate_name in required:
                result = report.gate_results.get(gate_name)
                if result is None:
                    raise ValueError(
                        f"Policy Violation: PRODUCTION_CANDIDATE missing required gate {gate_name}."
                    )
                if result.status != GateStatus.PASS:
                    raise ValueError(
                        "Policy Violation: PRODUCTION_CANDIDATE requires PASS for "
                        f"{gate_name}; found {result.status.name}."
                    )

        if report.initial_state in (
            CertificationState.REJECTED,
            CertificationState.SUSPENDED,
            CertificationState.REVOKED,
        ):
            if report.final_state != report.initial_state:
                raise ValueError(
                    "Policy Violation: Cannot automatically upgrade a "
                    f"{report.initial_state.name} strategy."
                )

        return True
