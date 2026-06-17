from pathlib import Path
import runpy
import sys

runpy.run_path(str(Path(__file__).with_name("bootstrap.py")))

from core.paths import data_root

from core.kite_client import kite_client

if __name__ == "__main__":
    try:
        data = kite_client.instruments("NFO")
    except Exception as e:
        print(f"Instruments fetch failed: {e}")
        raise SystemExit(1)
    if not data:
        print("No instruments fetched. Check Kite credentials/session.")
        raise SystemExit(1)
    import json
    out = data_root() / "kite_instruments.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        json.dump({"NFO": data}, f, default=str)
    print(f"Saved {len(data)} instruments to {out}")
