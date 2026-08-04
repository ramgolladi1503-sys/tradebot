#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent))

from core.upstox_capture.subscription_planner import build_subscription_plan

def main():
    inst_master_path = Path("runtime/upstox_instruments/complete.json")
    date_str_dashed = datetime.now().strftime("%Y-%m-%d")
    run_id = datetime.now().strftime("%H%M%S")
    output_dir = Path("/Users/madhuram/tradebot/.runtime/market_data/upstox_replay_capture_v1") / date_str_dashed / run_id

    # Simple LTP fallback prices to build universe
    fallback_prices = {
        "NIFTY": 24500.0,
        "BANKNIFTY": 52200.0,
        "SENSEX": 80000.0
    }
    
    print(f"Building subscription plan at: {output_dir}")
    plan = build_subscription_plan(inst_master_path, output_dir, fallback_prices)
    print(f"Plan built. Keys: {len(plan['full'])} Full, {len(plan['ltpc'])} LTPC.")

if __name__ == "__main__":
    main()
