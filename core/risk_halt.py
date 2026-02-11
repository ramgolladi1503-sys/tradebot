import json
from pathlib import Path
from config import config as cfg
from core.time_utils import now_utc_epoch, now_ist

def _path():
    return Path(cfg.RISK_HALT_FILE)

def load_halt():
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def is_halted():
    path = _path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        return bool(data.get("halted"))
    except Exception:
        return False

def set_halt(reason, details=None):
    path = _path()
    payload = {
        "halted": True,
        "reason": reason,
        "details": details or {},
        "timestamp_epoch": now_utc_epoch(),
        "timestamp_ist": now_ist().isoformat(),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    try:
        from core.incidents import trigger_hard_halt
        trigger_hard_halt({"reason": reason, "details": details or {}})
    except Exception as exc:
        print(f"[INCIDENT_ERROR] hard_halt err={exc}")
    return payload

def clear_halt():
    path = _path()
    payload = {
        "halted": False,
        "reason": "",
        "details": {},
        "timestamp_epoch": now_utc_epoch(),
        "timestamp_ist": now_ist().isoformat(),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload
