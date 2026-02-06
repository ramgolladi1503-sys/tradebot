import json
import time
from pathlib import Path

REG_PATH = Path("logs/model_registry.json")

def _load():
    if REG_PATH.exists():
        try:
            return json.loads(REG_PATH.read_text())
        except Exception:
            pass
    return {"active": {}, "models": []}

def _save(data):
    REG_PATH.parent.mkdir(exist_ok=True)
    REG_PATH.write_text(json.dumps(data, indent=2))

def register_model(model_type, path, metrics=None):
    data = _load()
    entry = {
        "type": model_type,
        "path": str(path),
        "metrics": metrics or {},
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["models"].append(entry)
    _save(data)
    return entry

def activate_model(model_type, path):
    data = _load()
    data["active"][model_type] = str(path)
    _save(data)
    return data["active"]

def get_active(model_type):
    data = _load()
    return data.get("active", {}).get(model_type)
