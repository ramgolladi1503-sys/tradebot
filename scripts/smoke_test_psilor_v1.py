#!/usr/bin/env python3
import os
import sys
import pytz
import logging
import pandas as pd
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from scripts.fetch_psilor_v1_data import UpstoxFetcher

IST_TZ = pytz.timezone('Asia/Kolkata')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_smoke():
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        logging.error("UPSTOX_ACCESS_TOKEN not set")
        sys.exit(1)
        
    start_date = pd.to_datetime("2024-10-02").tz_localize(IST_TZ)
    end_date = start_date + timedelta(days=2)
    
    base_dir = Path("data/psilor_v1/upstox/smoke")
    
    # We will override the fetch loop to strictly only run 1 expiry, 1 future, 2 CE, 2 PE
    # By subclassing the fetcher to hook the discovery
    
    class BoundedFetcher(UpstoxFetcher):
        def fetch_expired_derivatives(self):
            import json
            logging.info("Fetching Bounded Expired Derivatives...")
            expired_dir = self.base_dir / "expired"
            expired_dir.mkdir(parents=True, exist_ok=True)
            
            import urllib
            sym_url = urllib.parse.quote("NSE_INDEX|Nifty 50")
            endpoint = f"/v2/expired-instruments/expiries?instrument_key={sym_url}"
            status, data, raw, m_entry = self._make_request(endpoint, api_version="2.0")
            self.manifest_entries.append(m_entry)
            
            if m_entry["success_blocker_verdict"] not in ["SUCCESS_POPULATED", "SUCCESS_VALID_EMPTY"]:
                return
                
            expiries = data.get("data", []) if data else []
            if not expiries:
                return
            
            # We will iterate through expiries to find the first valid monthly one
            # Save properly in smoke dir (Phase 9 required real output)
            with open(self.base_dir / "expiries.json", "w") as f:
                json.dump(expiries, f, indent=2)
            
            self.metrics["EXPIRED_EXPIRY_DISCOVERY"] = "PASS"
            self.metrics["EXPIRY_METADATA"] = "PASS"
            
            for expiry in expiries:
                # Futures
                f_endp = f"/v2/expired-instruments/future/contract?instrument_key={sym_url}&expiry_date={expiry}"
                f_status, f_data, f_raw, f_mentry = self._make_request(f_endp, api_version="2.0")
                self.manifest_entries.append(f_mentry)
                
                f_contracts = f_data.get("data", []) if f_data else []
                
                # Options
                o_endp = f"/v2/expired-instruments/option/contract?instrument_key={sym_url}&expiry_date={expiry}"
                o_status, o_data, o_raw, o_mentry = self._make_request(o_endp, api_version="2.0")
                self.manifest_entries.append(o_mentry)
                
                o_contracts = o_data.get("data", []) if o_data else []
                ce_contracts = [c for c in o_contracts if c.get("instrument_type") == "CE"]
                pe_contracts = [c for c in o_contracts if c.get("instrument_type") == "PE"]
                
                if f_contracts and len(ce_contracts) >= 2 and len(pe_contracts) >= 2:
                    # Found a valid monthly expiry with both futures and options!
                    self.metrics["EXPIRED_FUTURE_DISCOVERY"] = "PASS"
                    self.metrics["FUTURE_METADATA_DISCOVERED"] += 1
                    
                    f_contracts = f_contracts[:1]
                    
                    with open(self.base_dir / "future_contracts.json", "w") as f:
                        json.dump(f_contracts, f, indent=2)
                        
                    f_dir = self.base_dir / "futures" / expiry
                    f_dir.mkdir(parents=True, exist_ok=True)
                    
                    for c in f_contracts:
                        ik = c.get("instrument_key")
                        if ik:
                            self.metrics["FUTURE_CONTRACTS_REQUESTED"] += 1
                            self.fetch_historical_candles(ik, f_dir / f"{urllib.parse.quote(ik)}.parquet", chunk_monthly=True, version="v2", series_type="FUTURE")
                            
                    self.metrics["EXPIRED_OPTION_DISCOVERY"] = "PASS"
                    self.metrics["OPTION_METADATA_DISCOVERED"] += 4
                    
                    o_contracts_bounded = ce_contracts[:2] + pe_contracts[:2]
                    
                    with open(self.base_dir / "option_contracts.json", "w") as f:
                        json.dump(o_contracts_bounded, f, indent=2)
                        
                    o_dir = self.base_dir / "options" / expiry
                    o_dir.mkdir(parents=True, exist_ok=True)
                    
                    for c in o_contracts_bounded:
                        ik = c.get("instrument_key")
                        type_sym = "CE" if c.get("instrument_type") == "CE" else "PE"
                        if ik:
                            self.metrics["OPTION_CONTRACTS_REQUESTED"] += 1
                            self.fetch_historical_candles(ik, o_dir / f"{urllib.parse.quote(ik)}.parquet", chunk_monthly=True, version="v2", series_type=type_sym)
                            
                    # We have fulfilled the smoke test bounding
                    break

            if self.metrics["FUTURE_CONTRACTS_REQUESTED"] > 0 and self.metrics["OPTION_CONTRACTS_REQUESTED"] > 0:
                self.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"

    logging.info("Starting Bounded Smoke Test...")
    fetcher = BoundedFetcher(start_date, end_date, base_dir=base_dir)
    fetcher.run()
    
    # Calculate SHA256SUMS
    with open(base_dir / "SHA256SUMS", "w") as sums:
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file == "SHA256SUMS": continue
                p = Path(root) / file
                with open(p, "rb") as f:
                    sha = hashlib.sha256(f.read()).hexdigest()
                sums.write(f"{sha}  {p.relative_to(base_dir)}\n")
    
    # Print Verdict
    import json
    report_path = base_dir / "validation_report.json"
    
    # Run asserts based on Phase 9
    real_expiry = len(json.load(open(base_dir / "expiries.json")))
    real_future_contracts = len(json.load(open(base_dir / "future_contracts.json")))
    real_option_contracts = json.load(open(base_dir / "option_contracts.json"))
    real_ce = len([c for c in real_option_contracts if c.get("instrument_type") == "CE"])
    real_pe = len([c for c in real_option_contracts if c.get("instrument_type") == "PE"])
    
    future_files = len(list(base_dir.glob("futures/*/*.parquet")))
    ce_pe_files = len(list(base_dir.glob("options/*/*.parquet")))
    
    logging.info(f"REAL_EXPIRY_DISCOVERED: {real_expiry}")
    logging.info(f"REAL_FUTURE_CONTRACTS: {real_future_contracts}")
    logging.info(f"REAL_CE_CONTRACTS: {real_ce}")
    logging.info(f"REAL_PE_CONTRACTS: {real_pe}")
    logging.info(f"REAL_FUTURE_CANDLE_FILES: {future_files}")
    logging.info(f"REAL_CE_PE_CANDLE_FILES: {ce_pe_files}")

    if real_expiry >= 1 and real_future_contracts >= 1 and real_ce >= 2 and real_pe >= 2 and future_files >= 1 and ce_pe_files >= 4:
        logging.info("Final Verdict: PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE")
    else:
        logging.info("Final Verdict: FAILED_ASSERTIONS")

if __name__ == "__main__":
    run_smoke()
