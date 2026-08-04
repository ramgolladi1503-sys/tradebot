import os
import json
import csv
from pathlib import Path
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger("subscription_planner")

NIFTY_50_CONSTITUENTS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "LTIM", "M&M", "MARUTI", "NTPC", "NESTLEIND", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SUNPHARMA",
    "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM",
    "TITAN", "ULTRACEMCO", "WIPRO", "SHRIRAMFIN"
]

def load_instrument_master(path: Path) -> list[dict]:
    if not path.exists():
        logger.error(f"Instrument master JSON not found at {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.values())
        return list(data)
    except Exception as e:
        logger.error(f"Failed to load instrument master: {e}")
        return []

def resolve_option_surface(instruments: list[dict], underlying_name: str, spot_price: float, strikes_count: int = 10, step_size: float = 100.0) -> list[str]:
    """Finds CE/PE options ATM +- strikes_count for the nearest expiry of underlying."""
    today = datetime.now().date()
    
    opts = [
        i for i in instruments
        if i.get("name") == underlying_name
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry")
    ]
    if not opts:
        return []
        
    valid_opts = []
    for opt in opts:
        try:
            exp_date = datetime.strptime(opt["expiry"], "%Y-%m-%d").date()
            if exp_date >= today:
                opt["_exp_date"] = exp_date
                valid_opts.append(opt)
        except Exception:
            pass
            
    if not valid_opts:
        return []
        
    valid_opts.sort(key=lambda x: x["_exp_date"])
    nearest_expiry = valid_opts[0]["_exp_date"]
    
    # Filter for nearest expiry
    df_exp = pd.DataFrame([o for o in valid_opts if o["_exp_date"] == nearest_expiry])
    if df_exp.empty:
        return []
        
    # Find ATM and strikes window
    atm = round(spot_price / step_size) * step_size
    strikes = [atm + (i * step_size) for i in range(-strikes_count, strikes_count + 1)]
    
    df_strikes = df_exp[df_exp['strike_price'].isin(strikes)]
    return df_strikes['instrument_key'].tolist()

def resolve_futures(instruments: list[dict], name: str, count: int = 2) -> list[str]:
    today = datetime.now().date()
    futs = [
        i for i in instruments
        if i.get("name") == name and i.get("instrument_type") == "FUT"
    ]
    valid_futs = []
    for fut in futs:
        try:
            exp_date = datetime.strptime(fut.get("expiry", ""), "%Y-%m-%d").date()
            if exp_date >= today:
                fut["_exp_date"] = exp_date
                valid_futs.append(fut)
        except Exception:
            pass
    valid_futs.sort(key=lambda x: x["_exp_date"])
    unique_expiries = sorted(list(set([x["_exp_date"] for x in valid_futs])))
    if not unique_expiries:
        return []
    targets = unique_expiries[:count]
    return [x["instrument_key"] for x in valid_futs if x["_exp_date"] in targets]

def build_subscription_plan(instruments_path: Path, output_dir: Path, underlying_prices: dict) -> dict:
    instruments = load_instrument_master(instruments_path)
    if not instruments:
        return {"full": [], "ltpc": []}

    output_dir.mkdir(parents=True, exist_ok=True)

    full_keys = set()
    ltpc_keys = set()
    exclusions = []

    # 1. Spot Indices (Tier A1)
    indices_mapping = {
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "NIFTY BANK": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
        "INDIA VIX": "NSE_INDEX|India VIX"
    }
    for name, key in indices_mapping.items():
        found = any(i.get("instrument_key") == key for i in instruments)
        if found:
            full_keys.add(key)
        else:
            exclusions.append((name, "INDEX", "Spot Index missing in master"))

    # 2. Options Surface (Tier A3)
    # NIFTY ATM +- 10 (step 50)
    nifty_options = resolve_option_surface(instruments, "NIFTY", underlying_prices.get("NIFTY", 24500.0), strikes_count=10, step_size=50.0)
    full_keys.update(nifty_options)
    
    # BANKNIFTY ATM +- 10 (step 100)
    banknifty_options = resolve_option_surface(instruments, "BANKNIFTY", underlying_prices.get("BANKNIFTY", 52200.0), strikes_count=10, step_size=100.0)
    full_keys.update(banknifty_options)
    
    # SENSEX ATM +- 10 (step 100)
    sensex_options = resolve_option_surface(instruments, "SENSEX", underlying_prices.get("SENSEX", 80000.0), strikes_count=10, step_size=100.0)
    full_keys.update(sensex_options)

    # 3. Futures (Tier A1)
    full_keys.update(resolve_futures(instruments, "NIFTY", count=2))
    full_keys.update(resolve_futures(instruments, "BANKNIFTY", count=2))

    # 4. NIFTY 50 constituents (Tier A2)
    for symbol in NIFTY_50_CONSTITUENTS:
        eq_matches = [
            i for i in instruments
            if i.get("trading_symbol") == symbol
            and i.get("instrument_type") == "EQ"
            and i.get("exchange") == "NSE"
        ]
        if eq_matches:
            full_keys.add(eq_matches[0]["instrument_key"])
        else:
            exclusions.append((symbol, "EQ", "Constituent EQ missing in master"))

    # 5. Broad Market LTPC (Lane B)
    # Get all F&O underlyings
    fo_underlyings = set(i.get("name") for i in instruments if i.get("segment") == "NSE_FO" and i.get("name"))
    # Add their equity equivalents to LTPC
    for und in fo_underlyings:
        eq_matches = [
            i for i in instruments
            if i.get("trading_symbol") == und
            and i.get("instrument_type") == "EQ"
            and i.get("exchange") == "NSE"
        ]
        if eq_matches:
            ltpc_keys.add(eq_matches[0]["instrument_key"])

    # Enforce strict V3 limits: 2,000 for Full, 5,000 for LTPC
    full_list = sorted(list(full_keys))
    if len(full_list) > 2000:
        logger.warning(f"Full feed keys ({len(full_list)}) exceed 2,000 limit. Truncating.")
        full_list = full_list[:2000]

    ltpc_list = sorted(list(ltpc_keys - set(full_list)))
    if len(ltpc_list) > 5000:
        logger.warning(f"LTPC feed keys ({len(ltpc_list)}) exceed 5,000 limit. Truncating.")
        ltpc_list = ltpc_list[:5000]

    plan = {
        "full": full_list,
        "ltpc": ltpc_list
    }

    # Save outputs
    with open(output_dir / "universe_plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    with open(output_dir / "exclusions.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol", "Type", "Reason"])
        writer.writerows(exclusions)

    logger.info(f"Generated subscription plan: {len(full_list)} Full, {len(ltpc_list)} LTPC. Excluded {len(exclusions)} instruments.")
    return plan
