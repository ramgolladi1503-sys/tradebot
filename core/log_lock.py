import json
import time
from pathlib import Path
from config import config as cfg

def _path():
    return Path(cfg.LOG_LOCK_FILE)

def is_locked():
    path = _path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        return bool(data.get("locked", True))
    except Exception:
        return True

def lock(reason="append-only enabled"):
    path = _path()
    payload = {
        "locked": True,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload

def unlock():
    path = _path()
    payload = {
        "locked": False,
        "reason": "",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload
