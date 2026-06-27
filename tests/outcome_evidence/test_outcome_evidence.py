import json
import tempfile
from pathlib import Path
from core.outcome_evidence.evidence_models import ReplayCandidate, OptionTracePoint
from core.outcome_evidence.evidence_types import EvidenceQuality, OutcomeStatus, ExitReason, CostModelStatus
from core.outcome_evidence.candidate_loader import CandidateLoader
from core.outcome_evidence.option_trace_adapter import OptionTraceAdapter
from core.outcome_evidence.outcome_resolver import OutcomeResolver
from core.outcome_evidence.mfe_mae import MfeMaeCalculator
from core.outcome_evidence.cost_model import IndianIndexOptionsCostModel
from core.outcome_evidence.execution_simulator import ExecutionSimulator
from core.outcome_evidence.regime_context import RegimeContextLoader
from core.outcome_evidence.evidence_store import OutcomeEvidenceStore


def test_candidate_loader_complete():
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f.write(json.dumps({
            "candidate_id": "c1",
            "strategy_id": "s1",
            "timestamp_epoch": 1000.0,
            "instrument_id": "BANKNIFTY24DEC50000CE",
            "entry": 100.0,
            "target": 120.0,
            "stop": 90.0,
            "execution_ok": True
        }) + "\n")
        f_path = f.name
        
    loader = CandidateLoader(Path(f_path))
    cands = list(loader.load_jsonl())
    assert len(cands) == 1
    cand = cands[0]
    assert cand.candidate_id == "c1"
    assert cand.entry_price == 100.0
    assert cand.target_price == 120.0
    assert cand.stop_price == 90.0
    assert cand.execution_ok is True
    assert cand.evidence_quality == EvidenceQuality.COMPLETE
    
    Path(f_path).unlink()


def test_candidate_loader_missing_fields_no_fake():
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f.write(json.dumps({
            "candidate_id": "c2",
            "strategy_id": "s1"
        }) + "\n")
        f_path = f.name
        
    loader = CandidateLoader(Path(f_path))
    cand = list(loader.load_jsonl())[0]
    assert cand.entry_price == 0.0
    assert cand.target_price == 0.0
    assert cand.stop_price == 0.0
    assert cand.evidence_quality == EvidenceQuality.INSUFFICIENT
    
    Path(f_path).unlink()


def test_option_trace_adapter_alignment():
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        for t in [900, 1000, 1100]:
            f.write(json.dumps({"timestamp": t, "ltp": 100.0}) + "\n")
        f_path = f.name
        
    adapter = OptionTraceAdapter(Path(f_path))
    tick = adapter.get_nearest_forward_tick(950)
    assert tick is not None
    assert tick.timestamp == 1000
    
    tick = adapter.get_nearest_forward_tick(1150)
    assert tick is None
    
    Path(f_path).unlink()


def test_outcome_resolver_target_hit():
    resolver = OutcomeResolver()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120)
    
    traces = [
        OptionTracePoint(1000, 100),
        OptionTracePoint(1005, 110),
        OptionTracePoint(1010, 125)
    ]
    
    outcome = resolver.resolve(cand, traces)
    assert outcome.status == OutcomeStatus.TARGET_HIT
    assert outcome.exit_reason == ExitReason.TARGET


def test_outcome_resolver_stop_hit():
    resolver = OutcomeResolver()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120)
                           
    traces = [
        OptionTracePoint(1000, 100),
        OptionTracePoint(1005, 95),
        OptionTracePoint(1010, 85)
    ]
    
    outcome = resolver.resolve(cand, traces)
    assert outcome.status == OutcomeStatus.STOP_HIT
    assert outcome.exit_reason == ExitReason.STOP


def test_outcome_resolver_ambiguous_both_hit():
    resolver = OutcomeResolver()
    
    # E.g. a huge candle where high > target and low < stop in the exact same tick
    
    # We simulate Both Hit if a trace point triggers both simultaneously in logic.
    # In the current logic, we just check cross. Since the price went to 130, it didn't cross 90.
    # If the price was somehow evaluated such that both were true at the exact same tick.
    # Let's say target=100, stop=100.
    cand2 = ReplayCandidate(candidate_id="2", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=100, target_price=100)
    traces2 = [OptionTracePoint(1000, 100)]
    outcome = resolver.resolve(cand2, traces2)
    assert outcome.status == OutcomeStatus.AMBIGUOUS_BOTH_HIT


def test_outcome_resolver_no_trace_data():
    resolver = OutcomeResolver()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120)
    outcome = resolver.resolve(cand, [])
    assert outcome.status == OutcomeStatus.NO_TRACE_DATA


def test_outcome_resolver_time_stop():
    resolver = OutcomeResolver()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120, time_stop=1010)
    traces = [
        OptionTracePoint(1000, 100),
        OptionTracePoint(1005, 105),
        OptionTracePoint(1010, 108)
    ]
    outcome = resolver.resolve(cand, traces)
    assert outcome.status == OutcomeStatus.TIME_STOP


def test_mfe_mae_calculator():
    calc = MfeMaeCalculator()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120)
    traces = [
        OptionTracePoint(1000, 100),
        OptionTracePoint(1005, 115), # MFE
        OptionTracePoint(1010, 95)   # MAE
    ]
    mfe_mae = calc.calculate(cand, traces, exit_time=1010)
    assert mfe_mae is not None
    assert mfe_mae.mfe_points == 15.0
    assert mfe_mae.mae_points == 5.0


def test_cost_model():
    model = IndianIndexOptionsCostModel(default_slippage_points=0.5, default_spread_points=0.5)
    cost = model.calculate(100.0, 110.0, 15, bid_ask_spread=1.0)
    assert cost.total_cost > 0
    assert cost.status == CostModelStatus.COMPLETE
    
    cost2 = model.calculate(100.0, 110.0, 15, bid_ask_spread=None)
    assert cost2.status == CostModelStatus.ESTIMATED


def test_execution_simulator():
    sim = ExecutionSimulator()
    cand = ReplayCandidate(candidate_id="1", strategy_id="s", timestamp=1000, instrument_id="i", underlying="u",
                           entry_price=100, stop_price=90, target_price=120, execution_ok=False)
                           
    entry_tick = OptionTracePoint(1000, 100, bid=99, ask=101)
    res = sim.simulate(cand, entry_tick, None)
    
    assert res.entry_fill == 101 # Hits ask for long entry
    assert res.spread_impact == 2.0
    assert res.is_hypothetical_rejected is True


def test_regime_context_missing():
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f_path = f.name
        
    loader = RegimeContextLoader(Path(f_path))
    ctx = loader.get_context_at(1000)
    assert ctx.trend is None
    
    Path(f_path).unlink()


def test_evidence_store_jsonl():
    with tempfile.TemporaryDirectory() as td:
        store = OutcomeEvidenceStore(Path(td))
        from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord, ExecutionSimulation, CostBreakdown
        
        rec = OutcomeEvidenceRecord(
            run_id="r1", candidate_id="1", strategy_id="s", input_source="", 
            evidence_quality=EvidenceQuality.COMPLETE, outcome_status=OutcomeStatus.TARGET_HIT, 
            exit_reason=ExitReason.TARGET, mfe_mae=None, 
            cost_breakdown=CostBreakdown(0,0,0,0,0,0,0,0,0,15,CostModelStatus.COMPLETE),
            gross_pnl=10.0, net_pnl=9.0, regime_context=None,
            simulation=ExecutionSimulation(0,0,0,0,False,False,False), warnings=[], created_timestamp=1000
        )
        store.save_records([rec])
        
        with open(Path(td) / "outcome_evidence.jsonl") as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["outcome_status"] == "TARGET_HIT"
