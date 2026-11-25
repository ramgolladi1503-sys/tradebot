import os
import sys
import requests
from pathlib import Path

def check_token():
    env_path = Path(".env")
    token = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("UPSTOX_ACCESS_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'\"")
                break
    if not token:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        print("[!] CRITICAL PREFLIGHT: UPSTOX_ACCESS_TOKEN is empty!")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "TradeBot/1.0"
    }
    try:
        r = requests.get("https://api.upstox.com/v2/user/profile", headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", {})
            user_name = data.get("user_name", "Authorized User")
            print(f"[✓] Upstox Access Token Preflight Validated ({user_name})")
            sys.exit(0)
        elif r.status_code in (401, 403):
            print(f"[!] CRITICAL AUTH FAILURE: Upstox Access Token Expired (HTTP {r.status_code})")
            sys.exit(2)
        else:
            print(f"[!] Preflight HTTP status: {r.status_code}")
            sys.exit(2)
    except Exception as e:
        print(f"[*] Network check skipped or unreachable: {e}")
        sys.exit(0)

if __name__ == "__main__":
    check_token()
