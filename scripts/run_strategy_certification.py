import argparse
import sys
import logging
from datetime import date

from core.strategy_certification.certification_types import CertificationState
from core.strategy_certification.certification_engine import CertificationEngine
from core.strategy_certification.report_generator import ReportGenerator
from core.strategy_certification.audit_log import AuditLogger
from core.strategy_certification.validation import CertificationPolicyValidator
from core.strategy_certification.certification_loader import DiskCertificationLoader
from core.strategy_certification.certification_errors import CertificationInputMissingError, CertificationValidationError

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def main():
    parser = argparse.ArgumentParser(description="Run Strategy Certification Engine")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy ID to certify")
    parser.add_argument("--dry-run", action="store_true", help="Run with mock data")
    args = parser.parse_args()
    
    logging.info(f"Running certification for {args.strategy}")
    loader = DiskCertificationLoader()
    
    try:
        manifest, truth_report, evidence_summary, stats_report = loader.load_certification_inputs(args.strategy)
    except CertificationInputMissingError as e:
        logging.error(f"CERTIFICATION_INPUT_MISSING: {e}")
        sys.exit(1)
    except CertificationValidationError as e:
        logging.error(f"CERTIFICATION_VALIDATION_ERROR: {e}")
        sys.exit(1)

    logging.info("Evaluating Certification Gates...")
    report = CertificationEngine.run_certification(
        manifest=manifest,
        truth_report=truth_report,
        evidence_summary=evidence_summary,
        statistics_report=stats_report,
        initial_state=CertificationState.RESEARCH_ONLY
    )
    
    logging.info(f"Final Certification State: {report.final_state.name}")
    
    logging.info("Validating policies...")
    CertificationPolicyValidator.validate_report(report)
    
    logging.info("Generating reports...")
    generator = ReportGenerator()
    generator.generate_all(report)
    
    logging.info("Writing audit log...")
    logger = AuditLogger()
    logger.log(report)
    
    logging.info("Done.")

if __name__ == "__main__":
    main()
