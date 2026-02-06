from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sys
from pathlib import Path

from config import config as cfg
from core.kite_client import KiteConnect
from core.kite_client import kite_client
import getpass

def mask(val, keep=4):
    if not val:
        return "MISSING"
    return val[:keep] + ("*" * (max(0, len(val) - keep)))

def _update_env(access_token):
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(f"KITE_ACCESS_TOKEN={access_token}\n")
        return
    lines = env_path.read_text().splitlines()
    updated = False
    out = []
    for line in lines:
        if line.startswith("KITE_ACCESS_TOKEN="):
            out.append(f"KITE_ACCESS_TOKEN={access_token}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"KITE_ACCESS_TOKEN={access_token}")
    env_path.write_text("\n".join(out) + "\n")

if __name__ == "__main__":
    if not KiteConnect:
        raise SystemExit("kiteconnect not installed.")
    if not cfg.KITE_API_KEY or not cfg.KITE_API_SECRET:
        raise SystemExit("Missing KITE_API_KEY or KITE_API_SECRET in .env")

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

    kite = KiteConnect(api_key=cfg.KITE_API_KEY)
    try:
        data = kite.generate_session(request_token, api_secret=cfg.KITE_API_SECRET)
    except Exception as e:
        raise SystemExit(f"Session generation failed: {e}")

    access_token = data.get("access_token")
    if not access_token:
        raise SystemExit("No access_token returned.")

    auto_update = "--update-env" in sys.argv
    if auto_update:
        _update_env(access_token)
        print("Updated .env with new KITE_ACCESS_TOKEN")
        try:
            # refresh in-memory session
            if kite_client.kite:
                kite_client.kite.set_access_token(access_token)
            else:
                kite_client._ensure()
            print("Refreshed in-memory Kite session.")
            try:
                profile = kite_client.kite.profile()
                user_id = profile.get("user_id", "")
                print(f"Profile OK for user: {mask(user_id, keep=2)}")
            except Exception:
                pass
            try:
                inst = kite_client.instruments("NFO")
                print(f"NFO instruments: {len(inst)}")
            except Exception:
                pass
        except Exception:
            pass
    print(f"Generated access token: {mask(access_token)}")
    if not auto_update:
        print("Update your .env with KITE_ACCESS_TOKEN=<token>")
