#!/usr/bin/env python
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import re
import sys

from config import config as cfg
from core import risk_halt
from core.kite_client import kite_client
from core.security_guard import resolve_kite_access_token
from core.auth_health import get_kite_auth_health
from core.time_utils import now_ist, now_utc_epoch


def _masked_stats(name: str, value: str) -> dict:
    token = str(value or "")
    tail = token[-4:] if len(token) >= 4 else token
    return {
        f"{name}_len": len(token),
        f"{name}_tail4": tail,
        f"{name}_has_whitespace": bool(re.search(r"\s", token)),
    }


def _write_payload(payload: dict) -> None:
    path = Path(getattr(cfg, "AUTH_WARMUP_LOG_PATH", "logs/auth_warmup.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    now = now_ist()
    payload = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now.isoformat(),
        "ok": False,
        "reason_code": None,
        "details": {},
    }

    try:
        token = resolve_kite_access_token(repo_root=Path(__file__).resolve().parents[1], require_token=True).strip()
        cfg.KITE_ACCESS_TOKEN = token
        payload["details"].update(_masked_stats("access_token", token))
        payload["details"].update(_masked_stats("api_key", str(getattr(cfg, "KITE_API_KEY", ""))))

        kite_client.kite = None
        kite_client.last_init_error = None
        auth_payload = get_kite_auth_health(force=True)
        if not auth_payload.get("ok"):
            raise RuntimeError(auth_payload.get("error") or "kite_auth_failed")
        if not kite_client.kite:
            reason = getattr(kite_client, "last_init_error", None) or "kite_init_failed"
            raise RuntimeError(str(reason))
        margins = kite_client.kite.margins()
        user_id = str((auth_payload or {}).get("user_id", ""))
        margin_keys = sorted((margins or {}).keys()) if isinstance(margins, dict) else []

        payload["ok"] = True
        payload["reason_code"] = "AUTH_WARMUP_OK"
        payload["details"]["user_last4"] = user_id[-4:] if user_id else ""
        payload["details"]["margin_keys"] = margin_keys
        _write_payload(payload)
        print(f"[AUTH_WARMUP] ok user_last4={payload['details']['user_last4']} margin_keys={','.join(margin_keys)}")
        return 0
    except Exception as exc:
        payload["ok"] = False
        payload["reason_code"] = "AUTH_WARMUP_FAILED"
        payload["details"]["error"] = str(exc)
        _write_payload(payload)
        print(f"[AUTH_WARMUP] failed err={exc}")
        if getattr(cfg, "AUTH_WARMUP_TRIGGER_RISK_HALT", True):
            try:
                risk_halt.set_halt("auth_warmup_failed", {"error": str(exc)})
                print("[AUTH_WARMUP] risk_halt set: auth_warmup_failed")
            except Exception as halt_exc:
                print(f"[AUTH_WARMUP] failed to set risk halt: {halt_exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
