from pathlib import Path
from typing import List
from .evidence_models import OutcomeEvidenceRecord, OutcomeEvidenceRunSummary
from .evidence_types import EvidenceQuality


class ReportGenerator:
    """Generates markdown reports for the outcome evidence run."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_reports(self, summary: OutcomeEvidenceRunSummary, records: List[OutcomeEvidenceRecord]):
        self._generate_run_report(summary, records)
        self._generate_outcome_quality_report(records)
        self._generate_rejected_candidate_report(records)
        self._generate_cost_model_report(records)
        self._generate_regime_context_report(records)
        self._generate_limitations_report()
        
    def _generate_run_report(self, summary: OutcomeEvidenceRunSummary, records: List[OutcomeEvidenceRecord]):
        content = f"""# 03 Replay Run Report

## Summary
- **Run ID**: {summary.run_id}
- **Status**: {summary.run_status}
- **Total Candidates**: {summary.total_candidates}
- **Executable**: {summary.executable_count}
- **Rejected**: {summary.rejected_count}
- **Insufficient Evidence**: {summary.insufficient_evidence_count}

## Ambiguities
- **Ambiguous Outcomes**: {summary.ambiguous_count}
- **Weak LTP Count**: {summary.weak_ltp_count}

*(No performance claims or strategy edge assertions are made in this report)*
"""
        (self.output_dir / "03_replay_run_report.md").write_text(content)
        
    def _generate_outcome_quality_report(self, records: List[OutcomeEvidenceRecord]):
        counts = {q.name: 0 for q in EvidenceQuality}
        for r in records:
            counts[r.evidence_quality.name] += 1
            
        content = "# 04 Outcome Quality Report\n\n## Evidence Quality Breakdown\n"
        for q, c in counts.items():
            content += f"- **{q}**: {c}\n"
        (self.output_dir / "04_outcome_quality_report.md").write_text(content)

    def _generate_rejected_candidate_report(self, records: List[OutcomeEvidenceRecord]):
        rejected = [r for r in records if r.simulation.is_hypothetical_rejected]
        content = f"# 05 Rejected Candidate Report\n\nTotal Rejected (Hypothetical Outcomes): {len(rejected)}\n"
        (self.output_dir / "05_rejected_candidate_report.md").write_text(content)

    def _generate_cost_model_report(self, records: List[OutcomeEvidenceRecord]):
        content = "# 06 Cost Model Report\n\nRecords cost assumptions. Default spreads/slippage are used when exact bid/ask unavailable.\n"
        (self.output_dir / "06_cost_model_report.md").write_text(content)

    def _generate_regime_context_report(self, records: List[OutcomeEvidenceRecord]):
        content = "# 07 Regime Context Report\n\nDescribes attached regimes during candidates timeframe.\n"
        (self.output_dir / "07_regime_context_report.md").write_text(content)

    def _generate_limitations_report(self):
        content = """# 08 Limitations

- Simulated fills may not match live fills.
- LTP traces without bid/ask lack strict execution realism.
- Both-hit scenarios are marked AMBIGUOUS when tick granularity is insufficient.
- This is a read-only engine, not a certification of profitability.
"""
        (self.output_dir / "08_limitations.md").write_text(content)
