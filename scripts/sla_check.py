from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json

from config import config as cfg
from core.telegram_alerts import send_telegram_message
from core.incidents import trigger_feed_stale
from core.freshness_sla import get_freshness_status
from core.slo_guard import evaluate_slo_status

OUT = Path("logs/sla_check.json")


if __name__ == "__main__":
    payload = get_freshness_status(force=True)
    payload["slo_guard"] = evaluate_slo_status(enforce_failover=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)

    alerts = []
    allow_stale = bool(payload.get("allow_stale_quotes"))
    market_open = bool(payload.get("market_open"))
    ltp = payload.get("ltp") or {}
    depth = payload.get("depth") or {}
    depth_required = bool(depth.get("required", False))
    ltp_max = ltp.get("max_age_sec") or getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)
    depth_max = depth.get("max_age_sec") or getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0)
    alerts_enabled = bool(market_open and (not allow_stale))
    if alerts_enabled:
        ltp = payload.get("ltp") or {}
        depth = payload.get("depth") or {}
        if ltp.get("age_sec") is None:
            alerts.append("Tick epoch missing")
        if depth_required and depth.get("age_sec") is None:
            alerts.append("Depth epoch missing")
        if ltp.get("age_sec") is None or ltp.get("age_sec") > ltp_max:
            alerts.append("Tick feed lagging")
        if depth_required and (depth.get("age_sec") is None or depth.get("age_sec") > depth_max):
            alerts.append("Depth feed lagging")
        slo = payload.get("slo_guard") or {}
        if bool(slo.get("should_enforce")) and str(slo.get("status") or "").upper() in {"BREACH", "FAILOVER"}:
            alerts.append("SLO guard breach")
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
