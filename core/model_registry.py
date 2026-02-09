import json
import time
import hashlib
from pathlib import Path

REG_PATH = Path("logs/model_registry.json")


def _hash_file(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load():
    if REG_PATH.exists():
        try:
            data = json.loads(REG_PATH.read_text())
            if "active" not in data:
                data["active"] = {}
            if "shadow" not in data:
                data["shadow"] = {}
            if "history" not in data:
                data["history"] = {}
            if "models" not in data:
                data["models"] = []
            return data
        except Exception:
            pass
    return {"active": {}, "shadow": {}, "history": {}, "models": []}


def _save(data):
    REG_PATH.parent.mkdir(exist_ok=True)
    tmp_path = REG_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(REG_PATH)


def _find_entry(data, model_type, path):
    path = str(path)
    for i, entry in enumerate(data.get("models", [])):
        if entry.get("type") == model_type and entry.get("path") == path:
            return i, entry
    return None, None


def register_model(model_type, path, metrics=None, governance=None, status="candidate"):
    data = _load()
    entry = {
        "type": model_type,
        "path": str(path),
        "hash": _hash_file(path),
        "metrics": metrics or {},
        "governance": governance or {},
        "status": status,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    idx, _ = _find_entry(data, model_type, path)
    if idx is None:
        data["models"].append(entry)
    else:
        data["models"][idx].update(entry)
    _save(data)
    return entry


def update_model_metrics(model_type, path, metrics=None, governance=None):
    data = _load()
    idx, entry = _find_entry(data, model_type, path)
    if idx is None:
        entry = register_model(model_type, path, metrics=metrics, governance=governance)
        return entry
    if metrics:
        entry.setdefault("metrics", {}).update(metrics)
    if governance:
        entry.setdefault("governance", {}).update(governance)
    data["models"][idx] = entry
    _save(data)
    return entry


def activate_model(model_type, path, metrics=None, governance=None):
    data = _load()
    prev = data.get("active", {}).get(model_type)
    if prev and prev != str(path):
        data.setdefault("history", {}).setdefault(model_type, []).append(prev)
    data["active"][model_type] = str(path)
    update_model_metrics(model_type, path, metrics=metrics, governance=governance)
    # mark status
    idx, entry = _find_entry(data, model_type, path)
    if idx is not None:
        entry["status"] = "active"
        data["models"][idx] = entry
    _save(data)
    return data["active"]


def set_shadow(model_type, path, metrics=None, governance=None):
    data = _load()
    data["shadow"][model_type] = str(path)
    update_model_metrics(model_type, path, metrics=metrics, governance=governance)
    idx, entry = _find_entry(data, model_type, path)
    if idx is not None:
        entry["status"] = "shadow"
        data["models"][idx] = entry
    _save(data)
    return data["shadow"]


def rollback_model(model_type, steps=1):
    data = _load()
    history = data.get("history", {}).get(model_type, [])
    if not history or steps <= 0 or len(history) < steps:
        return None
    new_path = history[-steps]
    # trim history
    data["history"][model_type] = history[:-steps]
    data["active"][model_type] = new_path
    idx, entry = _find_entry(data, model_type, new_path)
    if idx is not None:
        entry["status"] = "active"
        data["models"][idx] = entry
    _save(data)
    return new_path


def prune_history(model_type, keep_n=3):
    data = _load()
    history = data.get("history", {}).get(model_type, [])
    if keep_n is None or keep_n <= 0:
        return history
    if len(history) <= keep_n:
        return history
    data["history"][model_type] = history[-keep_n:]
    _save(data)
    return data["history"][model_type]


def get_active(model_type):
    data = _load()
    return data.get("active", {}).get(model_type)


def get_shadow(model_type):
    data = _load()
    return data.get("shadow", {}).get(model_type)


def get_active_entry(model_type):
    data = _load()
    path = data.get("active", {}).get(model_type)
    if not path:
        return None
    _, entry = _find_entry(data, model_type, path)
    return entry


def get_shadow_entry(model_type):
    data = _load()
    path = data.get("shadow", {}).get(model_type)
    if not path:
        return None
    _, entry = _find_entry(data, model_type, path)
    return entry


def list_models(model_type=None):
    data = _load()
    models = data.get("models", [])
    if not model_type:
        return models
    return [m for m in models if m.get("type") == model_type]
