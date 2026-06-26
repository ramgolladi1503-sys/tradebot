import json

def run():
    target_id = "NIFTY-2026-06-16-23800-PE-mean-reversion-1781512764"
    with open(".runtime/logs/suggestions.jsonl", "r") as f:
        for line in f:
            if target_id in line:
                try:
                    c = json.loads(line)
                    time_ist = c.get("ts_ist", c.get("decision_trace", {}).get("ts_ist", "Unknown Time"))
                    levels = c.get("levels", {})
                    
                    entry = levels.get("entry")
                    if entry is None:
                        entry = c.get("final_entry")
                        
                    print(f"Time (IST): {time_ist}")
                    print(f"Entry Price: {entry}")
                    print(f"Stoploss: {levels.get('stoploss')}")
                    print(f"Target: {levels.get('target')}")
                except Exception as e:
                    print(f"Error parsing JSON: {e}")
                break
run()
