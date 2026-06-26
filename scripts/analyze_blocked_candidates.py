import json
import glob
from pathlib import Path

def run():
    files = glob.glob(".runtime/logs/suggestions*.jsonl")
    if not files:
        print("No suggestions logs found.")
        return
        
    for file in files:
        print(f"Analyzing {file}...")
        candidates = []
        with open(file, "r") as f:
            for line in f:
                try:
                    c = json.loads(line)
                    candidates.append(c)
                except:
                    pass
                    
        # find top blocked
        blocked = [c for c in candidates if c.get("decision", {}).get("status_raw") in ["blocked", "PLANNING", "advisory_only", "QUEUE_ONLY"] or c.get("decision", {}).get("permission_base") == "QUEUE_ONLY"]
        
        print(f"Total candidates: {len(candidates)}, Blocked: {len(blocked)}")
        
        # print some info about top ones
        for c in blocked[-5:]:
            sym = c.get("symbol", "UNKNOWN")
            adv_id = c.get("advisory_id", "UNKNOWN")
            decision = c.get("decision", {})
            levels = c.get("levels", {})
            entry = levels.get("entry")
            print(f"ID: {adv_id} | Blockers: {decision.get('blockers', [])} | Entry: {entry}")

if __name__ == "__main__":
    run()
