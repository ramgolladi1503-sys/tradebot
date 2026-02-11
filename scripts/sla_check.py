from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json

from config import config as cfg
from core.telegram_alerts import send_telegram_message
from core.incidents import trigger_feed_stale
from core.freshness_sla import get_freshness_status

OUT = Path("logs/sla_check.json")


if __name__ == "__main__":
    payload = get_freshness_status(force=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)

    alerts = []
    if payload.get("market_open"):
        ltp = payload.get("ltp") or {}
        depth = payload.get("depth") or {}
        if ltp.get("age_sec") is None:
            alerts.append("Tick epoch missing")
        if depth.get("age_sec") is None:
            alerts.append("Depth epoch missing")
        if ltp.get("age_sec") is None or ltp.get("age_sec") > getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5):
            alerts.append("Tick feed lagging")
        if depth.get("age_sec") is None or depth.get("age_sec") > getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0):
            alerts.append("Depth feed lagging")
        if alerts:
            send_telegram_message("SLA alert: " + ", ".join(alerts))
            try:
                trigger_feed_stale({
                    "alerts": alerts,
                    "tick_lag_sec": (payload.get("ltp") or {}).get("age_sec"),
                    "depth_lag_sec": (payload.get("depth") or {}).get("age_sec"),
                    "ts_ist": payload.get("ts_ist"),
                })
            except Exception as exc:
                print(f"[INCIDENT_ERROR] feed_stale trigger err={exc}")
