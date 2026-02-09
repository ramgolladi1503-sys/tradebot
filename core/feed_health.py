import json
import time
from pathlib import Path

from config import config as cfg
from core.time_utils import is_market_open_ist, now_ist
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
    if not SLA_PATH.exists():
        return {"ok": False, "reason": "sla_check_missing"}
    try:
        data = json.loads(SLA_PATH.read_text())
    except Exception:
        return {"ok": False, "reason": "sla_check_unreadable"}
    max_tick = float(getattr(cfg, "SLA_MAX_TICK_LAG_SEC", 120))
    max_depth = float(getattr(cfg, "SLA_MAX_DEPTH_LAG_SEC", 120))
    tick_lag = data.get("tick_lag_sec")
    depth_lag = data.get("depth_lag_sec")
    tick_last_epoch = data.get("tick_last_epoch")
    depth_last_epoch = data.get("depth_last_epoch")
    tick_msgs = data.get("tick_msgs_last_min", 0)
    depth_msgs = data.get("depth_msgs_last_min", 0)
    reasons = []
    if tick_last_epoch is None:
        reasons.append("epoch_missing:tick")
    if depth_last_epoch is None:
        reasons.append("epoch_missing:depth")
    if tick_lag is None and tick_msgs <= 0:
        reasons.append("tick_feed_stale")
    elif tick_lag is not None and tick_lag > max_tick:
        reasons.append("tick_feed_stale")
    if depth_lag is None and depth_msgs <= 0:
        reasons.append("depth_feed_stale")
    elif depth_lag is not None and depth_lag > max_depth:
        reasons.append("depth_feed_stale")
    return {
        "ok": len(reasons) == 0,
        "reasons": reasons,
        "tick_lag": tick_lag,
        "depth_lag": depth_lag,
        "tick_msgs_last_min": tick_msgs,
        "depth_msgs_last_min": depth_msgs,
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
