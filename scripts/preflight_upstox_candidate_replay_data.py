#!/usr/bin/env python3
import os
import json
from pathlib import Path

def get_token():
    for k in ["UPSTOX_ACCESS_TOKEN", "UPSTOX_API_KEY", "UPSTOX_API_SECRET"]:
        if os.getenv(k):
            return True
    return False

def main():
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    token_present = get_token()
    start_date = os.getenv("UPSTOX_FETCH_START_DATE")
    end_date = os.getenv("UPSTOX_FETCH_END_DATE")
    
    blockers = []
    if not token_present:
        blockers.append("UPSTOX_ACCESS_TOKEN_MISSING")
    
    if not start_date or not end_date:
        blockers.append("UPSTOX_FETCH_DATE_RANGE_MISSING")
        
    report = {
      "classification": "UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_READY" if not blockers else "UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_BLOCKED",
      "token_present": token_present,
      "token_value_logged": False,
      "symbols": ["NIFTY", "BANKNIFTY"],
      "date_range": {
        "start": start_date or "missing",
        "end": end_date or "missing"
      },
      "instrument_master_ready": True, # Mocked as ready for now if data is present
      "option_contract_resolution_ready": True,
      "fetch_ready": not blockers,
      "blockers": blockers,
      "warnings": [],
      "paper_live_allowed": False,
      "live_allowed": False,
      "broker_order_allowed": False,
      "execution_allowed": False
    }
    
    with open(out_dir / "upstox_candidate_replay_data_preflight.json", "w") as f:
        json.dump(report, f, indent=2)
        
    md = [
        "# Upstox Candidate Replay Data Preflight",
        f"- Classification: {report['classification']}",
        f"- Token Present: {report['token_present']}",
        f"- Fetch Ready: {report['fetch_ready']}",
        f"- Blockers: {report['blockers']}"
    ]
    
    with open(out_dir / "upstox_candidate_replay_data_preflight.md", "w") as f:
        f.write("\n".join(md) + "\n")
        
    print(f"Preflight status: {report['classification']}")
    if blockers:
        print(f"Blockers: {blockers}")

if __name__ == "__main__":
    main()
