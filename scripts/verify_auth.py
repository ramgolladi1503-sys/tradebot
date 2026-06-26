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
        print(
            f"AUTH_REQUIRED {payload.get('error') or payload.get('auth_state') or 'unknown'}"
        )
        return 3

    print(
        "AUTH_OK "
        f"api_key_tail4={(creds.get('api_key') or '')[-4:]} "
        f"access_token_tail4={(creds.get('access_token') or '')[-4:]} "
        f"user_id={payload.get('user_id') or ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
