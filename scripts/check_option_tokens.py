from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sys
from pathlib import Path

from core.kite_client import kite_client
from core.market_calendar import next_expiry_by_type
from config import config as cfg

if __name__ == "__main__":
    expiry_weekly = next_expiry_by_type("WEEKLY")
    expiry_monthly = next_expiry_by_type("MONTHLY")
    weekly_tokens = kite_client.resolve_option_tokens(cfg.SYMBOLS, expiry_weekly)
    monthly_tokens = kite_client.resolve_option_tokens(cfg.SYMBOLS, expiry_monthly)

    print(f"Weekly expiry: {expiry_weekly}, tokens: {len(weekly_tokens)}")
    print(f"Monthly expiry: {expiry_monthly}, tokens: {len(monthly_tokens)}")
