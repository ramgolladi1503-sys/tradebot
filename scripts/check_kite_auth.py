#!/usr/bin/env python
from pathlib import Path
import argparse
import runpy
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.auth import validate_kite_startup_credentials
from core.auth_manager import validate_token
from core.instance_lock import InstanceLock


def _execution_mode(value: str | None = None) -> str:
    mode = str(value or getattr(cfg, "EXECUTION_MODE", "SIM")).strip().upper()
    return mode if mode in {"LIVE", "PAPER", "SIM"} else "SIM"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Kite token and enforce single-instance Kite lock."
    )
    parser.add_argument(
        "--mode", default=None, help="Execution mode override: LIVE|PAPER|SIM"
    )
    args = parser.parse_args()

    mode = _execution_mode(args.mode)
    try:
        validate_kite_startup_credentials(
            repo_root_path=Path(__file__).resolve().parents[1],
            require_access_token=True,
            caller_module=__name__,
        )
    except RuntimeError as exc:
        print(f"AUTH_CONFIG_ERROR {exc}")
        return 2
    lock = None
    if mode in {"LIVE", "PAPER"}:
        lock = InstanceLock(repo_root_path=Path(__file__).resolve().parents[1])
        try:
            acquired, holder = lock.acquire()
        except RuntimeError as exc:
            print(f"LOCK_ERROR {exc}")
            return 4
        if not acquired:
            print(
                "LOCK_HELD "
                f"pid={holder.get('pid') or 'unknown'} "
                f"host={holder.get('host') or 'unknown'} "
                f"path={holder.get('lock_path') or lock.lock_path}"
            )
            return 2

    try:
        payload = validate_token(
            repo_root_path=Path(__file__).resolve().parents[1], force=True
        )
        ok = payload.get("ok") is True
        auth_state = str(payload.get("auth_state") or "").strip().upper()
        user_id = str(payload.get("user_id") or "").strip()
        verified = ok and auth_state == "OK" and bool(user_id)
        if verified:
            print(f"OK user_id={user_id}")
            return 0

        reason = str(payload.get("error") or auth_state or "unknown")
        if auth_state == "UNKNOWN_NETWORK":
            print(f"AUTH_UNVERIFIED_NETWORK mode={mode} reason={reason}")
            print("NEXT: restore network access and rerun python scripts/check_kite_auth.py")
            return 5

        print(f"AUTH_REQUIRED mode={mode} reason={reason}")
        print("NEXT: python scripts/kite_autologin_localhost.py")
        print("THEN: python scripts/check_kite_auth.py")
        return 3
    finally:
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    sys.exit(main())
