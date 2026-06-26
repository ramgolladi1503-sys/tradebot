import json
import glob
from pathlib import Path

def get_latest_file(pattern):
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=lambda f: Path(f).stat().st_mtime)

def run():
    latest_ranked = get_latest_file(".runtime/logs/ranked_pipeline_runtime_*.jsonl")
    if not latest_ranked:
        print("No ranked pipeline logs found.")
        return

    # read the last line of the ranked pipeline log
    with open(latest_ranked, "r") as f:
        lines = f.readlines()
        if not lines:
            print("Ranked log is empty.")
            return
        last_line = json.loads(lines[-1])
        
    report = last_line.get("report", {})
    candidates = report.get("ranked_candidates", [])
    
    if not candidates:
        print("No candidates currently generated in the last cycle.")
        print(f"Reason: {report.get('phase2_reason', 'unknown')}")
        return
        
    print(f"Found {len(candidates)} candidates in the latest cycle:\n")
    for c in candidates:
        symbol = c.get("symbol", "UNKNOWN")
        right = c.get("right", "")
        strike = c.get("strike", "")
        # The candidates might be nested under 'decision' or similar
        decision = c.get("decision", {})
        levels = c.get("levels", {})
        
        entry = levels.get("entry", "N/A")
        sl = levels.get("stoploss", "N/A")
        tg = levels.get("target", "N/A")
        
        action = decision.get("final_action", "UNKNOWN")
        status = decision.get("status_raw", "UNKNOWN")
        
        print(f"[{action}] {symbol} {strike} {right} | Entry: {entry} | SL: {sl} | Target: {tg} | Status: {status}")

if __name__ == "__main__":
    run()
