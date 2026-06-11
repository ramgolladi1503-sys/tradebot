import re

def search(filepath, keywords):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                print(f"{filepath}:{i+1}: {line.strip()}")

search("core/feed_execution_truth.py", ["feed_truth_allows_live_selection"])
