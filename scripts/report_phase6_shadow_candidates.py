#!/usr/bin/env python3
import os
import json
from pathlib import Path

CANDIDATE_STRATEGIES = [
    "MEAN_REVERSION_EXTENSION", "COMPRESSION_BREAKOUT", "TREND_PULLBACK",
    "VWAP_RECLAIM", "OPENING_DRIVE", "FAILED_BREAKOUT_TRAP",
    "EXHAUSTION_REVERSAL", "EVENT_VOLATILITY_EXPANSION", "LATE_DAY_MOMENTUM",
    "OPTION_PRESSURE", "OPENING_RANGE_BREAKOUT", "NO_TRADE_CHOP"
]

def main():
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    shadow_candidates = []
    
    for strat in CANDIDATE_STRATEGIES:
        strat_dir = out_dir / strat
        wfa_path = strat_dir / "phase_5_wfa_report.json"
        if wfa_path.exists():
            with open(wfa_path, "r") as f:
                report = json.load(f)
                if report.get("phase6_shadow_candidate") is True:
                    shadow_candidates.append({
                        "strategy_id": strat,
                        "phase5_wfa_passed": True,
                        "execution_grade": False,
                        "shadow_observation_only": True,
                        "paper_live_allowed": False,
                        "live_allowed": False,
                        "broker_order_allowed": False,
                        "execution_allowed": False
                    })

    if shadow_candidates:
        classification = "PHASE6_SHADOW_CANDIDATES_READY"
    else:
        classification = "PHASE6_SHADOW_CANDIDATES_EMPTY"

    final_report = {
        "classification": classification,
        "capture_date": "next_trading_day",
        "required_live_evidence": [
            "real candles",
            "real option-chain snapshots",
            "real option quotes",
            "real spread",
            "real depth if available",
            "real_order_sent=false",
            "no broker orders",
            "live_shadow_report.json"
        ],
        "strategies": shadow_candidates
    }
    
    json_path = out_dir / "phase6_shadow_candidates_for_next_live_capture.json"
    md_path = out_dir / "phase6_shadow_candidates_for_next_live_capture.md"
    
    with open(json_path, "w") as f:
        json.dump(final_report, f, indent=2)
        
    with open(md_path, "w") as f:
        f.write("# Phase 6 Shadow Candidates\n\n")
        f.write(f"**Classification**: {classification}\n")
        for sc in shadow_candidates:
            f.write(f"- {sc['strategy_id']}\n")

    # Readiness report
    readiness = {
        "status": "READY" if shadow_candidates else "BLOCKED",
        "selected_candidates": len(shadow_candidates),
        "real_candle_feed_required": True,
        "real_option_chain_snapshot_required": True,
        "real_option_quotes_required": True,
        "spread_depth_capture_required": True,
        "real_order_sent": False,
        "broker_order_path_active": False,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }
    
    with open(out_dir / "next_live_capture_readiness_for_phase6.json", "w") as f:
        json.dump(readiness, f, indent=2)
        
    with open(out_dir / "next_live_capture_readiness_for_phase6.md", "w") as f:
        f.write("# Next Live Capture Readiness for Phase 6\n\n")
        f.write(f"**Status**: {readiness['status']}\n")

    print(f"Phase 6 report generated. {len(shadow_candidates)} candidates ready.")

if __name__ == "__main__":
    main()
