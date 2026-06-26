import json
from pathlib import Path
from datetime import datetime

def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except:
        return {}

feed_health = load_json(".runtime/logs/feed_runtime_latest.json")
engine_status = load_json(".runtime/logs/engine_cycle_status.json")
suggestions = load_json(".runtime/logs/suggestions_status.json")

print(f"--- Live Monitor Update at {datetime.now().strftime('%H:%M:%S')} ---")

# Feed Health
ws_connected = feed_health.get("ws_connected", False)
feed_fresh = feed_health.get("feed_fresh", False)
ltp_age = feed_health.get("latest_ltp_age_sec", "N/A")
print(f"Feed Health: WS Connected: {ws_connected} | Fresh: {feed_fresh} | LTP Age: {ltp_age}s")

# Engine Status
feed_ok = engine_status.get("feed_ok", False)
cycle_stage = engine_status.get("cycle_stage", "unknown")
primary_blocker = engine_status.get("primary_blocker", "None")
print(f"Engine Status: Feed OK: {feed_ok} | Stage: {cycle_stage} | Blocker: {primary_blocker}")

# Candidates
status = suggestions.get("status", "unknown")
suggestion_count = suggestions.get("visible_suggestion_count", 0)
reason = suggestions.get("reason", "")
print(f"Candidates: Status: {status} | Suggestions: {suggestion_count} | Reason: {reason}")
if suggestion_count == 0:
    print("No valid candidates generated this cycle.")
else:
    print(f"Found {suggestion_count} candidates!")

