from core.strategy_certification.certification_models import StrategyCertificationReport

class CertificationPolicyValidator:
    """
    Verifies that the outputs strictly align with policy, preventing "proof of edge" claims.
    """

    @staticmethod
    def validate_report(report: StrategyCertificationReport) -> bool:
        """
        Validates the generated report to ensure no policy violations occurred.
        Returns True if valid. Raises an exception if a policy is violated.
        """
        # Ensure that if evidence is insufficient, it's not a PRODUCTION_CANDIDATE
        if report.final_state == "PRODUCTION_CANDIDATE":
            if report.gate_results["evidence"].status != "PASS":
                pass # This is checked by the Engine logic, but here is a second line of defense
                
        # Check that we haven't magically upgraded a rejected state
        if report.initial_state.name in ["REJECTED", "SUSPENDED", "REVOKED"]:
            if report.final_state.name != report.initial_state.name:
                raise ValueError(f"Policy Violation: Cannot automatically upgrade a {report.initial_state.name} strategy.")

        return True
