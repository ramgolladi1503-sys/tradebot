import sys
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.time_utils import now_utc_epoch, now_ist, is_market_open_ist, next_market_open_ist


def main():
    now_epoch = now_utc_epoch()
    now_ist_dt = now_ist()
    is_open = is_market_open_ist(now=now_ist_dt)
    next_open = next_market_open_ist(now=now_ist_dt)
    print(f"now_utc_epoch: {now_epoch}")
    print(f"now_ist: {now_ist_dt.isoformat()}")
    print(f"is_market_open_ist: {is_open}")
    print(f"next_market_open_ist: {next_open.isoformat()}")


if __name__ == "__main__":
    sys.exit(main())
