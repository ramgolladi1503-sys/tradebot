import re

def search(filepath, keywords):
    print(f"Searching {filepath} for keywords: {keywords}")
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                pass
                #print(f"{i+1}: {line.strip()}")

search("core/kite_depth_ws.py", ["stale", "1006", "process_restart", "healthy", "block_reconnect"])
search("core/feed_health_truth.py", ["healthy", "stale", "feed_ok"])
search("core/feed_runtime.py", ["restart", "recover"])
