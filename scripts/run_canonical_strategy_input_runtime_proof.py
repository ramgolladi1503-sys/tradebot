import os
import json
import logging
import pytest
from datetime import datetime, timezone, timedelta

# Isolate paths for testing
os.environ["DATA_ROOT"] = "/tmp/canonical_proof/data"
os.environ["LOGS_ROOT"] = "/tmp/canonical_proof/logs"
os.environ["DB_ROOT"] = "/tmp/canonical_proof/db"
os.environ["REPORTS_ROOT"] = "/tmp/canonical_proof/reports"
os.environ["EXECUTION_MODE"] = "PAPER"
os.environ["KITE_USE_API"] = "false"

from config import config as cfg
from core.ohlc_buffer import ohlc_buffer
from core.market_data import fetch_live_market_data, get_ltp
from core.time_utils import now_ist

def run_proof():
    print("Running canonical strategy-input runtime proof harness...")
    # The actual execution happens by invoking pytest on the test suite 
    # to run Scenarios A-G, which will generate the evidence JSON.
    exit_code = pytest.main([
        "-v", 
        "tests/core/test_canonical_strategy_input_runtime_proof.py"
    ])
    return exit_code

if __name__ == "__main__":
    exit(run_proof())
