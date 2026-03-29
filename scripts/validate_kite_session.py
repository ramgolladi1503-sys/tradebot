from pathlib import Path
import runpy
import os

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.auth import validate_kite_startup_credentials
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
    creds = validate_kite_startup_credentials(
        repo_root_path=Path(__file__).resolve().parents[1],
        require_access_token=True,
        caller_module=__name__,
    )
    effective_key = str(creds.get("api_key") or "").strip()
    local_token = read_local_kite_access_token().strip()

    print(f"API key: {mask(effective_key)}")
    print(f"API key has_whitespace: {any(ch.isspace() for ch in (effective_key or ''))}")
    print(
        "Token sources:"
        f" local={'YES' if bool(local_token) else 'NO'}"
        f" path={local_token_path()}"
    )
    payload = get_kite_auth_health(force=True)
    if not payload.get("ok"):
        raise SystemExit(f"Session validation failed: {payload.get('error')}")
    user_id = payload.get("user_id", "")
    print(f"Session OK for user: {mask(user_id, keep=2)}")
