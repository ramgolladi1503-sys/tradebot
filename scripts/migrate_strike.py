from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import re
from pathlib import Path

QUEUE_FILES = [
    Path("logs/review_queue.json"),
    Path("logs/quick_review_queue.json"),
    Path("logs/zero_hero_queue.json"),
    Path("logs/scalp_queue.json"),
]


def infer_strike(trade_id: str):
    if not trade_id:
        return None
    if "ATM" in trade_id:
        return "ATM"
    m = re.search(r"-(CE|PE)-(\d{3,6})(?:-|$)", trade_id)
    if m:
        return int(m.group(2))
    m = re.search(r"-(\d{3,6})-(CE|PE)(?:-|$)", trade_id)
    if m:
        return int(m.group(1))
    return None


def migrate_file(path: Path):
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
    except Exception:
        return 0
    if not isinstance(data, list):
        return 0
    updated = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        if row.get("strike") not in (None, "", 0):
            continue
        strike = infer_strike(row.get("trade_id", ""))
        if strike is not None:
            row["strike"] = strike
            updated += 1
    if updated:
        path.write_text(json.dumps(data, indent=2))
    return updated


if __name__ == "__main__":
    total = 0
    for f in QUEUE_FILES:
        total += migrate_file(f)
    print(f"Migrated strike for {total} entries.")
