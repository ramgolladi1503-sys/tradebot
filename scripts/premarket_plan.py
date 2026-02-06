from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
from datetime import datetime
from pathlib import Path
import sys

from core.market_data import fetch_live_market_data
from core.telegram_alerts import send_telegram_message


def build_plan():
    data = fetch_live_market_data()
    plan = {
        "timestamp": datetime.now().isoformat(),
        "symbols": []
    }
    for m in data:
        if m.get("instrument") != "OPT":
            continue
        plan["symbols"].append({
            "symbol": m.get("symbol"),
            "ltp": m.get("ltp"),
            "regime": m.get("regime"),
            "day_type": m.get("day_type"),
            "day_confidence": m.get("day_confidence"),
            "orb_bias": m.get("orb_bias"),
            "minutes_since_open": m.get("minutes_since_open"),
        })
    return plan


if __name__ == "__main__":
    plan = build_plan()
    out = Path("logs/premarket_plan.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(plan, indent=2))
    # Export CSV
    try:
        import pandas as pd
        rows = plan.get("symbols", [])
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv("logs/premarket_plan.csv", index=False)
    except Exception:
        pass
    # Telegram delivery
    try:
        lines = []
        for s in plan.get("symbols", []):
            lines.append(f"{s.get('symbol')}: {s.get('day_type')} (conf {s.get('day_confidence')}) | ORB {s.get('orb_bias')}")
        msg = "Pre‑Market Plan\n" + "\n".join(lines[:10])
        send_telegram_message(msg)
    except Exception:
        pass
    print(f"Saved premarket plan to {out}")
