import re

def search(filepath, keywords):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                print(f"{filepath}:{i+1}: {line.strip()}")

search("core/kite_depth_ws.py", ["feed_ok"])
search("core/feed_runtime.py", ["feed_ok"])
search("core/runtime_health.py", ["feed_ok"])
