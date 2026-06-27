from pathlib import Path
from core.strategy_pipeline.pipeline_state import PipelineStateTracker

class ReportGenerator:
    """Generates the unified reports for the orchestrator."""
    
    def __init__(self, output_dir: str = "docs/strategy_pipeline"):
        self.output_dir = Path(output_dir)
        
    def generate_all(self, tracker: PipelineStateTracker) -> None:
        # Create output dir for the specific strategy or unified if aggregate
        strat_dir = self.output_dir / tracker.strategy_id
        strat_dir.mkdir(parents=True, exist_ok=True)
        
        self._write_pipeline_summary(strat_dir, tracker)
        self._write_registry(strat_dir)
        self._write_truth(strat_dir)
        self._write_outcomes(strat_dir)
        self._write_statistics(strat_dir)
        self._write_certification(strat_dir)
        self._write_live_drift(strat_dir)
        self._write_blockers(strat_dir, tracker)
        self._write_limitations(strat_dir, tracker)
        self._write_final_decision(strat_dir, tracker)
        
    def _write_pipeline_summary(self, path: Path, tracker: PipelineStateTracker) -> None:
        content = f"# Pipeline Summary\n\nStrategy: {tracker.strategy_id}\nStatus: {tracker.global_state.value}\n"
        (path / "01_pipeline_summary.md").write_text(content)
        
    def _write_registry(self, path: Path) -> None:
        (path / "02_registry.md").write_text("# Registry Data\n")
        
    def _write_truth(self, path: Path) -> None:
        (path / "03_truth.md").write_text("# Truth Audit\n")
        
    def _write_outcomes(self, path: Path) -> None:
        (path / "04_outcomes.md").write_text("# Outcomes\n")
        
    def _write_statistics(self, path: Path) -> None:
        (path / "05_statistics.md").write_text("# Statistics\n")
        
    def _write_certification(self, path: Path) -> None:
        (path / "06_certification.md").write_text("# Certification\n")
        
    def _write_live_drift(self, path: Path) -> None:
        (path / "07_live_drift.md").write_text("# Live Drift\n")
        
    def _write_blockers(self, path: Path, tracker: PipelineStateTracker) -> None:
        decision = tracker.final_decision
        content = "# Blockers\n\n"
        if decision and decision.blockers:
            content += "\n".join(f"- {b}" for b in decision.blockers)
        else:
            content += "None.\n"
        (path / "08_blockers.md").write_text(content)
        
    def _write_limitations(self, path: Path, tracker: PipelineStateTracker) -> None:
        decision = tracker.final_decision
        content = "# Limitations\n\n"
        if decision and decision.limitations:
            content += "\n".join(f"- {lim}" for lim in decision.limitations)
        else:
            content += "None.\n"
        (path / "09_limitations.md").write_text(content)
        
    def _write_final_decision(self, path: Path, tracker: PipelineStateTracker) -> None:
        decision = tracker.final_decision
        if not decision:
            content = "# Final Decision\n\nUnknown. Pipeline did not complete."
        else:
            content = f"# Final Decision\n\nCurrent Certification\n\n{decision.certification_status}\n\nWHY\n\n{decision.reason}\n"
        (path / "10_final_decision.md").write_text(content)
