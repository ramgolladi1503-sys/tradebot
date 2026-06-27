from pathlib import Path
from core.research_registry.research_models import ResearchRegistryReport
from core.research_registry.dependency_graph import DependencyGraph
from core.research_registry.lineage_tracker import LineageTracker
from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_types import ResearchStage, PromotionStatus

class ReportGenerator:
    """Generates the 12 Markdown files in docs/research_registry/."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, filename: str, content: str):
        (self.output_dir / filename).write_text(content, encoding="utf-8")

    def generate(self, report: ResearchRegistryReport, hypothesis_registry: HypothesisRegistry, experiment_registry: ExperimentRegistry):
        self._write("01_hypothesis_inventory.md", self._generate_hypothesis_inventory(report))
        self._write("02_experiment_inventory.md", self._generate_experiment_inventory(report))
        self._write("03_lineage_graph.md", self._generate_lineage_graph(hypothesis_registry, experiment_registry))
        self._write("04_parameter_history.md", self._generate_parameter_history(report))
        self._write("05_failed_experiments.md", self._generate_failed_experiments(report))
        self._write("06_successful_experiments.md", self._generate_successful_experiments(report))
        self._write("07_promotion_candidates.md", self._generate_promotion_candidates(report))
        self._write("08_duplicate_detection.md", self._generate_duplicate_detection(report))
        self._write("09_limitations.md", self._generate_limitations(report))
        self._write("10_architecture.md", self._generate_architecture())
        self._write("11_governance.md", self._generate_governance())
        self._write("12_summary.md", self._generate_summary(report))

    def _generate_hypothesis_inventory(self, report: ResearchRegistryReport) -> str:
        lines = ["# Hypothesis Inventory\n"]
        for hyp in report.hypotheses:
            lines.append(f"## {hyp.hypothesis_id}: {hyp.title}")
            lines.append(f"- **Author**: {hyp.author}")
            lines.append(f"- **Created**: {hyp.created_timestamp.isoformat()}")
            lines.append(f"- **Description**: {hyp.description}\n")
        return "\n".join(lines)

    def _generate_experiment_inventory(self, report: ResearchRegistryReport) -> str:
        lines = ["# Experiment Inventory\n"]
        for exp in report.experiments:
            lines.append(f"## Experiment {exp.experiment_id}")
            lines.append(f"- **Parent Hypothesis**: {exp.parent_hypothesis_id}")
            lines.append(f"- **Versions**: {len(exp.versions)}")
        return "\n".join(lines)

    def _generate_lineage_graph(self, hypothesis_registry: HypothesisRegistry, experiment_registry: ExperimentRegistry) -> str:
        lines = ["# Lineage Graph\n", "```mermaid", "graph TD"]
        graph = DependencyGraph(hypothesis_registry, experiment_registry).build_full_lineage_graph()
        for hyp_id, data in graph.items():
            lines.append(f"    {hyp_id}[\"{hyp_id}\"]")
            for exp in data["experiments"]:
                exp_id = exp["experiment_id"]
                lines.append(f"    {hyp_id} --> {exp_id}[\"{exp_id}\"]")
                if exp["evidence_links"]["strategy"]:
                    lines.append(f"    {exp_id} --> STRAT_{exp_id}[\"Strategy Registry\"]")
        lines.append("```")
        return "\n".join(lines)

    def _generate_parameter_history(self, report: ResearchRegistryReport) -> str:
        lines = ["# Parameter History\n"]
        for exp in report.experiments:
            history = LineageTracker.extract_parameter_evolution(exp)
            lines.append(f"## {exp.experiment_id}")
            for item in history:
                lines.append(f"- **{item['version_id']}** ({item['stage']}): {item['parameters']}")
        return "\n".join(lines)

    def _generate_failed_experiments(self, report: ResearchRegistryReport) -> str:
        lines = ["# Failed Experiments\n"]
        for exp in report.experiments:
            if exp.versions and exp.versions[-1].stage == ResearchStage.FAILED:
                lines.append(f"- {exp.experiment_id} failed in version {exp.versions[-1].version_id}")
        return "\n".join(lines)

    def _generate_successful_experiments(self, report: ResearchRegistryReport) -> str:
        lines = ["# Successful Experiments\n"]
        for exp in report.experiments:
            if exp.versions and exp.versions[-1].stage in (ResearchStage.PAPER_READY, ResearchStage.SHADOW_READY, ResearchStage.STRATEGY_REGISTRY):
                lines.append(f"- {exp.experiment_id} reached {exp.versions[-1].stage.name}")
        return "\n".join(lines)

    def _generate_promotion_candidates(self, report: ResearchRegistryReport) -> str:
        lines = ["# Promotion Candidates\n"]
        for dec in report.decisions:
            if dec.recommendation.status in (PromotionStatus.READY_FOR_IMPLEMENTATION, PromotionStatus.READY_FOR_STRATEGY_REGISTRY):
                lines.append(f"- {dec.experiment_id} (Version: {dec.version_id}): {dec.recommendation.status.name}")
                for reason in dec.recommendation.reasons:
                    lines.append(f"  - {reason}")
        return "\n".join(lines)

    def _generate_duplicate_detection(self, report: ResearchRegistryReport) -> str:
        return "# Duplicate Detection\n\nNo duplicate IDs allowed by registry design."

    def _generate_limitations(self, report: ResearchRegistryReport) -> str:
        lines = ["# Limitations\n"]
        for exp in report.experiments:
            if exp.versions:
                lims = exp.versions[-1].result.limitations
                if lims:
                    lines.append(f"## {exp.experiment_id}")
                    for lim in lims:
                        lines.append(f"- {lim}")
        return "\n".join(lines)

    def _generate_architecture(self) -> str:
        return "# Architecture\n\nPurely read-only registry. No execution bindings."

    def _generate_governance(self) -> str:
        return "# Governance\n\nState transitions are recommended, never automated."

    def _generate_summary(self, report: ResearchRegistryReport) -> str:
        return f"# Summary\n\nHypotheses: {len(report.hypotheses)}\nExperiments: {len(report.experiments)}\nDecisions: {len(report.decisions)}\n"
