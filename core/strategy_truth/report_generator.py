import os
from typing import List
from core.strategy_truth.truth_models import StrategyTruthReport, StrategyTruthSummary


class ReportGenerator:
    """Generates markdown reports for Strategy Truth Engine."""

    def __init__(self, output_dir: str = "docs/strategy_truth"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def write_reports(self, summary: StrategyTruthSummary):
        self._write_01_loaded_registry(summary.reports, summary.registry_incomplete_count)
        self._write_02_parameter_inventory(summary.reports)
        self._write_03_heuristic_audit(summary.reports)
        self._write_04_indicator_inventory(summary.reports)
        self._write_05_dependency_graph(summary.reports)
        self._write_06_strategy_truth_summary(summary)

    def _write_01_loaded_registry(self, reports: List[StrategyTruthReport], incomplete: int):
        path = os.path.join(self.output_dir, "01_loaded_registry.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Loaded Registry\n\n")
            f.write(f"Incomplete Registries: {incomplete}\n\n")
            for r in reports:
                f.write(f"## {r.strategy_id}\n")
                f.write(f"- Registry Complete: {r.is_registry_complete}\n")

    def _write_02_parameter_inventory(self, reports: List[StrategyTruthReport]):
        path = os.path.join(self.output_dir, "02_parameter_inventory.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Parameter Inventory\n\n")
            for r in reports:
                f.write(f"## {r.strategy_id}\n")
                for p in r.parameter_findings:
                    f.write(f"- {p.name}: {p.value} ({p.classification.value}) at {p.file_path}:{p.line_number}\n")

    def _write_03_heuristic_audit(self, reports: List[StrategyTruthReport]):
        path = os.path.join(self.output_dir, "03_heuristic_audit.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Heuristic Audit\n\n")
            for r in reports:
                f.write(f"## {r.strategy_id}\n")
                for h in r.heuristic_findings:
                    f.write(f"- {h.keyword_found} -> {h.classification.value} at {h.file_path}:{h.line_number}\n")

    def _write_04_indicator_inventory(self, reports: List[StrategyTruthReport]):
        path = os.path.join(self.output_dir, "04_indicator_inventory.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Indicator Inventory\n\n")
            for r in reports:
                f.write(f"## {r.strategy_id}\n")
                for i in r.indicator_findings:
                    f.write(f"- {i.indicator_name}: {i.status.value} - {i.reason}\n")

    def _write_05_dependency_graph(self, reports: List[StrategyTruthReport]):
        path = os.path.join(self.output_dir, "05_dependency_graph.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Dependency Graph\n\n")
            for r in reports:
                f.write(f"## {r.strategy_id}\n")
                for d in r.dependency_findings:
                    f.write(f"- {d.dependency_type}: {d.dependency_name} (Missing: {d.is_missing}, Unused: {d.is_unused}, Direct: {d.is_direct_coupling}) - {d.reason}\n")

    def _write_06_strategy_truth_summary(self, summary: StrategyTruthSummary):
        path = os.path.join(self.output_dir, "06_strategy_truth_summary.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Strategy Truth Summary\n\n")
            f.write(f"Total Strategies: {summary.total_strategies}\n")
            f.write(f"Fully Verified: {summary.fully_verified_count}\n")
            f.write(f"Partially Verified: {summary.partially_verified_count}\n")
            f.write(f"Mismatch: {summary.mismatch_count}\n")
            f.write(f"Registry Incomplete: {summary.registry_incomplete_count}\n\n")
            
            for r in summary.reports:
                f.write(f"## {r.strategy_id}\n")
                f.write(f"- Verdict: {r.verdict.value}\n")
                f.write(f"- Evidence Count: {len(r.rule_evidence)}\n")
                f.write(f"- Parameter Count: {len(r.parameter_findings)}\n")
                f.write(f"- Heuristic Risk Count: {len([h for h in r.heuristic_findings if 'RISK' in h.classification.value])}\n")
                f.write(f"- Indicator Mismatch Count: {len([i for i in r.indicator_findings if i.status.value != 'DECLARED_AND_USED'])}\n")
                f.write(f"- Dependency Concerns: {len([d for d in r.dependency_findings if d.is_missing or d.is_unused or d.is_direct_coupling])}\n")
