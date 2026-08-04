import json
import logging
import csv
import calendar
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pandas as pd

logger = logging.getLogger("subscription_planner")

NIFTY_50_CONSTITUENTS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "ITC", "INFY", "INDIGO",
    "JSWSTEEL", "JIOFIN", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "MAXHEALTH", "NTPC", "NESTLEIND", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TMPV", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"
]

def load_instrument_master(json_path: Path) -> list[dict]:
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.values())
        return list(data)
    except Exception as e:
        logger.error(f"Failed to load instrument master: {e}")
        return []

def parse_expiry(expiry_val) -> date:
    if isinstance(expiry_val, (int, float)):
        return datetime.fromtimestamp(expiry_val / 1000.0, tz=timezone.utc).date()
    elif isinstance(expiry_val, str):
        if expiry_val.isdigit():
            return datetime.fromtimestamp(float(expiry_val) / 1000.0, tz=timezone.utc).date()
        return datetime.strptime(expiry_val, "%Y-%m-%d").date()
    else:
        raise ValueError(f"Invalid expiry format/type: {expiry_val} ({type(expiry_val)})")

def is_monthly_by_calendar(d: date) -> bool:
    c = calendar.monthcalendar(d.year, d.month)
    thursdays = [week[3] for week in c if week[3] != 0]
    return d.day == thursdays[-1]

def resolve_option_surface_weekly_monthly(instruments: list[dict], underlying_name: str, spot_price: float, reference_date: date = None) -> tuple[list[str], dict]:
    today = reference_date or date.today()

    opts = [
        i for i in instruments
        if i.get("name") == underlying_name
        and i.get("instrument_type") in ["CE", "PE"]
        and i.get("expiry") is not None
    ]
    if not opts:
        raise ValueError(f"No option instruments found for {underlying_name}")

    valid_opts = []
    for opt in opts:
        try:
            exp_date = parse_expiry(opt["expiry"])
            if exp_date >= today:
                opt_copy = dict(opt)
                opt_copy["_exp_date"] = exp_date
                valid_opts.append(opt_copy)
        except Exception:
            pass

    if not valid_opts:
        raise ValueError(f"No future option expiries found for {underlying_name}")

    weekly_expiries = set()
    monthly_expiries = set()

    for opt in valid_opts:
        exp_date = opt["_exp_date"]
        is_wk = opt.get("weekly")
        if is_wk is None:
            is_wk = not is_monthly_by_calendar(exp_date)

        if is_wk:
            weekly_expiries.add(exp_date)
        else:
            monthly_expiries.add(exp_date)

    if not weekly_expiries and not monthly_expiries:
        raise ValueError("Could not resolve any option expiries")

    nearest_weekly = min(weekly_expiries) if weekly_expiries else min(monthly_expiries)

    # Select nearest monthly expiry that is strictly after or equal to nearest weekly
    future_monthlies = [m for m in sorted(list(monthly_expiries)) if m >= nearest_weekly]
    if not future_monthlies:
        # Fallback to any future expiry marked monthly
        future_monthlies = sorted(list(monthly_expiries))

    if future_monthlies:
        first_monthly = future_monthlies[0]
        if first_monthly == nearest_weekly:
            next_monthlies = [m for m in future_monthlies if m > nearest_weekly]
            nearest_monthly = next_monthlies[0] if next_monthlies else first_monthly
        else:
            nearest_monthly = first_monthly
    else:
        # Fallback calendar calculation if no weekly=False entry exists
        all_future_expiries = sorted(list(set(o["_exp_date"] for o in valid_opts)))
        monthlies = [e for e in all_future_expiries if is_monthly_by_calendar(e)]
        nearest_monthly = monthlies[0] if monthlies else all_future_expiries[-1]

    # ATM Strike Calculation (step 50 for NIFTY)
    atm_weekly = round(spot_price / 50.0) * 50.0
    atm_monthly = round(spot_price / 50.0) * 50.0

    weekly_strike_list = [atm_weekly + (i * 50.0) for i in range(-10, 11)]
    monthly_strike_list = [atm_monthly + (i * 50.0) for i in range(-5, 6)]

    weekly_matched = [
        o for o in valid_opts
        if o["_exp_date"] == nearest_weekly and float(o.get("strike_price", 0.0)) in weekly_strike_list
    ]
    monthly_matched = [
        o for o in valid_opts
        if o["_exp_date"] == nearest_monthly and float(o.get("strike_price", 0.0)) in monthly_strike_list
    ]

    weekly_keys = [o["instrument_key"] for o in weekly_matched]
    monthly_keys = [o["instrument_key"] for o in monthly_matched]

    # Validation Checks
    weekly_ce = sum(1 for o in weekly_matched if o.get("instrument_type") == "CE")
    weekly_pe = sum(1 for o in weekly_matched if o.get("instrument_type") == "PE")
    monthly_ce = sum(1 for o in monthly_matched if o.get("instrument_type") == "CE")
    monthly_pe = sum(1 for o in monthly_matched if o.get("instrument_type") == "PE")

    weekly_strikes_found = set(float(o.get("strike_price")) for o in weekly_matched)
    monthly_strikes_found = set(float(o.get("strike_price")) for o in monthly_matched)

    atm_present = (atm_weekly in weekly_strikes_found) and (atm_monthly in monthly_strikes_found)
    symmetric = (weekly_ce == 21 and weekly_pe == 21 and monthly_ce == 11 and monthly_pe == 11)
    distinct_expiries = (nearest_weekly != nearest_monthly)

    report = {
        "weekly_expiry": nearest_weekly.isoformat(),
        "monthly_expiry": nearest_monthly.isoformat(),
        "weekly_ce_count": weekly_ce,
        "weekly_pe_count": weekly_pe,
        "monthly_ce_count": monthly_ce,
        "monthly_pe_count": monthly_pe,
        "weekly_strikes": sorted(list(weekly_strikes_found)),
        "monthly_strikes": sorted(list(monthly_strikes_found)),
        "atm_present": atm_present,
        "symmetric": symmetric,
        "distinct_expiries": distinct_expiries,
        "status": "PASS" if (atm_present and symmetric and distinct_expiries) else "FAIL"
    }

    if report["status"] != "PASS":
        reasons = []
        if not atm_present: reasons.append(f"ATM {atm_weekly} missing")
        if not symmetric: reasons.append(f"CE/PE counts asymmetrical or window incomplete (weekly CE={weekly_ce}/PE={weekly_pe}, monthly CE={monthly_ce}/PE={monthly_pe})")
        if not distinct_expiries: reasons.append(f"Expiries collapsed: weekly={nearest_weekly} == monthly={nearest_monthly}")
        raise ValueError(f"Option surface validation failed for {underlying_name}: " + ", ".join(reasons))

    all_keys = sorted(list(set(weekly_keys + monthly_keys)))
    return all_keys, report

def resolve_futures(instruments: list[dict], name: str, count: int = 2, reference_date: date = None) -> list[str]:
    today = reference_date or date.today()
    futs = [
        i for i in instruments
        if i.get("name") == name and i.get("instrument_type") == "FUT"
    ]
    valid_futs = []
    for fut in futs:
        try:
            exp_date = parse_expiry(fut.get("expiry"))
            if exp_date >= today:
                fut_copy = dict(fut)
                fut_copy["_exp_date"] = exp_date
                valid_futs.append(fut_copy)
        except Exception:
            pass
    valid_futs.sort(key=lambda x: x["_exp_date"])
    unique_expiries = sorted(list(set([x["_exp_date"] for x in valid_futs])))
    if not unique_expiries:
        raise ValueError(f"No future contracts found for {name}")
    targets = unique_expiries[:count]
    matched = [x["instrument_key"] for x in valid_futs if x["_exp_date"] in targets]
    return sorted(list(set(matched)))

def build_subscription_plan(instruments_path: Path, output_dir: Path, nifty_spot: float, reference_date: date = None, restrict_universe: bool = True) -> tuple[dict, dict]:
    instruments = load_instrument_master(instruments_path)
    if not instruments:
        raise FileNotFoundError(f"Instrument master missing or empty at {instruments_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    full_keys = set()
    ltpc_keys = set()
    exclusions = []

    # 1. Spot Indices
    indices_mapping = {
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "NIFTY BANK": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
        "INDIA VIX": "NSE_INDEX|India VIX",
        "NIFTY FINANCIAL SERVICES": "NSE_INDEX|Nifty Fin Service",
        "NIFTY IT": "NSE_INDEX|Nifty IT",
        "NIFTY AUTO": "NSE_INDEX|Nifty Auto",
        "NIFTY FMCG": "NSE_INDEX|Nifty FMCG",
        "NIFTY PHARMA": "NSE_INDEX|Nifty Pharma",
        "NIFTY METAL": "NSE_INDEX|Nifty Metal",
        "NIFTY ENERGY": "NSE_INDEX|Nifty Energy",
    }

    if restrict_universe:
        # Exclude SENSEX from active full keys
        indices_mapping.pop("SENSEX", None)

    for name, key in indices_mapping.items():
        found = any(i.get("instrument_key") == key for i in instruments)
        if found:
            full_keys.add(key)
        else:
            exclusions.append((name, "INDEX", "Spot Index missing in master"))

    # 2. Options Surface
    nifty_option_keys, surface_report = resolve_option_surface_weekly_monthly(
        instruments, "NIFTY", nifty_spot, reference_date=reference_date
    )
    full_keys.update(nifty_option_keys)

    if restrict_universe:
        exclusions.append(("BANKNIFTY", "OPTIONS", "BANKNIFTY options excluded for NIFTY MEG validation run"))
        exclusions.append(("SENSEX", "OPTIONS", "SENSEX options excluded for NIFTY MEG validation run"))

    # 3. Futures
    nifty_futures = resolve_futures(instruments, "NIFTY", count=2, reference_date=reference_date)
    full_keys.update(nifty_futures)

    if restrict_universe:
        exclusions.append(("BANKNIFTY", "FUTURES", "BANKNIFTY futures excluded for NIFTY MEG validation run"))

    # 4. NIFTY 50 constituents
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

    if not restrict_universe:
        # Add LTPC broad market if not restricted
        fo_underlyings = set(i.get("name") for i in instruments if i.get("segment") == "NSE_FO" and i.get("name"))
        for und in fo_underlyings:
            eq_matches = [
                i for i in instruments
                if i.get("trading_symbol") == und
                and i.get("instrument_type") == "EQ"
                and i.get("exchange") == "NSE"
            ]
            if eq_matches:
                ltpc_keys.add(eq_matches[0]["instrument_key"])
    else:
        exclusions.append(("BROAD_FO_LTPC", "EQ", "Broad market LTPC universe excluded for NIFTY MEG validation run"))

    full_list = sorted(list(full_keys))
    ltpc_list = sorted(list(ltpc_keys - set(full_list)))

    # Fail-closed Budget Validation
    FULL_LIMIT = 2000
    LTPC_LIMIT = 5000
    COMBINED_LIMIT = 7000

    requested_full = len(full_list)
    requested_ltpc = len(ltpc_list)
    accepted_full = min(requested_full, FULL_LIMIT)
    accepted_ltpc = min(requested_ltpc, LTPC_LIMIT)
    omitted = []

    if requested_full > FULL_LIMIT:
        budget_verdict = f"FAIL_SUBSCRIPTION_BUDGET Full limit exceeded: requested {requested_full} > {FULL_LIMIT}"
        omitted = full_list[FULL_LIMIT:]
    elif requested_ltpc > LTPC_LIMIT:
        budget_verdict = f"FAIL_SUBSCRIPTION_BUDGET LTPC limit exceeded: requested {requested_ltpc} > {LTPC_LIMIT}"
        omitted = ltpc_list[LTPC_LIMIT:]
    else:
        budget_verdict = "PASS_SUBSCRIPTION_BUDGET"

    budget_report = {
        "provider": "upstox",
        "feed_version": "v3",
        "entitlement_source": "upstox_developer_api",
        "full_limit": FULL_LIMIT,
        "ltpc_limit": LTPC_LIMIT,
        "combined_limit": COMBINED_LIMIT,
        "requested_full": requested_full,
        "requested_ltpc": requested_ltpc,
        "accepted_full": accepted_full,
        "accepted_ltpc": accepted_ltpc,
        "omitted_instruments": omitted,
        "budget_verdict": budget_verdict
    }

    if budget_verdict != "PASS_SUBSCRIPTION_BUDGET":
        raise ValueError(budget_verdict)

    plan = {
        "full": full_list,
        "ltpc": ltpc_list,
        "surface_report": surface_report,
        "budget_report": budget_report
    }

    with open(output_dir / "universe_plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    with open(output_dir / "exclusions.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol", "Type", "Reason"])
        writer.writerows(exclusions)

    with open(output_dir / "subscription_budget.json", "w") as f:
        json.dump(budget_report, f, indent=2)

    logger.info(f"Generated subscription plan: {requested_full} Full, {requested_ltpc} LTPC. Budget verdict: {budget_verdict}")
    return plan, budget_report
