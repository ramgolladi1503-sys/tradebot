from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
from pathlib import Path

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
    import pandas as pd
    out = Path("data/kite_instruments.csv")
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(data).to_csv(out, index=False)
    print(f"Saved {len(data)} instruments to {out}")
