import json
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import hashlib

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-portable-hash", required=True)
    parser.add_argument("--outdir", required=True)
    return parser.parse_args()

def check_file_quality(path: str, required_instruments: list) -> dict:
    result = {
        "is_valid": False,
        "exact_identity_match": False,
        "opening_window_complete": False,
        "cutoff_window_complete": False,
        "reason": ""
    }
    
    if not Path(path).exists():
        result["reason"] = "FILE_MISSING"
        return result
        
    try:
        df = pd.read_parquet(path, columns=["timestamp", "symbol"])
    except Exception as e:
        result["reason"] = f"READ_ERROR: {e}"
        return result
        
    if df.empty:
        result["reason"] = "EMPTY_DATAFRAME"
        return result
        
    instruments = df["symbol"].unique()
    if len(instruments) != 1 or instruments[0] not in required_instruments:
        result["reason"] = f"INSTRUMENT_MISMATCH: expected {required_instruments}, got {list(instruments)}"
        return result
        
    result["exact_identity_match"] = True
    
    # Check timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")
        
    date_str = df["timestamp"].iloc[0].strftime("%Y-%m-%d")
    
    # Needs to cover at least 09:15 to 14:45
    min_ts = df["timestamp"].min()
    max_ts = df["timestamp"].max()
    
    req_start = pd.Timestamp(f"{date_str} 09:15:00", tz="Asia/Kolkata")
    req_cutoff = pd.Timestamp(f"{date_str} 14:45:00", tz="Asia/Kolkata")
    
    if min_ts > req_start:
        result["reason"] = "MISSING_OPENING_CANDLES"
        return result
        
    result["opening_window_complete"] = True
    
    if max_ts < req_cutoff:
        result["reason"] = "MISSING_CUTOFF_CANDLES"
        return result
        
    result["cutoff_window_complete"] = True
    result["is_valid"] = True
    
    return result

def main():
    args = parse_args()
    
    with open(args.manifest) as f:
        manifest = json.load(f)
        
    if manifest.get("portable_dataset_hash") != args.expected_portable_hash:
        raise ValueError(f"MANIFEST MISMATCH: expected {args.expected_portable_hash}")
        
    files = manifest.get("stable_files", [])
    
    sessions = {}
    
    # Group by date
    for f in files:
        if f.get("data_family") != "underlying_candles":
            continue
            
        path = f.get("absolute_path", "")
        import re
        match = re.search(r"(\d{4}-?\d{2}-?\d{2})", Path(path).name)
        if not match:
            continue
        date = match.group(1).replace("-", "")
            
        # Format date to YYYY-MM-DD for standard ISO
        if len(date) == 8:
            date_iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        else:
            date_iso = date
            
        if date_iso not in sessions:
            sessions[date_iso] = {"nifty_file": None, "banknifty_file": None, "instruments": set()}
            
        instruments = f.get("instruments", [])
        if "NSE_INDEX|Nifty 50" in instruments or "NIFTY" in instruments:
            if not sessions[date_iso]["nifty_file"]:
                sessions[date_iso]["nifty_file"] = f["absolute_path"]
        if "NSE_INDEX|Nifty Bank" in instruments or "BANKNIFTY" in instruments:
            if not sessions[date_iso]["banknifty_file"]:
                sessions[date_iso]["banknifty_file"] = f["absolute_path"]
                
        for i in instruments:
            sessions[date_iso]["instruments"].add(i)
            
    audit_results = []
    eligible_dates = []
    
    for date in sorted(sessions.keys()):
        nifty_file = sessions[date]["nifty_file"]
        banknifty_file = sessions[date]["banknifty_file"]
        
        status = {
            "date": date,
            "nifty_file": nifty_file,
            "banknifty_file": banknifty_file,
            "parsed_instruments": list(sessions[date]["instruments"]),
            "manifest_inclusion": True,
            "is_eligible": False,
            "rejection_reason": None,
            "nifty_audit": None,
            "banknifty_audit": None
        }
        
        if not nifty_file or not banknifty_file:
            status["rejection_reason"] = "MISSING_REQUIRED_INDEX"
            audit_results.append(status)
            continue
            
        nifty_audit = check_file_quality(nifty_file, ["NSE_INDEX|Nifty 50", "NIFTY"])
        banknifty_audit = check_file_quality(banknifty_file, ["NSE_INDEX|Nifty Bank", "BANKNIFTY"])
        
        status["nifty_audit"] = nifty_audit
        status["banknifty_audit"] = banknifty_audit
        
        if not nifty_audit["is_valid"]:
            status["rejection_reason"] = f"NIFTY_INVALID: {nifty_audit['reason']}"
            audit_results.append(status)
            continue
            
        if not banknifty_audit["is_valid"]:
            status["rejection_reason"] = f"BANKNIFTY_INVALID: {banknifty_audit['reason']}"
            audit_results.append(status)
            continue
            
        status["is_eligible"] = True
        eligible_dates.append(date)
        audit_results.append(status)
        
    out_path = Path(args.outdir) / "session_universe_audit.json"
    
    summary = {
        "observed_date_count": len(audit_results),
        "eligible_date_count": len(eligible_dates),
        "ineligible_date_count": len(audit_results) - len(eligible_dates),
        "eligible_dates": eligible_dates,
        "eligible_list_sha256": hashlib.sha256(json.dumps(eligible_dates).encode("utf-8")).hexdigest(),
        "sessions": audit_results
    }
    
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
        
    print(f"Generated universe audit at {out_path}")
    print(f"Eligible sessions: {len(eligible_dates)}")

if __name__ == "__main__":
    main()
