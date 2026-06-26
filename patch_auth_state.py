from core.auth_manager import *
import os

_CACHE_AUTH_STATE = {"mtime": 0.0, "size": 0, "path": "", "data": {}}

def patched_load_auth_state(*, repo_root_path: Path | str | None = None) -> dict[str, Any]:
    global _CACHE_AUTH_STATE
    path = auth_state_path(repo_root_path=repo_root_path)
    if not path.exists():
        return {}
        
    try:
        stat = path.stat()
        mtime = float(stat.st_mtime)
        size = int(stat.st_size)
    except Exception:
        mtime = 0.0
        size = 0

    if (
        _CACHE_AUTH_STATE["path"] == str(path)
        and _CACHE_AUTH_STATE["mtime"] == mtime
        and _CACHE_AUTH_STATE["size"] == size
        and _CACHE_AUTH_STATE["data"]
    ):
        return dict(_CACHE_AUTH_STATE["data"])

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
        
    result = payload if isinstance(payload, dict) else {}
    _CACHE_AUTH_STATE["path"] = str(path)
    _CACHE_AUTH_STATE["mtime"] = mtime
    _CACHE_AUTH_STATE["size"] = size
    _CACHE_AUTH_STATE["data"] = dict(result)
    return result

import core.auth_manager
core.auth_manager.load_auth_state = patched_load_auth_state
