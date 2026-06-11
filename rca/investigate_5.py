import re

def search(filepath, keywords):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                print(f"{filepath}:{i+1}: {line.strip()}")

search("core/feed_zombie_state.py", ["zombie", "stale"])
search("core/feed_health_truth.py", ["feed_ok", "reason", "option_age_missing", "feed_state_unsafe"])
