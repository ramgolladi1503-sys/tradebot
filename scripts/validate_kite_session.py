from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import os

from config import config as cfg
from core.auth_health import get_kite_auth_health
from core.security_guard import local_token_path, read_local_kite_access_token

def mask(val, keep=4):
    if not val:
        return "MISSING"
    raw = str(val)
    if len(raw) <= keep:
        return raw
    return ("*" * (len(raw) - keep)) + raw[-keep:]

if __name__ == "__main__":
    env_key = os.getenv("KITE_API_KEY", "").strip()
    effective_key = env_key or str(getattr(cfg, "KITE_API_KEY", "") or "").strip()
    local_token = read_local_kite_access_token().strip()
    env_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    cfg_token = str(getattr(cfg, "KITE_ACCESS_TOKEN", "") or "").strip()

    print(f"API key: {mask(effective_key)}")
    print(f"API key has_whitespace: {any(ch.isspace() for ch in (effective_key or ''))}")
    print(
        "Token sources:"
        f" env={'YES' if bool(env_token) else 'NO'}"
        f" cfg={'YES' if bool(cfg_token) else 'NO'}"
        f" local={'YES' if bool(local_token) else 'NO'}"
        f" path={local_token_path()}"
    )
    if not effective_key:
        raise SystemExit("Missing KITE_API_KEY in env/config")

    payload = get_kite_auth_health(force=True)
    if not payload.get("ok"):
        raise SystemExit(f"Session validation failed: {payload.get('error')}")
    user_id = payload.get("user_id", "")
    print(f"Session OK for user: {mask(user_id, keep=2)}")
