#!/usr/bin/env python3
"""
Safe live run supervisor — wraps main.py with restart on fatal exit.
Does NOT enable live orders. Does NOT change safety gates.
ALLOW_LIVE_ORDERS, MANUAL_APPROVAL_REQUIRED etc. must be set by caller.
"""

import os
import sys
import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="[supervisor] %(message)s")
logger = logging.getLogger(__name__)


def run_supervisor(args, executable=sys.executable, script_name="main.py"):
    max_restarts = int(os.environ.get("LIVE_SUPERVISED_MAX_RESTARTS", "10"))
    wait_sec = float(os.environ.get("LIVE_SUPERVISED_RESTART_WAIT_SEC", "15.0"))

    logger.info(f"Starting tradebot supervised run. MAX_RESTARTS={max_restarts}")

    restart_count = 0
    while restart_count < max_restarts:
        attempt = restart_count + 1
        logger.info(f"Attempt {attempt}/{max_restarts}")

        cmd = [executable, script_name] + args

        try:
            exit_code = subprocess.call(cmd)
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt. Exiting supervisor.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Failed to execute {script_name}: {e}")
            exit_code = 1

        if exit_code == 0:
            logger.info("Clean exit (code 0). Not restarting.")
            break

        logger.info(f"Exited code={exit_code}. Restarting in {wait_sec}s...")
        time.sleep(wait_sec)
        restart_count += 1

    logger.info(f"Done. restarts={restart_count}")
    return restart_count


if __name__ == "__main__":
    run_supervisor(sys.argv[1:])
