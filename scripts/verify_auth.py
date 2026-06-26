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
        raw_auth_state = str(payload.get("auth_state") or "").strip().upper()
        safe_auth_state = (
            raw_auth_state
            if raw_auth_state in {"FAILED", "SKIPPED_SIM_MODE", "AUTH_REQUIRED", "UNKNOWN"}
            else "UNKNOWN"
        )
        sys.stdout.write(f"AUTH_REQUIRED {safe_auth_state}\n")
        return 3

    sys.stdout.write("AUTH_OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
