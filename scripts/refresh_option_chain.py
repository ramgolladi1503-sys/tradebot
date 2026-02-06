from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sys
from pathlib import Path

from core.option_chain import fetch_option_chain
from core.market_data import get_ltp
from config import config as cfg

if __name__ == "__main__":
    stats = {}
    for sym in cfg.SYMBOLS:
        ltp = get_ltp(sym)
        chain = fetch_option_chain(sym, ltp)
        stats[sym] = {
            "ltp": ltp,
            "count": len(chain),
            "premium_min": min([c.get("ltp", 0) for c in chain], default=0),
            "premium_max": max([c.get("ltp", 0) for c in chain], default=0),
        }
    print("Option chain refreshed.")
    for sym, s in stats.items():
        print(sym, s)
