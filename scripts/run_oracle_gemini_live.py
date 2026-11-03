"""
ORACLE Runner Daemon
====================
Standalone, decoupled daemon that continuously inspects live market telemetry from
the Upstox capture chunks and evaluates decisions via Gemini Live Copilot.

Attribution: [ORACLE_GEMINI_LIVE]
Independent log: logs/oracle_gemini_live_{YYYYMMDD}.log
"""

import time
import os
import sys
import glob
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")
from core.oracle_live_gemini_adapter import OracleGeminiLiveAdapter

def run_oracle_daemon():
    print("=================================================================")
    print("Starting ORACLE Gemini Live Copilot Daemon")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Attribution Prefix: [ORACLE_GEMINI_LIVE]")
    print("=================================================================")

    adapter = OracleGeminiLiveAdapter(poll_interval_sec=30.0, signal_cooldown_sec=120.0)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Dynamic capture directory lookup across external volumes and local fallback
    potential_dirs = [
        Path(f"/Volumes/TradeBot/live market capture/{today_str}/chunks"),
        Path(f"/Volumes/TradeBotData/live market capture/{today_str}/chunks"),
        Path(f"/Volumes/TradeBotFast/live market capture/{today_str}/chunks"),
        REPO_ROOT / ".runtime" / "market_data" / today_str / "chunks",
    ]
    capture_dir = next((p for p in potential_dirs if p.exists()), potential_dirs[-1])
    print(f"Tracking capture directory: {capture_dir}")

    # Known morning range seeded from exchange
    or_high = 23317.0
    or_low = 23211.8

    # Try querying official RBFN levels for spot boundaries
    trend_decider, upper_reversal, lower_reversal = 0.0, 0.0, 0.0
    try:
        from research.rbfn_options.core.spot_boundary_model import get_official_rbfn_boundaries
        rbfn_b = get_official_rbfn_boundaries(datetime.now().strftime("%Y-%m-%d"))
        if rbfn_b:
            trend_decider = rbfn_b.trend_decider
            upper_reversal = rbfn_b.upper_reversal
            lower_reversal = rbfn_b.lower_reversal
    except Exception as e:
        print(f"RBFN boundary lookup fallback: {e}")

    while True:
        try:
            raw_chunks = glob.glob(os.path.join(capture_dir, "*.parquet"))
            if not raw_chunks:
                time.sleep(2)
                continue

            # Sort by file modification time so newly written chunks are read first
            chunks = sorted(raw_chunks, key=os.path.getmtime)
            
            # Read latest chunk
            latest_chunk = chunks[-1]
            df = pd.read_parquet(latest_chunk)
            
            # Fetch real-time live Spot directly from Upstox quote API
            token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
            spot = 0.0
            if token:
                try:
                    encoded_key = urllib.parse.quote("NSE_INDEX|Nifty 50")
                    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={encoded_key}"
                    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        qdata = json.loads(resp.read().decode())
                        spot = float(qdata["data"]["NSE_INDEX:Nifty 50"]["last_price"])
                except Exception as ex:
                    pass
            
            if spot <= 0.0:
                spot = 23250.0

            # Dynamically round to nearest ATM strike (e.g. 23230 -> 23250 ATM)
            atm_strike = int(round(spot / 50.0) * 50)
            
            # Extract latest matching strikes from parquet if available
            ce_symbol = f"NIFTY {atm_strike} CE"
            pe_symbol = f"NIFTY {atm_strike} PE"
            atm_ce = 0.0
            atm_pe = 0.0

            ce_rows = df[df["symbol"].str.contains(ce_symbol, na=False)]
            pe_rows = df[df["symbol"].str.contains(pe_symbol, na=False)]
            if not ce_rows.empty:
                atm_ce = float(ce_rows.iloc[-1]["ltp"])
            if not pe_rows.empty:
                atm_pe = float(pe_rows.iloc[-1]["ltp"])
            
            # Evaluate via Gemini with full structured contract and boundary grounding
            adapter.evaluate_market_snapshot(
                spot=spot,
                or_high=or_high,
                or_low=or_low,
                trend_decider=trend_decider,
                upper_reversal=upper_reversal,
                lower_reversal=lower_reversal,
                futures_basis=0.90,
                candidate_ce_symbol=ce_symbol,
                candidate_ce_ltp=atm_ce,
                candidate_pe_symbol=pe_symbol,
                candidate_pe_ltp=atm_pe,
            )
            time.sleep(30)
        except Exception as e:
            print(f"Daemon cycle error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_oracle_daemon()
