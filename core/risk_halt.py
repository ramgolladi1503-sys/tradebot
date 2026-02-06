import json
import time
from pathlib import Path
from config import config as cfg

def _path():
    return Path(cfg.RISK_HALT_FILE)

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
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload

def clear_halt():
    path = _path()
    payload = {
        "halted": False,
        "reason": "",
        "details": {},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload
