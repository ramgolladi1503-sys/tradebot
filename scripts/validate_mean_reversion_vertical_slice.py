#!/usr/bin/env python3
import json
from pathlib import Path

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def main():
    strat_id = "MEAN_REVERSION_EXTENSION"
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    catalog_path = base_dir / "historical_data_catalog.json"

    catalog = {}
    if catalog_path.exists():
        with open(catalog_path, "r") as f:
            catalog = json.load(f)
            
    dates_available = catalog.get("date_range_found", [])
    has_sufficient_backtest = len(dates_available) >= 30
    
    thresholds_path = Path("configs/candidate_strategy_validation_thresholds.json")
    thresholds = {}
    if thresholds_path.exists():
        with open(thresholds_path, "r") as f:
            thresholds = json.load(f)
            
    minimum_wfa_windows = thresholds.get("minimum_wfa_windows", 6)
    min_trades = thresholds.get("min_trades", 30)

    # Phase 4: Backtest
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    trades = []
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))
                    
    passed_p4 = False
    verdict_p4 = "BLOCKED"
    blockers_p4 = []
    
    if not has_sufficient_backtest:
        blockers_p4.append("INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA")
    elif not trades:
        blockers_p4.append("PHASE4_TRADE_LEDGER_MISSING_OR_EMPTY")
    elif len(trades) < min_trades:
        blockers_p4.append("MINIMUM_TRADE_COUNT_NOT_MET")
    else:
        # Calculate real metrics from ledger if it existed and had enough trades
        passed_p4 = True
        verdict_p4 = "PASSED"
        
    if not passed_p4:
        write_json(base_dir / "phase_4_report.json", {
            "passed": passed_p4,
            "verdict": verdict_p4,
            "blockers": blockers_p4,
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False
        })
    else:
        pass

    # Phase 5: WFA
    wfa_windows_passed = 0
    wfa_windows_failed = 0
    passed_p5 = False
    verdict_p5 = "BLOCKED"
    blockers_p5 = []
    
    if not passed_p4:
        blockers_p5.append("PHASE4_NOT_PASSED")
        
    if wfa_windows_passed + wfa_windows_failed < minimum_wfa_windows:
        blockers_p5.append("MINIMUM_WFA_WINDOWS_NOT_MET")
        
    if passed_p4 and (wfa_windows_passed + wfa_windows_failed >= minimum_wfa_windows):
        passed_p5 = True
        verdict_p5 = "PASSED"

    if not passed_p5:
        write_json(base_dir / "phase_5_wfa_report.json", {
            "passed": passed_p5,
            "verdict": verdict_p5,
            "phase6_shadow_candidate": False,
            "blockers": blockers_p5,
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False
        })
    else:
        pass

    # Phase 6: Shadow Candidate
    if passed_p5:
        write_json(base_dir / "phase6_shadow_candidate_report.json", {
            "classification": "PHASE6_SHADOW_CANDIDATE_READY",
            "shadow_observation_only": True,
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False,
            "blockers": []
        })
    else:
        write_json(base_dir / "phase6_shadow_candidate_report.json", {
            "classification": "NOT_PHASE6_READY",
            "phase6_shadow_candidate": False,
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False,
            "blockers": ["PHASE5_WFA_NOT_PASSED"]
        })
    
    print(f"Validated Phase 4 and Phase 5 vertical slice for {strat_id}")

if __name__ == "__main__":
    main()
