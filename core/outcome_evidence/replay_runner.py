import time
from pathlib import Path
from typing import Optional
from .candidate_loader import CandidateLoader
from .option_trace_adapter import OptionTraceAdapter
from .outcome_resolver import OutcomeResolver
from .mfe_mae import MfeMaeCalculator
from .cost_model import IndianIndexOptionsCostModel
from .execution_simulator import ExecutionSimulator
from .regime_context import RegimeContextLoader
from .evidence_store import OutcomeEvidenceStore
from .evidence_models import OutcomeEvidenceRecord, OutcomeEvidenceRunSummary, ReplayOutcome, RegimeContextEvidence
from .evidence_types import EvidenceQuality, OutcomeStatus, ReplayRunStatus
from .report_generator import ReportGenerator


class OutcomeEvidenceRunner:
    """Orchestrates the outcome evidence pipeline."""
    
    def __init__(self, run_id: str, store_dir: Path, cost_model: IndianIndexOptionsCostModel):
        self.run_id = run_id
        self.store = OutcomeEvidenceStore(store_dir)
        self.resolver = OutcomeResolver()
        self.mfe_mae_calculator = MfeMaeCalculator()
        self.cost_model = cost_model
        self.execution_simulator = ExecutionSimulator()
        self.report_generator = ReportGenerator(Path("docs/outcome_evidence"))

    def run(self, candidate_file: Path, option_trace_file: Path, regime_file: Optional[Path], dry_run: bool = False) -> OutcomeEvidenceRunSummary:
        start_time = time.time()
        loader = CandidateLoader(candidate_file)
        trace_adapter = OptionTraceAdapter(option_trace_file)
        regime_loader = RegimeContextLoader(regime_file) if regime_file else None
        
        records = []
        total_candidates = 0
        executable_count = 0
        rejected_count = 0
        insufficient_count = 0
        ambiguous_count = 0
        weak_ltp_count = 0
        
        for candidate in loader.load_jsonl():
            total_candidates += 1
            if candidate.execution_ok:
                executable_count += 1
            else:
                rejected_count += 1
                
            if candidate.evidence_quality == EvidenceQuality.UNUSABLE:
                insufficient_count += 1
                continue
                
            # Get traces for the outcome window
            traces = trace_adapter.get_trace_window(candidate.timestamp)
            
            # Resolve target/stop
            outcome: ReplayOutcome = self.resolver.resolve(candidate, traces)
            
            if outcome.status == OutcomeStatus.AMBIGUOUS_BOTH_HIT:
                ambiguous_count += 1
            if outcome.status == OutcomeStatus.INSUFFICIENT_CANDIDATE_FIELDS:
                insufficient_count += 1
                
            # MFE / MAE
            mfe_mae = self.mfe_mae_calculator.calculate(candidate, traces, outcome.exit_time)
            
            # Execution Sim
            entry_tick = traces[0] if traces else None
            exit_tick = None
            if outcome.exit_time and traces:
                for t in traces:
                    if t.timestamp >= outcome.exit_time:
                        exit_tick = t
                        break
                        
            sim = self.execution_simulator.simulate(candidate, entry_tick, exit_tick)
            
            # Cost breakdown
            cost = self.cost_model.calculate(
                entry_price=sim.entry_fill,
                exit_price=sim.exit_fill,
                lot_size=15, # Default lot size, could be configured
                bid_ask_spread=sim.spread_impact if sim.spread_impact > 0 else None
            )
            
            # Regime
            regime = regime_loader.get_context_at(candidate.timestamp) if regime_loader else RegimeContextEvidence()
            
            net_pnl = outcome.gross_pnl - cost.total_cost if outcome.gross_pnl else -cost.total_cost
            
            warnings = []
            if candidate.evidence_quality != EvidenceQuality.COMPLETE:
                warnings.append(f"Candidate data quality is {candidate.evidence_quality.name}")
                
            record = OutcomeEvidenceRecord(
                run_id=self.run_id,
                candidate_id=candidate.candidate_id or "UNKNOWN",
                strategy_id=candidate.strategy_id or "UNKNOWN",
                input_source=str(candidate_file),
                evidence_quality=candidate.evidence_quality,
                outcome_status=outcome.status,
                exit_reason=outcome.exit_reason,
                mfe_mae=mfe_mae,
                cost_breakdown=cost,
                gross_pnl=outcome.gross_pnl,
                net_pnl=net_pnl,
                regime_context=regime,
                simulation=sim,
                warnings=warnings,
                created_timestamp=time.time()
            )
            records.append(record)
            
        if not dry_run and records:
            self.store.save_records(records, filename=f"evidence_{self.run_id}.jsonl")
            
        end_time = time.time()
        summary = OutcomeEvidenceRunSummary(
            run_id=self.run_id,
            run_status=ReplayRunStatus.SUCCESS.name if total_candidates > 0 else ReplayRunStatus.FAILED.name,
            total_candidates=total_candidates,
            executable_count=executable_count,
            rejected_count=rejected_count,
            insufficient_evidence_count=insufficient_count,
            ambiguous_count=ambiguous_count,
            weak_ltp_count=weak_ltp_count,
            start_time=start_time,
            end_time=end_time
        )
        
        if not dry_run:
            self.report_generator.generate_reports(summary, records)
            
        return summary
