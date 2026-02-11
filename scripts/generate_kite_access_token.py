from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sys
import re

from config import config as cfg
from core.kite_client import KiteConnect
from core.kite_client import kite_client
from core.auth_health import get_kite_auth_health
from core.security_guard import write_local_kite_access_token
import getpass

def mask(val, keep=4):
    if not val:
        return "MISSING"
    if len(val) <= keep:
        return val
    return ("*" * (len(val) - keep)) + val[-keep:]


def _secret_debug(label, value):
    raw = str(value or "")
    return {
        f"{label}_len": len(raw),
        f"{label}_last4": raw[-4:] if len(raw) >= 4 else raw,
        f"{label}_has_whitespace": bool(re.search(r"\s", raw)),
    }


def _looks_placeholder_api_key(value):
    token = str(value or "").strip().lower()
    if not token:
        return True
    if token.startswith("your_") or "placeholder" in token:
        return True
    return token in {
        "your_kiteconnect_api_key",
        "your_kite_api_key",
        "your_api_key",
        "changeme",
    }

def _persist_local_token(access_token):
    return write_local_kite_access_token(access_token)


def generate_validated_token(api_key, api_secret, request_token, kite_connect_cls):
    kite = kite_connect_cls(api_key=api_key)
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("no_access_token_returned")
    kite.set_access_token(access_token)
    margins = kite.margins()
    if margins is None:
        raise RuntimeError("margins_missing")
    return kite, access_token, margins


def generate_token_flow(api_key, api_secret, request_token, update_store, kite_connect_cls, persist_fn):
    kite, access_token, margins = generate_validated_token(
        api_key,
        api_secret,
        request_token,
        kite_connect_cls,
    )
    token_path = None
    if update_store:
        token_path = persist_fn(access_token)
        cfg.KITE_ACCESS_TOKEN = access_token
        auth_payload = get_kite_auth_health(force=True)
        if not auth_payload.get("ok"):
            if token_path:
                try:
                    Path(token_path).unlink()
                except Exception:
                    pass
            raise RuntimeError(auth_payload.get("error") or "profile_validation_failed")
    else:
        auth_payload = {"user_id": "", "user_name": ""}
    return {
        "kite": kite,
        "access_token": access_token,
        "profile": auth_payload,
        "margins": margins,
        "token_path": token_path,
    }

if __name__ == "__main__":
    if not KiteConnect:
        raise SystemExit("kiteconnect not installed.")
    if not cfg.KITE_API_KEY or not cfg.KITE_API_SECRET:
        raise SystemExit("Missing KITE_API_KEY or KITE_API_SECRET in .env")
    if _looks_placeholder_api_key(cfg.KITE_API_KEY):
        raise SystemExit(
            "Invalid KITE_API_KEY placeholder detected. Set real Kite app key in env/.env before generating token."
        )

    request_token = ""
    if "--request-token" in sys.argv:
        idx = sys.argv.index("--request-token")
        if idx + 1 < len(sys.argv):
            request_token = sys.argv[idx + 1]
    if not request_token and "--prompt-token" in sys.argv:
        request_token = getpass.getpass("Enter Kite request token: ").strip()
    if not request_token:
        request_token = getattr(cfg, "KITE_REQUEST_TOKEN", "") or ""
    if not request_token:
        raise SystemExit("Missing KITE_REQUEST_TOKEN in .env (or pass --request-token)")

    api_debug = _secret_debug("api_key", cfg.KITE_API_KEY)
    print(
        "[KITE_AUTH] "
        f"api_key_len={api_debug['api_key_len']} "
        f"api_key_last4={api_debug['api_key_last4']} "
        f"api_key_has_whitespace={api_debug['api_key_has_whitespace']}"
    )

    auto_update = "--update-env" in sys.argv
    try:
        flow = generate_token_flow(
            cfg.KITE_API_KEY,
            cfg.KITE_API_SECRET,
            request_token,
            auto_update,
            KiteConnect,
            _persist_local_token,
        )
    except Exception as e:
        raise SystemExit(f"Kite session validation failed (profile/margins): {e}")
    kite = flow["kite"]
    access_token = flow["access_token"]
    profile = flow["profile"]
    margins = flow["margins"]
    token_path = flow["token_path"]

    token_debug = _secret_debug("access_token", access_token)
    print(
        "[KITE_AUTH] "
        f"access_token_len={token_debug['access_token_len']} "
        f"access_token_last4={token_debug['access_token_last4']} "
        f"access_token_has_whitespace={token_debug['access_token_has_whitespace']}"
    )

    user_id = str(profile.get("user_id", "") or "")
    print(f"[KITE_AUTH] profile_ok user_last4={user_id[-4:] if user_id else 'NONE'}")
    if isinstance(margins, dict):
        print(f"[KITE_AUTH] margins_ok keys={','.join(sorted(margins.keys())[:5])}")
    else:
        print("[KITE_AUTH] margins_ok")

    if auto_update:
        print(f"Updated local token store: {token_path}")
        try:
            # refresh in-memory session using same validated token
            if kite_client.kite:
                kite_client.kite.set_access_token(access_token)
            else:
                kite_client._ensure()
            print("Refreshed in-memory Kite session.")
            auth_payload = get_kite_auth_health(force=True)
            if auth_payload.get("ok"):
                user_id = auth_payload.get("user_id", "")
                print(f"Profile OK for user: {mask(user_id, keep=2)}")
            else:
                print(f"Profile check failed: {auth_payload.get('error')}")
            try:
                inst = kite_client.instruments("NFO")
                print(f"NFO instruments: {len(inst)}")
            except Exception as e:
                print(f"Instruments check skipped: {e}")
        except Exception as e:
            print(f"Session refresh warning: {e}")
    print(f"Generated access token: {mask(access_token)}")
    if not auto_update:
        print("Export with: export KITE_ACCESS_TOKEN=<token>")
        print("Or run with --update-env to store under ~/.trading_bot/")
