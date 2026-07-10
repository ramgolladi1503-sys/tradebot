#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path

CANDIDATE_STRATEGIES = [
    "MEAN_REVERSION_EXTENSION", "COMPRESSION_BREAKOUT", "TREND_PULLBACK",
    "VWAP_RECLAIM", "OPENING_DRIVE", "FAILED_BREAKOUT_TRAP",
    "EXHAUSTION_REVERSAL", "EVENT_VOLATILITY_EXPANSION", "LATE_DAY_MOMENTUM",
    "OPTION_PRESSURE", "OPENING_RANGE_BREAKOUT", "NO_TRADE_CHOP"
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-candidate-generators", action="store_true")
    args = parser.parse_args()

    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cap_path = out_dir / "historical_data_capability.json"
    if cap_path.exists():
        with open(cap_path, "r") as f:
            cap = json.load(f)
    else:
        cap = {"classification": "HISTORICAL_DATA_CAPABILITY_BLOCKED", "is_candle_only": True}

    for strat in CANDIDATE_STRATEGIES:
        is_candle_only = cap.get("is_candle_only", True)
        
        # Option pressure explicitly requires depth/pressure.
        if strat == "OPTION_PRESSURE" and is_candle_only:
            passed = False
            verdict = "BLOCKED"
            wfa_allowed = False
        else:
            # Other strategies can do research WFA on candle data
            passed = cap.get("token_present", False)
            verdict = "PASSED_FOR_RESEARCH" if passed else "BLOCKED"
            wfa_allowed = passed
            
        report = {
            "strategy_id": strat,
            "phase": "phase_2",
            "phase_name": "historical_data_coverage",
            "passed": passed,
            "verdict": verdict,
            "wfa_mode_allowed": "CANDLE_LEVEL_RESEARCH_WFA" if wfa_allowed else "NONE",
            "stress_replay_allowed": False, # Candle only blocks stress replay
            "required_data": ["underlying_candles"],
            "available_data": ["underlying_candles"] if cap.get("underlying_candle_availability") else [],
            "missing_data": ["bid_ask", "depth"] if is_candle_only else [],
            "usable_date_ranges": [],
            "blockers": ["Missing bid/ask and depth"] if is_candle_only else [],
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False
        }
        
        strat_dir = out_dir / strat
        strat_dir.mkdir(parents=True, exist_ok=True)
        
        with open(strat_dir / "phase_2_report.json", "w") as f:
            json.dump(report, f, indent=2)
            
    print("Phase 2 Data Coverage Audit complete.")

if __name__ == "__main__":
    main()
