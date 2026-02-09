#!/usr/bin/env python
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from config import config as cfg
from core.time_utils import is_market_open_ist

SLA_PATH = Path("logs/sla_check.json")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-open", action="store_true")
    args = parser.parse_args()

    if not SLA_PATH.exists():
        raise SystemExit("logs/sla_check.json missing. Run scripts/sla_check.py first.")

    payload = json.loads(SLA_PATH.read_text())

    max_depth = float(getattr(cfg, "SLA_MAX_DEPTH_LAG_SEC", 120))
    max_tick = float(getattr(cfg, "SLA_MAX_TICK_LAG_SEC", 120))

    market_open = args.market_open or is_market_open_ist()
    fail = False
    if payload.get("tick_last_epoch") is None:
        print("FAIL: tick epoch missing")
        fail = True
    if payload.get("depth_last_epoch") is None:
        print("FAIL: depth epoch missing")
        fail = True
    if payload.get("depth_lag_sec") is None or payload.get("depth_lag_sec") > max_depth:
        msg = "depth feed stale"
        print(("FAIL: " if market_open else "WARN: ") + msg)
        fail = fail or market_open
    if payload.get("tick_lag_sec") is None or payload.get("tick_lag_sec") > max_tick:
        msg = "tick feed stale"
        print(("FAIL: " if market_open else "WARN: ") + msg)
        fail = fail or market_open

    if not fail:
        print("PASS: feed SLA OK")
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
