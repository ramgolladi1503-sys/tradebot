from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
from pathlib import Path

QUEUE_PATH = Path("logs/review_queue.json")

def migrate():
    if not QUEUE_PATH.exists():
        print("No review queue file found.")
        return
    data = json.loads(QUEUE_PATH.read_text())
    if not data:
        print("Review queue empty.")
        return
    # Ensure keys exist
    defaults = {
        "side": None,
        "qty": None,
        "confidence": None,
        "regime": None,
    }
    for row in data:
        for k, v in defaults.items():
            row.setdefault(k, v)
    QUEUE_PATH.write_text(json.dumps(data, indent=2))
    print(f"Migrated {len(data)} queued trades.")

if __name__ == "__main__":
    migrate()
