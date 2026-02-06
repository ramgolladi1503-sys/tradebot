from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import json
import sys
from datetime import datetime

if len(sys.argv) < 3:
    print("Usage: python scripts/update_trade_outcome.py <trade_id> <exit_price> [actual(1/0)]")
    sys.exit(1)

trade_id = sys.argv[1]
exit_price = float(sys.argv[2])
actual = int(sys.argv[3]) if len(sys.argv) > 3 else None
updated_entry = None

path = "data/trade_log.json"
updated = False
lines = []

with open(path, "r") as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("trade_id") == trade_id:
            entry["exit_price"] = exit_price
            entry["exit_time"] = str(datetime.now())
            if actual is None:
                # infer actual using R multiple
                entry_price = entry.get("entry", 0)
                stop = entry.get("stop_loss", 0)
                side = entry.get("side", "BUY")
                risk = abs(entry_price - stop) if stop else 0
                r_mult = 0
                if risk > 0:
                    if side == "BUY":
                        r_mult = (exit_price - entry_price) / risk
                    else:
                        r_mult = (entry_price - exit_price) / risk
                entry["actual"] = 1 if r_mult >= 1 else 0
                entry["r_multiple"] = round(r_mult, 3)
                entry["r_label"] = 1 if r_mult >= 1 else 0
            else:
                entry["actual"] = actual
            updated = True
            updated_entry = entry
        lines.append(json.dumps(entry))

if not updated:
    print("Trade ID not found.")
    sys.exit(1)

with open(path, "w") as f:
    f.write("\n".join(lines) + "\n")

print("Trade outcome updated.")

# Update strategy performance tracker
try:
    from core.strategy_tracker import StrategyTracker
    tracker = StrategyTracker()
    tracker.load("logs/strategy_perf.json")
    outcome = 1 if actual == 1 else -1
    if updated_entry:
        tracker.record(updated_entry.get("strategy"), outcome)
    tracker.save("logs/strategy_perf.json")
    print("Strategy performance updated.")
except Exception:
    pass
