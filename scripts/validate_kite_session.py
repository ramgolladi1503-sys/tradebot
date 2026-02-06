from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.kite_client import kite_client

def mask(val, keep=4):
    if not val:
        return "MISSING"
    return val[:keep] + ("*" * (max(0, len(val) - keep)))

if __name__ == "__main__":
    print(f"API key: {mask(cfg.KITE_API_KEY)}")
    print(f"Access token set: {'YES' if cfg.KITE_ACCESS_TOKEN else 'NO'}")
    if not cfg.KITE_API_KEY or not cfg.KITE_ACCESS_TOKEN:
        raise SystemExit("Missing KITE_API_KEY or KITE_ACCESS_TOKEN in .env")

    kite_client.ensure()
    if not kite_client.kite:
        raise SystemExit("Kite client not initialized. Check creds.")

    try:
        profile = kite_client.kite.profile()
        user_id = profile.get("user_id", "")
        print(f"Session OK for user: {mask(user_id, keep=2)}")
    except Exception as e:
        raise SystemExit(f"Session validation failed: {e}")
