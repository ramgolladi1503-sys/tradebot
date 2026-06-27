import os
from core.strategy_certification.certification_models import StrategyCertificationReport

class AuditLogger:
    """
    Appends certification decisions to an immutable audit log.
    """

    def __init__(self, log_path: str = "docs/strategy_certification/09_audit_log.md"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        
        # Initialize if it doesn't exist
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w") as f:
                f.write("# Strategy Certification Audit Log\n\n")
                f.write("| Timestamp | Strategy ID | Version | Initial State | Final State | Blockers Count | Limitations Count |\n")
                f.write("|-----------|-------------|---------|---------------|-------------|----------------|-------------------|\n")

    def log(self, report: StrategyCertificationReport) -> None:
        with open(self.log_path, "a") as f:
            ts = report.timestamp.isoformat()
            sid = report.strategy_id
            ver = report.strategy_version
            init = report.initial_state.name
            final = report.final_state.name
            block_cnt = len(report.aggregated_blockers)
            lim_cnt = len(report.aggregated_limitations)
            
            f.write(f"| {ts} | {sid} | {ver} | {init} | {final} | {block_cnt} | {lim_cnt} |\n")
