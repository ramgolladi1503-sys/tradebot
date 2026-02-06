from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

out_path = Path("data/trade_log.json")
out_path.parent.mkdir(exist_ok=True)

symbols = ["NIFTY", "BANKNIFTY", "SENSEX"]
strategies = ["ENSEMBLE_OPT", "FUT_TREND", "EQ_TREND"]

start = datetime.now() - timedelta(days=2)
rows = []
for i in range(30):
    ts = start + timedelta(minutes=30 * i)
    sym = random.choice(symbols)
    strat = random.choice(strategies)
    entry = random.uniform(50, 150)
    exit_price = entry + random.uniform(-15, 20)
    pnl = exit_price - entry
    rows.append({
        "trade_id": f"{sym}-{i}",
        "timestamp": str(ts),
        "symbol": sym,
        "instrument": "OPT",
        "side": "BUY",
        "entry": round(entry, 2),
        "target": round(entry + 10, 2),
        "qty": 1,
        "confidence": round(random.uniform(0.6, 0.9), 3),
        "stop_loss": round(entry - 8, 2),
        "capital_at_risk": round(8, 2),
        "regime": "NEUTRAL",
        "strategy": strat,
        "predicted": 1,
        "actual": 1 if pnl > 0 else 0,
        "exit_price": round(exit_price, 2),
        "exit_time": str(ts + timedelta(minutes=15))
    })

with open(out_path, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

print(f"Generated {len(rows)} sample trades at {out_path}")
