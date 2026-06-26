#!/usr/bin/env python
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.auth import validate_kite_startup_credentials
from core.auth_health import get_kite_auth_health


def main() -> int:
    try:
        creds = validate_kite_startup_credentials(
            repo_root_path=ROOT,
            require_access_token=True,
            caller_module=__name__,
        )
    except RuntimeError as exc:
        print(f"AUTH_CONFIG_ERROR {exc}")
        return 2

    payload = get_kite_auth_health(force=True)
    if not payload.get("ok"):
        err_msg = str(payload.get('error') or payload.get('auth_state') or 'unknown')
        sys.stdout.write(f"AUTH_REQUIRED {err_msg}\n")
        return 3

    ak_tail = str(creds.get('api_key') or '')[-4:]
    at_tail = str(creds.get('access_token') or '')[-4:]
    u_id = str(payload.get('user_id') or '')
    sys.stdout.write(f"AUTH_OK api_key_tail4={ak_tail} access_token_tail4={at_tail} user_id={u_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
