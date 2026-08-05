#!/usr/bin/env python3
import os
import sys
import pytz
import logging
import pandas as pd
from datetime import datetime, timedelta
from scripts.fetch_psilor_v1_data import UpstoxFetcher

IST_TZ = pytz.timezone('Asia/Kolkata')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_smoke():
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        logging.error("UPSTOX_ACCESS_TOKEN not set")
        sys.exit(1)
        
    start_date = pd.to_datetime("2026-07-02").tz_localize(IST_TZ)
    end_date = start_date + timedelta(days=2)
    
    logging.info("Starting Bounded Smoke Test...")
    fetcher = UpstoxFetcher(start_date, end_date)
    fetcher.run()
    
    # Check results
    import json
    report_path = "data/psilor_v1/upstox/validation_report.json"
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            metrics = json.load(f)
            logging.info(f"Final Verdict: {metrics.get('DATA_ADMISSION_VERDICT')}")
    else:
        logging.error("validation_report.json not produced.")

if __name__ == "__main__":
    run_smoke()
