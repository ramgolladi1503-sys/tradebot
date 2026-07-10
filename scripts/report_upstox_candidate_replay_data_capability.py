#!/usr/bin/env python3
import json
from pathlib import Path

def main():
    strategies = [
        "MEAN_REVERSION_EXTENSION",
        "COMPRESSION_BREAKOUT",
        "TREND_PULLBACK",
        "VWAP_RECLAIM",
        "OPENING_DRIVE",
        "FAILED_BREAKOUT_TRAP",
        "EXHAUSTION_REVERSAL",
        "EVENT_VOLATILITY_EXPANSION",
        "LATE_DAY_MOMENTUM",
        "OPTION_PRESSURE",
        "OPENING_RANGE_BREAKOUT",
        "NO_TRADE_CHOP"
    ]
    
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    reports = []
    
    for strat in strategies:
        report = {
          "strategy_id": strat,
          "strategy_kind": "candidate_generator_strategy",
          "contract_audit_status": "CANDIDATE_GENERATOR_CONTRACT_PASSED",
          "data_capability": "UPSTOX_OPTION_CANDLE_ONLY",
          "required_data": [
            "underlying candles",
            "option LTP",
            "option bid/ask",
            "option depth",
            "instrument metadata",
            "expiry/strike/option_type"
          ],
          "available_data": [
            "underlying candles",
            "option LTP",
            "instrument metadata",
            "expiry/strike/option_type"
          ],
          "missing_data": [
            "option bid/ask",
            "option depth"
          ],
          "replay_allowed": False,
          "replay_blockers": ["MISSING_OPTION_BID_ASK", "MISSING_OPTION_DEPTH", "STRESS_REPLAY_REQUIRES_DEPTH"],
          "paper_live_allowed": False,
          "live_allowed": False,
          "broker_order_allowed": False,
          "execution_allowed": False
        }
        reports.append(report)
        
    with open(out_dir / "upstox_candidate_replay_data_capability.json", "w") as f:
        json.dump(reports, f, indent=2)
        
    md = ["# Upstox Candidate Replay Data Capability Report"]
    for r in reports:
        md.append(f"## {r['strategy_id']}")
        md.append(f"- Data Capability: {r['data_capability']}")
        md.append(f"- Replay Allowed: {r['replay_allowed']}")
        md.append(f"- Replay Blockers: {r['replay_blockers']}")
        md.append("")
        
    with open(out_dir / "upstox_candidate_replay_data_capability.md", "w") as f:
        f.write("\n".join(md) + "\n")
        
if __name__ == "__main__":
    main()
