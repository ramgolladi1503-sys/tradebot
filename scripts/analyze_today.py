import json
import glob

def run():
    for file in glob.glob(".runtime/logs/*.jsonl"):
        with open(file, "r") as f:
            for line in f:
                if "2026-06-23" in line and "levels" in line:
                    c = json.loads(line)
                    print(file, c.keys())
                    break
run()
