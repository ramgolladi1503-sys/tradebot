#!/usr/bin/env python3
import os
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import urllib.parse
import urllib.request
import time
import hashlib
from dateutil.relativedelta import relativedelta
import logging
import gzip
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

UPSTOX_BASE_URL = "https://api.upstox.com"

class UpstoxDataError(Exception):
    pass

class UpstoxFetcher:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
        self.base_dir = Path("data/psilor_v1/upstox")
        self.ref_dir = Path("data/psilor_v1/reference")
        
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.manifest_entries = []
        self.validation_errors = []
        
        self.metrics = {
            "NIFTY_INDEX_SESSIONS": set(),
            "VIX_OVERLAP_SESSIONS": set(),
            "CONSTITUENT_MEMBERSHIP_AUTHORITY": "FAIL",
            "CONSTITUENT_SESSIONS": set(),
            "EXPIRED_FUTURES_OVERLAP_SESSIONS": set(),
            "EXPIRED_OPTION_OVERLAP_SESSIONS": set(),
            
            "BOTH_CE_AND_PE": "FAIL",
            "EXPIRY_METADATA": "FAIL",
            "ONE_MINUTE_INTERVAL_ONLY": "PASS",
            "DUPLICATE_CONFLICTS": 0,
            
            "INDEX_FETCH": "FAIL",
            "VIX_FETCH": "FAIL",
            "CONSTITUENT_FETCH": "FAIL",
            "EXPIRED_EXPIRY_DISCOVERY": "FAIL",
            "EXPIRED_FUTURE_CONTRACT_DISCOVERY": "FAIL",
            "EXPIRED_OPTION_CONTRACT_DISCOVERY": "FAIL",
            "EXPIRED_CANDLE_FETCH": "FAIL",
            
            "OPTION_METADATA_DISCOVERED": 0,
            "OPTION_CANDLES_ATTEMPTED": 0,
            "OPTION_CANDLES_SUCCESS": 0,
            "OPTION_UNIVERSE_COMPLETENESS": "FAIL",
            
            "DATA_ADMISSION_VERDICT": "INVALID_FETCH_IMPLEMENTATION"
        }
        
        self.blockers = set()

    def _make_request(self, endpoint, api_version="3.0", max_retries=3, method="GET"):
        url = f"{UPSTOX_BASE_URL}{endpoint}"
        
        req = urllib.request.Request(url, method=method, headers={
            "Accept": "application/json",
            "Api-Version": api_version,
            "Authorization": f"Bearer {self.token}"
        })
        
        req_id = str(uuid.uuid4())
        manifest_entry = {
            "request_id": req_id,
            "endpoint_family": endpoint.split('?')[0].split('/')[1] if len(endpoint.split('/')) > 1 else endpoint,
            "URL": url,
            "attempt_count": 0,
            "HTTP_status": 0,
            "Upstox_error_code": None,
            "response_row_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "output_file": None,
            "SHA-256": None,
            "success_blocker_verdict": None,
            "instrument_key": None,
            "expiry_date": None,
            "interval": None,
            "from_date": None,
            "to_date": None
        }

        parsed_url = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed_url.query)
        if "instrument_key" in qs:
            manifest_entry["instrument_key"] = qs["instrument_key"][0]
        if "expiry_date" in qs:
            manifest_entry["expiry_date"] = qs["expiry_date"][0]
            
        parts = parsed_url.path.split('/')
        if "historical-candle" in parts:
            try:
                manifest_entry["instrument_key"] = urllib.parse.unquote(parts[-4])
                manifest_entry["interval"] = parts[-3]
                manifest_entry["to_date"] = parts[-2]
                manifest_entry["from_date"] = parts[-1]
            except IndexError:
                pass

        for attempt in range(max_retries):
            manifest_entry["attempt_count"] += 1
            try:
                with urllib.request.urlopen(req) as response:
                    status = response.status
                    body = response.read()
                    data = json.loads(body.decode())
                    
                    manifest_entry["HTTP_status"] = status
                    manifest_entry["SHA-256"] = hashlib.sha256(body).hexdigest()
                    manifest_entry["success_blocker_verdict"] = "SUCCESS"
                    
                    return status, data, body, manifest_entry
                    
            except urllib.error.HTTPError as e:
                manifest_entry["HTTP_status"] = e.code
                if e.code == 429:
                    retry_after = e.headers.get("Retry-After")
                    sleep_time = int(retry_after) if retry_after else (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
                
                try:
                    body = e.read()
                    data = json.loads(body.decode())
                    if "errors" in data and len(data["errors"]) > 0:
                        err_code = data["errors"][0].get("errorCode")
                        manifest_entry["Upstox_error_code"] = err_code
                        if err_code == "UDAPI1149":
                            self.blockers.add("BLOCKED_UPSTOX_PLUS_REQUIRED")
                            manifest_entry["success_blocker_verdict"] = "BLOCKED_UPSTOX_PLUS_REQUIRED"
                            return e.code, data, body, manifest_entry
                except Exception:
                    pass
                
                manifest_entry["success_blocker_verdict"] = f"HTTP_ERROR_{e.code}"
                return e.code, None, b"", manifest_entry
                
            except Exception as e:
                manifest_entry["success_blocker_verdict"] = "CONNECTION_ERROR"
                logging.error(f"Request failed: {url}, Error: {e}")
                return 0, None, b"", manifest_entry
                
        manifest_entry["success_blocker_verdict"] = "MAX_RETRIES_EXCEEDED"
        return 429, None, b"", manifest_entry

    def validate_candles(self, candles, instrument_key):
        if not candles:
            return None
            
        records = []
        timestamps = {}
        
        first_ts = None
        last_ts = None
        
        for c in candles:
            if len(c) < 6:
                self.validation_errors.append(f"Invalid candle length for {instrument_key}")
                continue
                
            ts_str = c[0].replace('+05:30', '')
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                self.validation_errors.append(f"Timestamp parse error: {c[0]}")
                continue
                
            try:
                o, h, l, cl, v = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
                oi = float(c[6]) if len(c) > 6 else 0.0
            except ValueError:
                self.validation_errors.append(f"Non-numeric OHLCV for {instrument_key} at {ts}")
                continue
                
            candle_data = (o, h, l, cl, v, oi)
                
            if ts in timestamps:
                if timestamps[ts] == candle_data:
                    # Deterministic deduplication of identical candle
                    continue
                else:
                    self.metrics["DUPLICATE_CONFLICTS"] += 1
                    self.validation_errors.append(f"Duplicate timestamp mismatch {ts} for {instrument_key}")
                    raise UpstoxDataError(f"Duplicate candle conflict for {instrument_key} at {ts}")
                    
            timestamps[ts] = candle_data
            
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
            
            if not all(x >= 0 for x in [h, v, oi]) or not (h >= max(o, cl, l) and l <= min(o, cl, h)):
                self.validation_errors.append(f"OHLCV bounds violation for {instrument_key} at {ts}")
                raise UpstoxDataError(f"OHLCV bounds violation for {instrument_key} at {ts}")
                
            records.append({
                "timestamp": ts,
                "open": o, "high": h, "low": l, "close": cl, "volume": v, "open_interest": oi
            })
            
        return records, first_ts, last_ts

    def fetch_instrument_master(self):
        logging.info("Fetching Instrument Master...")
        date_str = datetime.now().strftime("%Y-%m-%d")
        master_dir = self.base_dir / "instrument_master" / f"captured_{date_str}"
        master_dir.mkdir(parents=True, exist_ok=True)
        
        complete_json_path = master_dir / "complete.json"
        
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                raw_data = gzip.decompress(response.read())
                data = json.loads(raw_data)
                
                with open(complete_json_path, "w") as f:
                    json.dump(data, f, separators=(',', ':'))
                
                manifest = {
                    "capture_date": date_str,
                    "source_effective_date": "UNKNOWN_UNLESS_PROVEN",
                    "historical_authority": False,
                    "row_count": len(data)
                }
                with open(master_dir / "manifest.json", "w") as f:
                    json.dump(manifest, f, indent=2)
                
        except Exception as e:
            logging.error(f"Failed to fetch BOD: {e}")
            self.validation_errors.append(f"Instrument master fetch failed: {e}")

    def fetch_historical_candles(self, symbol, out_path, chunk_monthly=False, interval="1minute", version="v3", metric_set=None):
        url_key = urllib.parse.quote(symbol)
        all_records = []
        
        current = self.start_date
        while current <= self.end_date:
            if chunk_monthly:
                next_date = current + relativedelta(months=1)
                chunk_end = min(self.end_date, next_date - timedelta(days=1))
            else:
                next_date = current + timedelta(days=1)
                chunk_end = current
                
            to_date = chunk_end.strftime("%Y-%m-%d")
            from_date = current.strftime("%Y-%m-%d")
            
            if version == "v3":
                endpoint = f"/v3/historical-candle/{url_key}/minutes/1/{to_date}/{from_date}"
            else:
                endpoint = f"/v2/expired-instruments/historical-candle/{url_key}/1minute/{to_date}/{from_date}"
                
            status, data, raw_body, m_entry = self._make_request(endpoint, api_version="3.0" if version == "v3" else "2.0")
            
            if data and "data" in data and "candles" in data["data"]:
                try:
                    res = self.validate_candles(data["data"]["candles"], symbol)
                    if res:
                        records, first_ts, last_ts = res
                        all_records.extend(records)
                        m_entry["response_row_count"] = len(records)
                        m_entry["first_timestamp"] = first_ts.isoformat() if first_ts else None
                        m_entry["last_timestamp"] = last_ts.isoformat() if last_ts else None
                        
                        if metric_set is not None:
                            for r in records:
                                metric_set.add(r["timestamp"].strftime("%Y-%m-%d"))
                except UpstoxDataError as e:
                    logging.error(e)
                    m_entry["success_blocker_verdict"] = "VALIDATION_FAILED"
            elif m_entry["success_blocker_verdict"] == "SUCCESS":
                m_entry["success_blocker_verdict"] = "EMPTY_RESPONSE_FAILED"
                self.validation_errors.append(f"Empty response for {symbol}")

            m_entry["output_file"] = str(out_path)
            self.manifest_entries.append(m_entry)
            
            if "BLOCKED_UPSTOX_PLUS_REQUIRED" in self.blockers:
                return None
                
            current = next_date
        
        if all_records:
            df = pd.DataFrame(all_records)
            df = df.sort_values("timestamp")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out_path)
            return df
        return None

    def fetch_indices(self):
        logging.info("Fetching Index Data...")
        df = self.fetch_historical_candles(
            "NSE_INDEX|Nifty 50", 
            self.base_dir / "index" / "nifty_50_1m.parquet", 
            chunk_monthly=True,
            metric_set=self.metrics["NIFTY_INDEX_SESSIONS"]
        )
        if df is not None and not df.empty:
            self.metrics["INDEX_FETCH"] = "PASS"
            
        df = self.fetch_historical_candles(
            "NSE_INDEX|India VIX", 
            self.base_dir / "vix" / "india_vix_1m.parquet", 
            chunk_monthly=True,
            metric_set=self.metrics["VIX_OVERLAP_SESSIONS"]
        )
        if df is not None and not df.empty:
            self.metrics["VIX_FETCH"] = "PASS"

    def fetch_constituents(self):
        logging.info("Fetching Constituents...")
        eff_date = self.end_date.strftime("%Y-%m-%d")
        manifest_path = self.ref_dir / f"nifty_constituents_{eff_date}.json"
        
        if not manifest_path.exists():
            self.blockers.add("MISSING_POINT_IN_TIME_NIFTY_CONSTITUENT_MANIFEST")
            self.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"] = "FAIL"
            logging.error("MISSING_POINT_IN_TIME_NIFTY_CONSTITUENT_MANIFEST: Cannot fetch dummy constituents. Proceeding with remainder.")
            return

        self.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"] = "PASS"
        with open(manifest_path, "r") as f:
            constituents = json.load(f).get("constituents", [])
            
        success_count = 0
        for symbol in constituents:
            clean_sym = symbol.split("|")[-1] if "|" in symbol else symbol
            out_path = self.base_dir / "constituents" / eff_date / f"{clean_sym}_1m.parquet"
            df = self.fetch_historical_candles(symbol, out_path, chunk_monthly=True, metric_set=self.metrics["CONSTITUENT_SESSIONS"])
            if df is not None and not df.empty:
                success_count += 1
                
        if success_count > 0:
            self.metrics["CONSTITUENT_FETCH"] = "PASS"

    def fetch_expired_derivatives(self):
        logging.info("Fetching Expired Derivatives...")
        expired_dir = self.base_dir / "expired"
        expired_dir.mkdir(parents=True, exist_ok=True)
        
        sym_url = urllib.parse.quote("NSE_INDEX|Nifty 50")
        endpoint = f"/v2/expired-instruments/expiries?instrument_key={sym_url}"
        status, data, raw, m_entry = self._make_request(endpoint, api_version="2.0")
        self.manifest_entries.append(m_entry)
        
        if "BLOCKED_UPSTOX_PLUS_REQUIRED" in self.blockers:
            return
            
        expiries = data.get("data", []) if data else []
        if not expiries:
            self.validation_errors.append("No expiries discovered")
            return
            
        with open(expired_dir / "expiries.json", "w") as f:
            json.dump(expiries, f, indent=2)
        
        self.metrics["EXPIRED_EXPIRY_DISCOVERY"] = "PASS"
        self.metrics["EXPIRY_METADATA"] = "PASS"
        
        has_future_fetch = False
        has_option_fetch = False
        
        for expiry in expiries:
            try:
                exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
                if exp_dt < self.start_date or exp_dt > self.end_date + timedelta(days=30):
                    continue
            except ValueError:
                pass
                
            # Future contracts
            f_endp = f"/v2/expired-instruments/future/contract?instrument_key={sym_url}&expiry_date={expiry}"
            f_status, f_data, f_raw, f_mentry = self._make_request(f_endp, api_version="2.0")
            self.manifest_entries.append(f_mentry)
            
            f_contracts = f_data.get("data", []) if f_data else []
            if f_contracts:
                self.metrics["EXPIRED_FUTURE_CONTRACT_DISCOVERY"] = "PASS"
                f_dir = expired_dir / "futures" / expiry
                f_dir.mkdir(parents=True, exist_ok=True)
                with open(f_dir / "contracts.json", "w") as f:
                    json.dump(f_contracts, f, indent=2)
                
                for c in f_contracts:
                    ik = c.get("instrument_key")
                    if ik:
                        df = self.fetch_historical_candles(ik, f_dir / f"{urllib.parse.quote(ik)}.parquet", chunk_monthly=True, version="v2", metric_set=self.metrics["EXPIRED_FUTURES_OVERLAP_SESSIONS"])
                        if df is not None and not df.empty:
                            has_future_fetch = True
            
            # Option contracts
            o_endp = f"/v2/expired-instruments/option/contract?instrument_key={sym_url}&expiry_date={expiry}"
            o_status, o_data, o_raw, o_mentry = self._make_request(o_endp, api_version="2.0")
            self.manifest_entries.append(o_mentry)
            
            o_contracts = o_data.get("data", []) if o_data else []
            if o_contracts:
                self.metrics["EXPIRED_OPTION_CONTRACT_DISCOVERY"] = "PASS"
                self.metrics["OPTION_METADATA_DISCOVERED"] += len(o_contracts)
                
                ce_found = any(c.get("instrument_type") == "CE" for c in o_contracts)
                pe_found = any(c.get("instrument_type") == "PE" for c in o_contracts)
                if ce_found and pe_found:
                    self.metrics["BOTH_CE_AND_PE"] = "PASS"
                
                o_dir = expired_dir / "options" / expiry
                o_dir.mkdir(parents=True, exist_ok=True)
                with open(o_dir / "contracts.json", "w") as f:
                    json.dump(o_contracts, f, indent=2)
                    
                for c in o_contracts:
                    ik = c.get("instrument_key")
                    if ik:
                        self.metrics["OPTION_CANDLES_ATTEMPTED"] += 1
                        df = self.fetch_historical_candles(ik, o_dir / f"{urllib.parse.quote(ik)}.parquet", chunk_monthly=True, version="v2", metric_set=self.metrics["EXPIRED_OPTION_OVERLAP_SESSIONS"])
                        if df is not None and not df.empty:
                            has_option_fetch = True
                            self.metrics["OPTION_CANDLES_SUCCESS"] += 1

        if has_future_fetch and has_option_fetch:
            self.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
            
        if self.metrics["OPTION_CANDLES_ATTEMPTED"] > 0 and self.metrics["OPTION_CANDLES_ATTEMPTED"] == self.metrics["OPTION_CANDLES_SUCCESS"]:
            self.metrics["OPTION_UNIVERSE_COMPLETENESS"] = "COMPLETE_RECONCILED"
        elif self.metrics["OPTION_CANDLES_ATTEMPTED"] > 0:
            self.metrics["OPTION_UNIVERSE_COMPLETENESS"] = "PARTIAL_DECLARED"

    def compute_verdict(self):
        if "BLOCKED_UPSTOX_PLUS_REQUIRED" in self.blockers:
            self.metrics["DATA_ADMISSION_VERDICT"] = "BLOCKED_UPSTOX_PLUS_REQUIRED"
            return
            
        # 1. Overlapping sessions calculation (exact dates)
        base_sets = [
            self.metrics["NIFTY_INDEX_SESSIONS"], 
            self.metrics["VIX_OVERLAP_SESSIONS"], 
            self.metrics["EXPIRED_FUTURES_OVERLAP_SESSIONS"], 
            self.metrics["EXPIRED_OPTION_OVERLAP_SESSIONS"]
        ]
        
        overlap = set.intersection(*base_sets) if all(base_sets) else set()
        
        # Determine verdict
        if "MISSING_POINT_IN_TIME_NIFTY_CONSTITUENT_MANIFEST" in self.blockers:
            if len(overlap) >= 30:
                verdict = "DATA_READY_FOR_DORL_ONLY"
            else:
                verdict = "BLOCKED_MISSING_CONSTITUENT_AUTHORITY"
        else:
            psilor_sets = base_sets + [self.metrics["CONSTITUENT_SESSIONS"]]
            psilor_overlap = set.intersection(*psilor_sets) if all(psilor_sets) else set()
            if len(psilor_overlap) >= 30:
                verdict = "DATA_READY_FOR_PSILOR_PROXY_VALIDATION"
            elif len(overlap) >= 30:
                verdict = "DATA_READY_FOR_DORL_ONLY"
            else:
                verdict = "BLOCKED_INSUFFICIENT_OVERLAP"
                
        if self.metrics["EXPIRED_CANDLE_FETCH"] != "PASS" or self.metrics["BOTH_CE_AND_PE"] != "PASS":
            verdict = "BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS"
            
        self.metrics["DATA_ADMISSION_VERDICT"] = verdict

    def generate_reports(self):
        with open(self.base_dir / "fetch_manifest.json", "w") as f:
            json.dump(self.manifest_entries, f, indent=2)
            
        self.compute_verdict()
            
        report = {
            "INDEX_FETCH": self.metrics["INDEX_FETCH"],
            "VIX_FETCH": self.metrics["VIX_FETCH"],
            "CONSTITUENT_MEMBERSHIP_AUTHORITY": self.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"],
            "CONSTITUENT_FETCH": self.metrics["CONSTITUENT_FETCH"],
            "EXPIRED_EXPIRY_DISCOVERY": self.metrics["EXPIRED_EXPIRY_DISCOVERY"],
            "EXPIRED_FUTURE_CONTRACT_DISCOVERY": self.metrics["EXPIRED_FUTURE_CONTRACT_DISCOVERY"],
            "EXPIRED_OPTION_CONTRACT_DISCOVERY": self.metrics["EXPIRED_OPTION_CONTRACT_DISCOVERY"],
            "EXPIRED_CANDLE_FETCH": self.metrics["EXPIRED_CANDLE_FETCH"],
            "OPTION_UNIVERSE_COMPLETENESS": self.metrics["OPTION_UNIVERSE_COMPLETENESS"],
            "OPTION_METADATA_DISCOVERED": self.metrics["OPTION_METADATA_DISCOVERED"],
            "OPTION_CANDLES_ATTEMPTED": self.metrics["OPTION_CANDLES_ATTEMPTED"],
            "OPTION_CANDLES_SUCCESS": self.metrics["OPTION_CANDLES_SUCCESS"],
            "DATA_ADMISSION_VERDICT": self.metrics["DATA_ADMISSION_VERDICT"],
            "DUPLICATE_CONFLICTS": self.metrics["DUPLICATE_CONFLICTS"],
            "errors": self.validation_errors
        }
        
        with open(self.base_dir / "validation_report.json", "w") as f:
            json.dump(report, f, indent=2)

    def run(self):
        self.fetch_instrument_master()
        self.fetch_indices()
        self.fetch_constituents()
        self.fetch_expired_derivatives()
        self.generate_reports()
        logging.info(f"Data fetch process completed. Verdict: {self.metrics['DATA_ADMISSION_VERDICT']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    default_end = datetime.now()
    default_start = default_end - relativedelta(months=6)
    
    parser.add_argument("--start-date", type=str, default=default_start.strftime("%Y-%m-%d"))
    parser.add_argument("--end-date", type=str, default=default_end.strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    
    fetcher = UpstoxFetcher(start, end)
    fetcher.run()
