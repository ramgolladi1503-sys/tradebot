import json
import time
from pathlib import Path

from config import config as cfg
from core.time_utils import is_market_open_ist, now_ist
from core.freshness_sla import get_freshness_status
from core.incidents import trigger_feed_stale


SLA_PATH = Path("logs/sla_check.json")
STATE_PATH = Path("logs/feed_health_state.json")


def _load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def get_feed_health():
    freshness = get_freshness_status(force=False)
    return {
        "ok": freshness.get("ok"),
        "reasons": freshness.get("reasons") or [],
        "market_open": freshness.get("market_open"),
        "tick_lag": (freshness.get("ltp") or {}).get("age_sec"),
        "depth_lag": (freshness.get("depth") or {}).get("age_sec"),
        "tick_msgs_last_min": None,
        "depth_msgs_last_min": None,
    }


def check_and_trigger():
    health = get_feed_health()
    market_open = is_market_open_ist()
    now_epoch = time.time()
    if market_open and not health.get("ok"):
        state = _load_state()
        cooldown = float(getattr(cfg, "FEED_STALE_INCIDENT_COOLDOWN_SEC", 300))
        last = float(state.get("last_incident_epoch") or 0.0)
        if now_epoch - last >= cooldown:
            trigger_feed_stale({
                "reasons": health.get("reasons"),
                "tick_lag_sec": health.get("tick_lag"),
                "depth_lag_sec": health.get("depth_lag"),
                "ts_ist": now_ist().isoformat(),
            })
            state["last_incident_epoch"] = now_epoch
            _save_state(state)
    return health
