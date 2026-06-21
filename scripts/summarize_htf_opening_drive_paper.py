#!/usr/bin/env python3
"""
Summarize HTF OPENING_DRIVE_CONT paper validation telemetry.
"""
import json
from pathlib import Path
from collections import defaultdict

CANDIDATES_LOG = Path("runtime/paper/htf_opening_drive_candidates.jsonl")
EXITS_LOG = Path("runtime/paper/htf_opening_drive_exits.jsonl")

def summarize():
    print("=" * 60)
    print("HTF OPENING_DRIVE_CONT Paper Validation Telemetry")
    print("=" * 60)

    candidates = []
    if CANDIDATES_LOG.exists():
        with open(CANDIDATES_LOG, "r") as f:
            for line in f:
                if line.strip():
                    candidates.append(json.loads(line))
    
    exits = []
    if EXITS_LOG.exists():
        with open(EXITS_LOG, "r") as f:
            for line in f:
                if line.strip():
                    exits.append(json.loads(line))
                    
    total_candidates = len(candidates)
    executable = [c for c in candidates if c.get("execution_ok") and not c.get("is_fallback") and not c.get("is_advisory")]
    stale_blocked = [c for c in candidates if c.get("is_stale") and not c.get("execution_ok")]
    
    print(f"Total Candidates Evaluated: {total_candidates}")
    print(f"Total Executable Paper Intent: {len(executable)}")
    print(f"Total Blocked (Stale Quotes): {len(stale_blocked)}")
    print(f"Total Exits Recorded: {len(exits)}")
    
    if exits:
        total_pnl = sum(e.get("realized_paper_pnl", 0.0) for e in exits)
        total_slippage = sum(e.get("slippage_estimate", 0.0) for e in exits)
        print("-" * 60)
        print(f"Total Realized Paper P&L: {total_pnl:.2f}")
        print(f"Total Estimated Slippage: {total_slippage:.2f}")
    
    print("=" * 60)

if __name__ == "__main__":
    summarize()
