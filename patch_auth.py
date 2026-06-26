from core.runtime_auth_freshness import *
import os, time

_CACHE_AUTH_HEALTH = {"mtime": 0.0, "size": 0, "path": "", "data": {}}

def patched_latest_auth_health(path: str | Path | None = None, *, max_lines: int = 200) -> dict[str, Any]:
    global _CACHE_AUTH_HEALTH
    target = Path(path).expanduser() if path is not None else logs_dir() / "auth_health.jsonl"
    if not target.exists():
        return {}
    
    try:
        stat = target.stat()
        mtime = float(stat.st_mtime)
        size = int(stat.st_size)
    except Exception:
        mtime = 0.0
        size = 0

    if (
        _CACHE_AUTH_HEALTH["path"] == str(target)
        and _CACHE_AUTH_HEALTH["mtime"] == mtime
        and _CACHE_AUTH_HEALTH["size"] == size
    ):
        return dict(_CACHE_AUTH_HEALTH["data"])

    try:
        with target.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(max(0, size - 32768)) # Read only the last 32KB
            lines = f.read().splitlines()[-max_lines:]
    except Exception:
        return {}
        
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
            
    result = {}
    if rows:
        result = max(rows, key=lambda row: _float_or_zero(row.get("ts_epoch")))
        
    _CACHE_AUTH_HEALTH["path"] = str(target)
    _CACHE_AUTH_HEALTH["mtime"] = mtime
    _CACHE_AUTH_HEALTH["size"] = size
    _CACHE_AUTH_HEALTH["data"] = dict(result)
    
    return result

import core.runtime_auth_freshness
core.runtime_auth_freshness.latest_auth_health = patched_latest_auth_health
