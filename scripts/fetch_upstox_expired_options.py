import argparse
import os
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import pytz

KOLKATA = pytz.timezone("Asia/Kolkata")

def safe_encode(key):
    return urllib.parse.quote(key)

class UpstoxClient:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Accept": "application/json",
            "Api-Version": "3.0",
            "Authorization": f"Bearer {token}",
            "User-Agent": "curl/8.4.0"
        }
    
    def request(self, url, max_retries=5):
        if not self.token:
            raise ValueError("AUTHENTICATION_BLOCKED: No access token provided.")
            
        req = urllib.request.Request(url, headers=self.headers)
        attempt = 0
        while attempt < max_retries:
            try:
                start_time = time.time()
                with urllib.request.urlopen(req, timeout=10) as response:
                    raw = response.read()
                    elapsed = time.time() - start_time
                    return {
                        "status": response.status,
                        "raw": raw,
                        "elapsed": elapsed,
                        "success": True,
                        "error_code": None,
                        "message": "OK"
                    }
            except urllib.error.HTTPError as e:
                elapsed = time.time() - start_time
                if e.code == 401:
                    return {"status": e.code, "raw": None, "elapsed": elapsed, "success": False, "error_code": "AUTH_FAILED", "message": "AUTHENTICATION_BLOCKED"}
                elif e.code == 403:
                    body = e.read()
                    msg = "PLUS_ENTITLEMENT_BLOCKED"
                    try:
                        j = json.loads(body)
                        if any(err.get('errorCode') == 'UDAPI1149' for err in j.get('errors', [])):
                            msg = "UDAPI1149 Plus Entitlement Blocked"
                    except Exception:
                        pass
                    return {"status": e.code, "raw": body, "elapsed": elapsed, "success": False, "error_code": "FORBIDDEN", "message": msg}
                elif e.code == 429:
                    retry_after = int(e.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    attempt += 1
                    continue
                elif e.code in (500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                elif e.code == 404:
                    return {"status": e.code, "raw": None, "elapsed": elapsed, "success": False, "error_code": "NOT_FOUND", "message": "Not Found"}
                else:
                    return {"status": e.code, "raw": None, "elapsed": elapsed, "success": False, "error_code": f"HTTP_{e.code}", "message": str(e)}
            except Exception as e:
                time.sleep(2 ** attempt)
                attempt += 1
        
        return {"status": None, "raw": None, "elapsed": 0, "success": False, "error_code": "MAX_RETRIES", "message": "Max retries exceeded"}

def hash_data(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def discover_expiries(client, underlying_key, out_root):
    print(f"Discovering expiries for {underlying_key}")
    url = f"https://api.upstox.com/v2/expired-instruments/expiries?instrument_key={safe_encode(underlying_key)}"
    res = client.request(url)
    if not res["success"]:
        print(f"Failed to fetch expiries: {res['message']}")
        return None
    
    data = json.loads(res["raw"])
    expiries = sorted(data.get("data", []))
    if not expiries:
        print("No expiries returned by API.")
        return []
    
    out_dir = out_root / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "expiry_inventory.json", "w") as f:
        json.dump(expiries, f, indent=2)
        
    print(f"Discovered {len(expiries)} expiries. Earliest: {expiries[0]}, Latest: {expiries[-1]}")
    return expiries

def get_contracts(client, underlying_key, expiry):
    url = f"https://api.upstox.com/v2/expired-instruments/option/contract?instrument_key={safe_encode(underlying_key)}&expiry_date={expiry}"
    res = client.request(url)
    if not res["success"]:
        print(f"Failed to fetch contracts for {expiry}: {res['message']}")
        return []
    
    data = json.loads(res["raw"])
    return data.get("data", [])

def get_candles(client, inst_key, interval, from_date, to_date):
    url = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{safe_encode(inst_key)}/{interval}/{to_date}/{from_date}"
    res = client.request(url)
    return res

def fetch_pipeline(args):
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("AUTHENTICATION_BLOCKED: Missing UPSTOX_ACCESS_TOKEN")
        return
        
    client = UpstoxClient(token)
    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)
    
    if args.command == "discover-expiries":
        discover_expiries(client, args.underlying_key, out_root)
        
    elif args.command == "pilot":
        expiries = discover_expiries(client, args.underlying_key, out_root)
        if not expiries:
            return
            
        recent = sorted(expiries)[-args.recent_expiries:]
        print(f"Pilot selected expiries: {recent}")
        
        # We need NIFTY underlying candles to find ATM.
        if not args.underlying_candles:
            print("Warning: no --underlying-candles passed. Cannot determine ATM properly.")
            # For pilot we might fake ATM if not passed, but let's just fail for safety
            print("Please pass --underlying-candles parquet.")
            return
            
        # load underlying
        df_und = pd.read_parquet(args.underlying_candles)
        df_und['timestamp'] = pd.to_datetime(df_und['timestamp']).dt.tz_convert(KOLKATA)
        
        # group by session date to find open/first price
        df_und['date'] = df_und['timestamp'].dt.date
        session_opens = df_und.groupby('date').first().reset_index()[['date', 'open']]
        
        all_contracts = []
        for exp in recent:
            conts = get_contracts(client, args.underlying_key, exp)
            all_contracts.extend(conts)
            
            # Save raw contracts
            raw_c_dir = out_root / "raw" / "responses" / args.underlying / f"expiry={exp}"
            raw_c_dir.mkdir(parents=True, exist_ok=True)
            with open(raw_c_dir / "contracts.json", "w") as f:
                json.dump(conts, f, indent=2)
                
        df_c = pd.DataFrame(all_contracts)
        
        manifest = []
        for exp in recent:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            # find underlying price on the expiry date (or nearest before)
            # a better way is to loop over every session date in the cycle up to expiry
            # For simplicity in Pilot: let's just use the expiry day itself.
            sess_row = session_opens[session_opens['date'] == exp_date]
            if len(sess_row) == 0:
                print(f"No underlying data for {exp_date}")
                continue
            spot = sess_row.iloc[0]['open']
            print(f"Session {exp_date} Spot Open: {spot}")
            
            # find ATM
            exp_conts = df_c[df_c['expiry'] == exp]
            strikes = sorted(exp_conts['strike_price'].unique())
            if not strikes:
                continue
            closest_strike = min(strikes, key=lambda x: abs(x - spot))
            idx = strikes.index(closest_strike)
            
            w = args.strike_wings
            selected_strikes = strikes[max(0, idx - w):min(len(strikes), idx + w + 1)]
            print(f"Selected strikes for {exp}: {selected_strikes}")
            
            target_conts = exp_conts[exp_conts['strike_price'].isin(selected_strikes)]
            
            for _, cont in target_conts.iterrows():
                inst = cont['instrument_key']
                opt = cont['instrument_type']
                strike = cont['strike_price']
                
                print(f"Fetching {opt} {strike} ({inst})")
                
                # from_date = start of week? Upstox requires from_date to to_date
                # for pilot we can fetch just 7 days before expiry
                from_d = (exp_date - timedelta(days=7)).strftime("%Y-%m-%d")
                to_d = exp
                
                res = get_candles(client, inst, args.interval, from_d, to_d)
                
                safe_inst = inst.replace("|", "_").replace(" ", "_")
                if res["success"]:
                    raw_dir = out_root / "raw" / "responses" / args.underlying / f"expiry={exp}" / f"instrument={safe_inst}"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_path = raw_dir / f"candles_{args.interval}.json"
                    with open(raw_path, "wb") as f:
                        f.write(res["raw"])
                    
                    sha = hash_data(res["raw"])
                    with open(str(raw_path) + ".sha256", "w") as f:
                        f.write(sha)
                        
                    # Normalize
                    cdata = json.loads(res["raw"]).get("data", {}).get("candles", [])
                    if cdata:
                        ndf = pd.DataFrame(cdata, columns=["timestamp", "open", "high", "low", "close", "volume", "open_interest"])
                        ndf['timestamp'] = pd.to_datetime(ndf['timestamp'])
                        
                        # Data-quality gate: OHLC check
                        invalid = (ndf['high'] < ndf[['open', 'close', 'low']].max(axis=1)) | (ndf['low'] > ndf[['open', 'close', 'high']].min(axis=1))
                        if invalid.any():
                            print(f"Warning: {invalid.sum()} invalid OHLC rows for {inst}")
                            ndf = ndf[~invalid]
                            
                        ndf['underlying'] = args.underlying
                        ndf['underlying_key'] = args.underlying_key
                        ndf['expiry'] = exp
                        ndf['strike'] = strike
                        ndf['option_type'] = opt
                        ndf['trading_symbol'] = cont['trading_symbol']
                        ndf['expired_instrument_key'] = inst
                        ndf['exchange_token'] = cont['exchange_token']
                        ndf['lot_size'] = cont['lot_size']
                        ndf['weekly'] = cont['weekly']
                        ndf['source'] = 'upstox_plus'
                        ndf['interval'] = args.interval
                        ndf['fetched_at'] = datetime.utcnow().isoformat()
                        ndf['raw_response_sha256'] = sha
                        
                        norm_dir = out_root / "normalized" / f"candles_{args.interval}" / f"underlying={args.underlying}" / f"expiry={exp}" / f"option_type={opt}" / f"strike={strike}"
                        norm_dir.mkdir(parents=True, exist_ok=True)
                        ndf.to_parquet(norm_dir / "part.parquet", index=False)
                        print(f"Saved {len(ndf)} rows for {opt} {strike}")
                
        print("Pilot done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upstox Expired Options Fetch Pipeline")
    subparsers = parser.add_subparsers(dest="command")
    
    p_disc = subparsers.add_parser("discover-expiries")
    p_disc.add_argument("--underlying-key", required=True)
    p_disc.add_argument("--output-root", required=True)
    
    p_pilot = subparsers.add_parser("pilot")
    p_pilot.add_argument("--underlying", required=True)
    p_pilot.add_argument("--underlying-key", required=True)
    p_pilot.add_argument("--recent-expiries", type=int, required=True)
    p_pilot.add_argument("--strike-wings", type=int, required=True)
    p_pilot.add_argument("--interval", required=True)
    p_pilot.add_argument("--output-root", required=True)
    p_pilot.add_argument("--underlying-candles", required=True)
    
    p_fetch = subparsers.add_parser("fetch")
    p_fetch.add_argument("--underlying", required=True)
    p_fetch.add_argument("--underlying-key", required=True)
    p_fetch.add_argument("--mode", required=True)
    p_fetch.add_argument("--strike-wings", type=int, required=True)
    p_fetch.add_argument("--interval", required=True)
    p_fetch.add_argument("--resume", action="store_true")
    p_fetch.add_argument("--output-root", required=True)
    
    p_val = subparsers.add_parser("validate")
    p_val.add_argument("--output-root", required=True)
    
    p_agg = subparsers.add_parser("aggregate")
    p_agg.add_argument("--source-interval", required=True)
    p_agg.add_argument("--target-interval", required=True)
    p_agg.add_argument("--output-root", required=True)
    
    args = parser.parse_args()
    fetch_pipeline(args)
