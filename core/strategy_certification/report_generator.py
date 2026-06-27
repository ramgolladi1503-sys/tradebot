import os
from core.strategy_certification.certification_models import StrategyCertificationReport, GateResult

class ReportGenerator:
    """
    Generates markdown reports based on the Strategy Certification Report.
    """

    def __init__(self, output_dir: str = "docs/strategy_certification"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_all(self, report: StrategyCertificationReport) -> None:
        self._write_gate_report("01_registry_gate.md", "Registry Gate", report.gate_results.get("registry"))
        self._write_gate_report("02_truth_gate.md", "Truth Gate", report.gate_results.get("truth"))
        self._write_gate_report("03_evidence_gate.md", "Evidence Gate", report.gate_results.get("evidence"))
        self._write_gate_report("04_statistics_gate.md", "Statistics Gate", report.gate_results.get("statistics"))
        self._write_gate_report("05_risk_gate.md", "Risk Gate", report.gate_results.get("risk"))
        
        self._write_certification_matrix(report)
        self._write_list_report("07_blockers.md", "Certification Blockers", report.aggregated_blockers)
        self._write_list_report("08_limitations.md", "Limitations & Warnings", report.aggregated_limitations)
        self._write_summary(report)

    def _write_gate_report(self, filename: str, title: str, result: GateResult | None) -> None:
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            f.write(f"# {title} Report\n\n")
            if not result:
                f.write("**Status**: SKIP\n\nNo evaluation available.\n")
                return
                
            f.write(f"**Status**: {result.status.name}\n\n")
            f.write(f"**Reason**: {result.reason}\n\n")
            
            if result.blockers:
                f.write("## Blockers\n\n")
                for b in result.blockers:
                    f.write(f"- {b}\n")
                f.write("\n")
                
            if result.warnings:
                f.write("## Warnings\n\n")
                for w in result.warnings:
                    f.write(f"- {w}\n")
                f.write("\n")
                
            if result.limitations:
                f.write("## Limitations\n\n")
                for lim in result.limitations:
                    f.write(f"- {lim}\n")
                f.write("\n")

    def _write_certification_matrix(self, report: StrategyCertificationReport) -> None:
        filepath = os.path.join(self.output_dir, "06_certification_matrix.md")
        with open(filepath, "w") as f:
            f.write("# Certification Matrix\n\n")
            f.write(f"**Strategy ID**: {report.strategy_id}\n")
            f.write(f"**Version**: {report.strategy_version}\n\n")
            f.write("| Gate | Status | Reason |\n")
            f.write("|------|--------|--------|\n")
            for gate_name, result in report.gate_results.items():
                f.write(f"| {gate_name.capitalize()} | {result.status.name} | {result.reason} |\n")

    def _write_list_report(self, filename: str, title: str, items: list[str]) -> None:
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            f.write(f"# {title}\n\n")
            if not items:
                f.write("None identified.\n")
                return
            for item in items:
                f.write(f"- {item}\n")

    def _write_summary(self, report: StrategyCertificationReport) -> None:
        filepath = os.path.join(self.output_dir, "10_certification_summary.md")
        with open(filepath, "w") as f:
            f.write("# Strategy Certification Summary\n\n")
            f.write(f"**Strategy ID**: {report.strategy_id}\n")
            f.write(f"**Version**: {report.strategy_version}\n")
            f.write(f"**Evaluated At**: {report.timestamp.isoformat()}\n\n")
            
            f.write("## Decision\n\n")
            f.write(f"**Initial State**: {report.initial_state.name}\n")
            f.write(f"**Final State**: {report.final_state.name}\n\n")
            
            f.write("> [!NOTE]\n")
            f.write("> Certification implies only that the available evidence currently satisfies the configured governance policy.\n")
            f.write("> It does not guarantee profitability or state that this strategy has an edge.\n")
