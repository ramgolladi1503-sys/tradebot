import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import fetch_live_market_data
from core.strategy_gatekeeper import StrategyGatekeeper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=1)
    parser.add_argument("--paper", action="store_true")
    args = parser.parse_args()

    duration = max(1, args.minutes) * 60
    end_ts = time.time() + duration
    gatekeeper = StrategyGatekeeper()
    events = []

    while time.time() < end_ts:
        try:
            data = fetch_live_market_data()
            for md in data:
                gate = gatekeeper.evaluate(md, mode="MAIN")
                events.append({
                    "ts_epoch": time.time(),
                    "symbol": md.get("symbol"),
                    "gate_allowed": gate.allowed,
                    "reasons": gate.reasons,
                })
        except Exception as e:
            events.append({
                "ts_epoch": time.time(),
                "error": f"DRILL_FETCH_FAIL:{e}",
            })
        time.sleep(1)

    out = Path("logs/dr_failover_drill.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"events": events, "minutes": args.minutes}, indent=2))
    print(f"DR drill complete: {out}")


if __name__ == "__main__":
    main()
