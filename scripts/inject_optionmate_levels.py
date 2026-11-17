#!/usr/bin/env python3
"""
OptionMate Level Injector CLI
=============================
Sets and persists exact OptionMate indicator levels for TradeBot/Sentinel:
- Saves to `runtime/optionmate_daily_levels.json`.
- Can be run manually every morning:
    python3 scripts/inject_optionmate_levels.py --nifty-td 25283 --nifty-rp1-u 25360 --nifty-rp2-u 25424.65 --nifty-rp1-l 25195 --nifty-rp2-l 25134
- Or called via JSON:
    python3 scripts/inject_optionmate_levels.py --json '{"NIFTY": {"trend_decider": 25283, "rp1_upper": 25360, "rp2_upper": 25424.65, "rp1_lower": 25195, "rp2_lower": 25134}}'
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / "runtime"
LEVELS_FILE = RUNTIME_DIR / "optionmate_daily_levels.json"


def save_levels(levels_dict: dict) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Format and enrich with timestamp
    for k, v in levels_dict.items():
        if isinstance(v, dict):
            v.setdefault("date", today_str)
            v.setdefault("updated_at", datetime.now().isoformat())

    with open(LEVELS_FILE, "w", encoding="utf-8") as f:
        json.dump(levels_dict, f, indent=2)
    
    print(f"✅ Successfully persisted OptionMate daily levels to {LEVELS_FILE}")
    for idx, lvl in levels_dict.items():
        if isinstance(lvl, dict):
            print(f"  [{idx}] TD: {lvl.get('trend_decider')} | RP1_U: {lvl.get('rp1_upper')} | RP2_U: {lvl.get('rp2_upper')} | RP1_L: {lvl.get('rp1_lower')} | RP2_L: {lvl.get('rp2_lower')}")
    return LEVELS_FILE


def main():
    parser = argparse.ArgumentParser(description="Inject OptionMate Indicator Levels into TradeBot")
    parser.add_argument("--json", type=str, help="Full JSON string of levels")
    parser.add_argument("--file", type=str, help="Path to JSON file with levels")
    parser.add_argument("--index", type=str, default="NIFTY", help="Target index (NIFTY, SENSEX, BANKNIFTY)")
    parser.add_argument("--td", type=float, help="Trend Decider price")
    parser.add_argument("--rp1-u", type=float, help="RP1 Upper Reversal price")
    parser.add_argument("--rp2-u", type=float, help="RP2 Upper Reversal price")
    parser.add_argument("--rp1-l", type=float, help="RP1 Lower Reversal price")
    parser.add_argument("--rp2-l", type=float, help="RP2 Lower Reversal price")
    args = parser.parse_args()

    levels_data = {}
    if LEVELS_FILE.exists():
        try:
            with open(LEVELS_FILE, "r") as f:
                levels_data = json.load(f)
        except Exception:
            levels_data = {}

    if args.json:
        data = json.loads(args.json)
        if "trend_decider" in data:
            levels_data[args.index] = data
        else:
            levels_data.update(data)
    elif args.file:
        with open(args.file, "r") as f:
            data = json.load(f)
        levels_data.update(data)
    elif args.td is not None:
        if None in (args.rp1_u, args.rp2_u, args.rp1_l, args.rp2_l):
            print("Error: When specifying --td, you must also provide --rp1-u, --rp2-u, --rp1-l, and --rp2-l", file=sys.stderr)
            sys.exit(1)
        levels_data[args.index] = {
            "trend_decider": args.td,
            "rp1_upper": args.rp1_u,
            "rp2_upper": args.rp2_u,
            "rp1_lower": args.rp1_l,
            "rp2_lower": args.rp2_l,
        }
    else:
        # Default prompt / display current
        if levels_data:
            print("Current Saved OptionMate Levels:")
            print(json.dumps(levels_data, indent=2))
            return
        else:
            parser.print_help()
            return

    save_levels(levels_data)


if __name__ == "__main__":
    main()
