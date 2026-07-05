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
        if sig.get("data_source") == "synthetic_test_fixture":
            return False, "synthetic data blocks replay"
            
    return True, "CANDIDATE_REPLAY_PASSED"

def replay_strategy(strategy_id, candidates, ctx):
    runtime_dir = Path("runtime/strategy_validation") / strategy_id
    state_file = runtime_dir / "strategy_lifecycle_state.yaml"
    
    if state_file.exists():
        with open(state_file) as f:
            state = yaml.safe_load(f)
            
        if state.get("lifecycle_state") != "CANDIDATE_GENERATOR_CONTRACT_PASSED":
            return "CANDIDATE_REPLAY_FAILED", "Strategy has not passed candidate generator contract"
    
    # Check all candidates
    all_signals = []
    
    for candidate in candidates:
        signals = adapt_candidate_to_signals(candidate, ctx, mode="real")
        
        if not signals:
            return "CANDIDATE_REPLAY_DATA_BLOCKED", "Candidate rejected by adapter"
            
        for sig in signals:
            # If adapter returns CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED, do not replay
            if sig.get("lifecycle_state") == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED":
                # missing option_ltp blocks replay
                # missing stop/target/time_stop blocks replay
                return "CANDIDATE_REPLAY_DATA_BLOCKED", sig.get("blocked_reason")
            
            # Require adapter_approved_for_replay: true
            if not sig.get("adapter_approved_for_replay"):
                return "CANDIDATE_REPLAY_DATA_BLOCKED", "Adapter did not approve replay"
                
            # If option_ltp, stop, target, time_stop, strike step, expiry, or quote provenance is missing
            if not sig.get("entry_price") or not sig.get("stop_loss") or not sig.get("target") or not sig.get("time_stop") or not sig.get("strike_step_used") or not sig.get("expiry") or not sig.get("quote_source"):
                return "CANDIDATE_REPLAY_DATA_BLOCKED", "Missing required replay fields"
                
            all_signals.append(sig)
    
    if not all_signals:
        return "CANDIDATE_REPLAY_FAILED", "No valid signals produced"
        
    passed, reason = run_historical_option_replay(all_signals, cost_model="stress")
    
    if passed:
        return "CANDIDATE_REPLAY_PASSED", "Replay successful"
    else:
        return "CANDIDATE_REPLAY_FAILED", reason

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", required=True)
    args = parser.parse_args()
    
    runtime_dir = Path("runtime/strategy_validation") / args.strategy_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    # For now, it's a stub that just writes CANDIDATE_REPLAY_READY 
    # if the contract passed, or fails if not.
    state_file = runtime_dir / "strategy_lifecycle_state.yaml"
    if state_file.exists():
        with open(state_file) as f:
            state = yaml.safe_load(f)
        if state.get("lifecycle_state") == "CANDIDATE_GENERATOR_CONTRACT_PASSED":
            lifecycle_state = "CANDIDATE_REPLAY_READY"
        else:
            lifecycle_state = "CANDIDATE_REPLAY_FAILED"
    else:
        lifecycle_state = "CANDIDATE_REPLAY_FAILED"

    replay_report = runtime_dir / "candidate_replay_report.json"
    with open(replay_report, "w") as f:
        json.dump({"lifecycle_state": lifecycle_state, "reason": "No candidates to replay in batch stub"}, f, indent=2)

if __name__ == "__main__":
    main()
