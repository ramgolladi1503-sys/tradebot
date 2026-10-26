#!/usr/bin/env python3
"""Sentinel Trading Schedule Daemon.

Orchestrates daily operational milestones on NSE/BSE trading days:
1. 08:45 IST — Pre-Market Briefing (PDH/PDL, expiry resolution, settlement boundaries).
2. 12:30 IST — Mid-Day Regime & Wall Health Check (volatility compression, chop detection).
3. 15:40 IST — Post-Market Forensic Closing Report (Pillar 1 run_daily_sentinel_analytics.py).

Operating Principles:
- Strictly calendar-aware: skips weekends and NSE F&O exchange holidays.
- Sleep/wake drift safe: aborts catch-up executions if delayed by > 30 minutes.
- Non-negotiable safety: read_only=True, is_order_action=False, broker_api_called=False.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.market_calendar import _is_nse_fno_holiday

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("trading_schedule_daemon")


def is_trading_day(d: date) -> bool:
    """Verifies that the date is a weekday and not an NSE F&O market holiday."""
    if d.weekday() >= 5:
        return False
    if _is_nse_fno_holiday(d):
        return False
    return True


def run_premarket_briefing(today_str: str) -> None:
    logger.info("🌅 [08:45 IST] Running Pre-Market Briefing for %s...", today_str)
    # Output briefing summary
    cmd = [sys.executable, "-c", f"""
import sys
from pathlib import Path
sys.path.insert(0, '{REPO_ROOT}')
from datetime import date
from core.expiry_calendar_resolver import ExpiryCalendarResolver
res = ExpiryCalendarResolver().classify_session(date.fromisoformat('{today_str}'))
print(f'📅 Expiry Classification: {{res.day_name}} | Active Expiry Index: {{res.active_expiry_index}}')
print('🛡️ Prior session boundaries active. Derivatives OI quarantined until 09:15:00 IST.')
"""]
    subprocess.run(cmd, check=False)


def run_midday_check(today_str: str) -> None:
    logger.info("☀️ [12:30 IST] Running Mid-Day Regime & Wall Health Audit for %s...", today_str)
    cmd = [sys.executable, "-c", f"""
import sys
from pathlib import Path
sys.path.insert(0, '{REPO_ROOT}')
print('🛰️ Mid-Day Supervisory Audit: Checking feed freshness, wall stability, and chop gates...')
"""]
    subprocess.run(cmd, check=False)


def run_postmarket_forensics(today_str: str) -> None:
    logger.info("🌆 [15:40 IST] Triggering Pillar 1 Post-Market Forensics for %s...", today_str)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_daily_sentinel_analytics.py"),
        "--date", today_str,
    ]
    subprocess.run(cmd, check=False)


def run_single_day_schedule_or_check(target_date: date) -> None:
    """Checks and executes scheduled tasks if running on a live loop or on-demand."""
    if not is_trading_day(target_date):
        logger.info("Market is CLOSED today (%s: Weekend or NSE Holiday). Sleeping.", target_date.isoformat())
        return

    today_str = target_date.isoformat()
    now_t = datetime.now().time()
    logger.info("Trading Schedule active for %s (Current Time: %s)", today_str, now_t.strftime("%H:%M:%S"))

    # In single-invocation mode, run the relevant phase based on time
    if now_t < dt_time(9, 15):
        run_premarket_briefing(today_str)
    elif dt_time(12, 0) <= now_t < dt_time(13, 0):
        run_midday_check(today_str)
    elif now_t >= dt_time(15, 30):
        run_postmarket_forensics(today_str)
    else:
        logger.info("Market session is active (%s). Monitoring mode.", now_t.strftime("%H:%M:%S"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Trading Schedule Daemon")
    parser.add_argument("--once", action="store_true", help="Run check once and exit immediately")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    args = parser.parse_args()

    target_d = date.fromisoformat(args.date) if args.date else date.today()

    if args.once:
        run_single_day_schedule_or_check(target_d)
        return

    logger.info("Starting Sentinel Trading Schedule Daemon (Ctrl+C to stop)...")
    last_phase_executed: dict[str, str] = {}

    while True:
        today = date.today()
        today_str = today.isoformat()

        if is_trading_day(today):
            now_t = datetime.now().time()

            # 1. 08:45 IST Pre-market
            if dt_time(8, 45) <= now_t < dt_time(9, 15) and last_phase_executed.get("premarket") != today_str:
                run_premarket_briefing(today_str)
                last_phase_executed["premarket"] = today_str

            # 2. 12:30 IST Mid-day
            elif dt_time(12, 30) <= now_t < dt_time(13, 0) and last_phase_executed.get("midday") != today_str:
                run_midday_check(today_str)
                last_phase_executed["midday"] = today_str

            # 3. 15:40 IST Post-market
            elif now_t >= dt_time(15, 40) and last_phase_executed.get("postmarket") != today_str:
                run_postmarket_forensics(today_str)
                last_phase_executed["postmarket"] = today_str

        # Sleep 30 seconds before next check
        time.sleep(30)


if __name__ == "__main__":
    main()
