#!/usr/bin/env python
import argparse
from config import config as cfg
from core.freshness_sla import get_freshness_status
from core.time_utils import is_market_open_ist

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-open", action="store_true")
    args = parser.parse_args()

    payload = get_freshness_status(force=True)
    max_depth = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0))
    max_tick = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))

    market_open = args.market_open or is_market_open_ist()
    fail = False
    if (payload.get("ltp") or {}).get("age_sec") is None and market_open:
        print("FAIL: tick epoch missing")
        fail = True
    if (payload.get("depth") or {}).get("age_sec") is None and market_open:
        print("FAIL: depth epoch missing")
        fail = True
    if (payload.get("depth") or {}).get("age_sec") is None or (payload.get("depth") or {}).get("age_sec") > max_depth:
        msg = "depth feed stale"
        print(("FAIL: " if market_open else "WARN: ") + msg)
        fail = fail or market_open
    if (payload.get("ltp") or {}).get("age_sec") is None or (payload.get("ltp") or {}).get("age_sec") > max_tick:
        msg = "tick feed stale"
        print(("FAIL: " if market_open else "WARN: ") + msg)
        fail = fail or market_open

    if not fail:
        print("PASS: feed SLA OK")
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
