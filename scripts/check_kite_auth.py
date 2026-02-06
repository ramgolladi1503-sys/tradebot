from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
from pathlib import Path

from core.kite_client import kite_client
from config import config as cfg

if __name__ == "__main__":
    print("API Key:", cfg.KITE_API_KEY[:4] + "..." if cfg.KITE_API_KEY else "MISSING")
    print("Access Token set:", "YES" if cfg.KITE_ACCESS_TOKEN else "NO")
    try:
        data = kite_client.instruments_cached("NFO", ttl_sec=0)
        print("NFO instruments:", len(data))
    except Exception as e:
        print(f"Live instruments fetch failed: {e}")
        cache_json = Path("data/kite_instruments.json")
        cache_csv = Path("data/kite_instruments.csv")
        if cache_json.exists() or cache_csv.exists():
            data = kite_client.instruments_cached("NFO", ttl_sec=10**9)
            print("NFO instruments (cache):", len(data))
        else:
            print("No local instruments cache found. Check network/DNS and retry.")
