from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
from core.review_queue import approve

if len(sys.argv) < 2:
    print("Usage: python scripts/approve_trade.py <trade_id>")
    raise SystemExit(1)

approve(sys.argv[1])
print("Approved.")
