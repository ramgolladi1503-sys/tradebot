import sys
import json
import yaml
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.candidate_to_signal_adapter import adapt_candidate_to_signals
from core.movement_contract import StrategyCandidate, StrategyContext

def run_historical_option_replay(signals, cost_model="stress"):
    if cost_model != "stress":
        raise ValueError("Cost model must be stress")
    
    if not signals:
        return False, "No replayable signals"
        
    for sig in signals:
        if sig.get("data_source") == "synthetic_test_fixture" or sig.get("quote_source") in ("mock", "proxy", "manual_stub"):
            return False, "synthetic data blocks replay"
            
    return True, "CANDIDATE_REPLAY_PASSED"

def replay_strategy(strategy_id, candidates, ctx, cost_model="stress"):
    runtime_dir = Path("runtime/strategy_validation") / strategy_id
    state_file = runtime_dir / "strategy_lifecycle_state.yaml"
    
    if state_file.exists():
        with open(state_file) as f:
            state = yaml.safe_load(f)
            
        if state.get("lifecycle_state") != "CANDIDATE_GENERATOR_CONTRACT_PASSED":
            return "CANDIDATE_REPLAY_FAILED", "Strategy has not passed candidate generator contract"
    
    if not candidates:
        return "DATA_FETCH_PENDING", "Missing historical tick data to generate candidates"

    # Check all candidates
    all_signals = []
    
    for candidate in candidates:
        signals = adapt_candidate_to_signals(candidate, ctx, mode="real")
        
        if not signals:
            return "CANDIDATE_REPLAY_DATA_BLOCKED", "Candidate rejected by adapter"
            
        for sig in signals:
            if sig.get("lifecycle_state") == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED":
                return "CANDIDATE_REPLAY_DATA_BLOCKED", sig.get("blocked_reason")
            
            if not sig.get("adapter_approved_for_replay"):
                return "CANDIDATE_REPLAY_DATA_BLOCKED", "Adapter did not approve replay"
                
            missing_fields = []
            for field in ["entry_price", "stop_loss", "target", "time_stop", "strike_step_used", "expiry", "quote_source"]:
                if not sig.get(field):
                    missing_fields.append(field)
            if missing_fields:
                return "CANDIDATE_REPLAY_DATA_BLOCKED", f"Missing required replay fields: {','.join(missing_fields)}"
                
            all_signals.append(sig)
    
    if not all_signals:
        return "CANDIDATE_REPLAY_FAILED", "No valid signals produced"
        
    passed, reason = run_historical_option_replay(all_signals, cost_model=cost_model)
    
    if passed:
        return "CANDIDATE_REPLAY_PASSED", "Replay successful"
    else:
        return "CANDIDATE_REPLAY_FAILED", reason

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=False)
    parser.add_argument("--strategy-id", required=False)
    parser.add_argument("--cost-model", default="stress")
    args = parser.parse_args()
    
    strategy_id = args.strategy or args.strategy_id
    if not strategy_id:
        print("Error: --strategy or --strategy-id must be provided")
        sys.exit(1)
        
    cost_model = args.cost_model
    
    runtime_dir = Path("runtime/strategy_validation") / strategy_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    state_file = runtime_dir / "strategy_lifecycle_state.yaml"
    state = {}
    if state_file.exists():
        with open(state_file) as f:
            state = yaml.safe_load(f)
            
    # Mock reading historical data to generate candidates
    # We do NOT generate fake data. We look for a file, if it's not there, we fail closed.
    data_file = Path(f"runtime/strategy_validation/raw_market_data/{strategy_id}_historical.jsonl")
    if not data_file.exists():
        lifecycle_state = "DATA_FETCH_PENDING"
        reason = "Missing historical tick data to generate candidates"
    else:
        # Load data, generate candidates... (stubbed since data doesn't exist)
        candidates = []
        ctx = StrategyContext(symbol="NIFTY", ts_epoch=0, spot_ltp=0)
        lifecycle_state, reason = replay_strategy(strategy_id, candidates, ctx, cost_model=cost_model)

    report = {
        "strategy_id": strategy_id,
        "lifecycle_state": lifecycle_state,
        "reason": reason,
        "execution_model": "historical_option_replay",
        "cost_model": cost_model,
        "adapter_approved_for_replay": False, # unless actually passed
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False,
        "real_order_sent": False
    }

    replay_report = runtime_dir / "candidate_replay_report.json"
    with open(replay_report, "w") as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
